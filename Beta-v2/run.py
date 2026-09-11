"""Reliable local launcher for the Beta-v2 backend and frontend.

The launcher performs read-only port probes before starting either child,
waits for bounded HTTP health checks, and keeps supervising both processes.
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence


BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"
RUNTIME_DIR = BACKEND_DIR / "runtime"
LAUNCHER_LOG_PATH = RUNTIME_DIR / "launcher.log"

HOST = "127.0.0.1"
BACKEND_PORT = 8010
FRONTEND_PORT = 3000
BACKEND_URL = f"http://{HOST}:{BACKEND_PORT}"
FRONTEND_URL = f"http://{HOST}:{FRONTEND_PORT}"

HTTP_PROBE_TIMEOUT_SECONDS = 0.75
STARTUP_TIMEOUT_SECONDS = 20.0
HEALTH_POLL_INTERVAL_SECONDS = 0.25
MONITOR_INTERVAL_SECONDS = 0.5
SHUTDOWN_TIMEOUT_SECONDS = 5.0
LAUNCHER_LOG_MAX_BYTES = 2_097_152
LAUNCHER_LOG_BACKUP_COUNT = 3

_launcher_logger = logging.getLogger("beta_v2.launcher")
_launcher_handler: RotatingFileHandler | None = None
_launcher_log_destination: Path | None = None
_launcher_run_id = "-"
_last_health_failure: dict[str, tuple[str, int]] = {}


class _LauncherContextFilter(logging.Filter):
    """Attach the current launch attempt ID to every persisted row."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = _launcher_run_id
        return True


def configure_launcher_logging(path: Path | None = None) -> bool:
    """Open a rotating launcher log without making startup depend on it."""

    global _launcher_handler, _launcher_log_destination

    if _launcher_handler is not None:
        return True
    destination = Path(path or LAUNCHER_LOG_PATH)
    handler: RotatingFileHandler | None = None
    try:
        if destination.is_symlink():
            raise OSError("launcher log path must not be a symbolic link")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination = destination.resolve()
        handler = RotatingFileHandler(
            destination,
            maxBytes=LAUNCHER_LOG_MAX_BYTES,
            backupCount=LAUNCHER_LOG_BACKUP_COUNT,
            encoding="utf-8",
            # Open eagerly so a successful return guarantees that this launch
            # can actually persist diagnostics at the advertised path.
            delay=False,
        )
        formatter = logging.Formatter(
            "%(asctime)sZ level=%(levelname)s run_id=%(run_id)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        formatter.converter = time.gmtime
        handler.setFormatter(formatter)
        handler.addFilter(_LauncherContextFilter())
        _launcher_logger.setLevel(logging.INFO)
        _launcher_logger.propagate = False
        _launcher_logger.addHandler(handler)
        _launcher_handler = handler
        _launcher_log_destination = destination
        return True
    except (OSError, ValueError):
        if handler is not None:
            handler.close()
        _launcher_log_destination = None
        return False


def shutdown_launcher_logging() -> None:
    """Flush and close the launcher-owned file handle."""

    global _launcher_handler, _launcher_log_destination

    handler = _launcher_handler
    _launcher_handler = None
    _launcher_log_destination = None
    if handler is not None:
        _launcher_logger.removeHandler(handler)
        handler.close()


def _os_error_fields(exc: OSError) -> tuple[str, int, int]:
    """Classify an OS error without retaining its potentially sensitive text."""

    error_number = exc.errno if isinstance(exc.errno, int) else 0
    winerror_value = getattr(exc, "winerror", 0)
    winerror = winerror_value if isinstance(winerror_value, int) else 0
    numeric = winerror or error_number
    if numeric in {48, 98, 10048}:
        reason = "address_in_use"
    elif numeric in {13, 10013}:
        reason = "permission_denied"
    else:
        reason = "probe_error"
    return reason, error_number, winerror


def _safe_exception_fields(exc: BaseException) -> tuple[str, int, int]:
    """Return non-message exception diagnostics safe for persistent logs."""

    if isinstance(exc, OSError):
        _reason, error_number, winerror = _os_error_fields(exc)
        return type(exc).__name__, error_number, winerror
    return type(exc).__name__, 0, 0


def _is_timeout_error(exc: BaseException) -> bool:
    """Recognize direct and urllib-wrapped socket timeout failures."""

    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    if isinstance(exc, urllib.error.URLError):
        return isinstance(exc.reason, (TimeoutError, socket.timeout))
    return False


def _safe_service_name(value: str) -> str:
    return value if value in {"backend", "frontend"} else "unknown"


class LauncherError(RuntimeError):
    """A safe, user-facing launcher failure."""


@dataclass(frozen=True)
class HealthTarget:
    """Description of one local service health check."""

    name: str
    url: str
    expected_json_status: str | None = None


HEALTH_TARGETS = (
    HealthTarget("backend", f"{BACKEND_URL}/ready", expected_json_status="ready"),
    HealthTarget("frontend", f"{FRONTEND_URL}/"),
)


def port_is_free(
    host: str,
    port: int,
) -> bool:
    """Return whether ``host:port`` can be reserved by a new local server.

    A short bind-and-close probe is used instead of ``connect_ex``. On Windows,
    a timed connect to a closed loopback port can report WSAEWOULDBLOCK (10035),
    which is ambiguous and previously caused both free ports to be rejected.
    """

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
            if exclusive is not None:
                probe.setsockopt(socket.SOL_SOCKET, exclusive, 1)
            probe.bind((host, port))
            return True
    except OSError as exc:
        reason, error_number, winerror = _os_error_fields(exc)
        _launcher_logger.warning(
            "event=port_probe_failed port=%d reason=%s errno=%d winerror=%d",
            port,
            reason,
            error_number,
            winerror,
        )
        return False


def find_unavailable_ports() -> list[tuple[str, int]]:
    """Return configured launcher ports that cannot safely be used."""

    configured_ports = (
        ("backend", BACKEND_PORT),
        ("frontend", FRONTEND_PORT),
    )
    return [
        (name, port)
        for name, port in configured_ports
        if not port_is_free(HOST, port)
    ]


def http_is_healthy(
    target: HealthTarget,
    *,
    timeout: float = HTTP_PROBE_TIMEOUT_SECONDS,
) -> bool:
    """Perform a bounded GET against a fixed loopback health target."""

    request = urllib.request.Request(
        target.url,
        headers={"Accept": "application/json, text/html", "User-Agent": "Beta-v2-launcher"},
        method="GET",
    )
    service = _safe_service_name(target.name)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            http_status = int(response.getcode() or 0)
            if http_status != 200:
                _last_health_failure[service] = ("http_error", int(http_status or 0))
                return False
            if target.expected_json_status is None:
                _last_health_failure.pop(service, None)
                return True
            try:
                payload = json.loads(response.read(4097))
            except (ValueError, UnicodeError, json.JSONDecodeError):
                _last_health_failure[service] = ("invalid_json", http_status)
                return False
            healthy = (
                isinstance(payload, dict)
                and payload.get("status") == target.expected_json_status
            )
            if healthy:
                _last_health_failure.pop(service, None)
            else:
                _last_health_failure[service] = ("status_mismatch", http_status)
            return healthy
    except urllib.error.HTTPError as exc:
        _last_health_failure[service] = ("http_error", int(exc.code or 0))
        return False
    except (OSError, ValueError, urllib.error.URLError) as exc:
        reason = "timeout" if _is_timeout_error(exc) else "unreachable"
        _last_health_failure[service] = (reason, 0)
        return False


def wait_for_services(
    processes: Mapping[str, subprocess.Popen[bytes]],
    targets: Sequence[HealthTarget] = HEALTH_TARGETS,
    *,
    timeout: float = STARTUP_TIMEOUT_SECONDS,
    poll_interval: float = HEALTH_POLL_INTERVAL_SECONDS,
    healthcheck: Callable[[HealthTarget], bool] | None = None,
) -> None:
    """Wait until all targets are healthy or raise a bounded launcher error."""

    checker = healthcheck or http_is_healthy
    pending = {target.name: target for target in targets}
    started = {target.name: time.monotonic() for target in targets}
    deadline = time.monotonic() + max(0.0, timeout)

    while pending:
        for name, process in processes.items():
            exit_code = process.poll()
            if exit_code is not None:
                _launcher_logger.error(
                    "event=child_exited phase=startup service=%s exit_code=%d",
                    _safe_service_name(name),
                    exit_code,
                )
                raise LauncherError(
                    f"{name.capitalize()} server exited during startup "
                    f"(exit code {exit_code})."
                )

        for name, target in tuple(pending.items()):
            if checker(target):
                pending.pop(name)
                _launcher_logger.info(
                    "event=service_healthy service=%s elapsed_ms=%d",
                    _safe_service_name(name),
                    round((time.monotonic() - started[name]) * 1000),
                )

        if not pending:
            return

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            names = ", ".join(sorted(pending))
            for name in sorted(pending):
                reason, http_status = _last_health_failure.get(
                    _safe_service_name(name),
                    ("unknown", 0),
                )
                _launcher_logger.error(
                    "event=service_health_timeout service=%s reason=%s "
                    "http_status=%d timeout_seconds=%g",
                    _safe_service_name(name),
                    reason,
                    http_status,
                    timeout,
                )
            raise LauncherError(
                f"Timed out after {timeout:g}s waiting for: {names}."
            )
        time.sleep(min(max(0.0, poll_interval), remaining))


def monitor_processes(
    processes: Mapping[str, subprocess.Popen[bytes]],
    *,
    poll_interval: float = MONITOR_INTERVAL_SECONDS,
) -> None:
    """Supervise every child until interrupted or one exits."""

    while True:
        for name, process in processes.items():
            exit_code = process.poll()
            if exit_code is not None:
                _launcher_logger.error(
                    "event=child_exited phase=runtime service=%s exit_code=%d",
                    _safe_service_name(name),
                    exit_code,
                )
                raise LauncherError(
                    f"{name.capitalize()} server exited unexpectedly "
                    f"(exit code {exit_code})."
                )
        time.sleep(max(0.01, poll_interval))


def terminate_processes(
    processes: Mapping[str, subprocess.Popen[bytes]],
    *,
    timeout: float = SHUTDOWN_TIMEOUT_SECONDS,
) -> None:
    """Terminate every live child, then kill only children that do not stop."""

    for name, process in processes.items():
        try:
            if process.poll() is None:
                _launcher_logger.info(
                    "event=child_shutdown service=%s action=terminate",
                    _safe_service_name(name),
                )
                process.terminate()
        except OSError as exc:
            # A concurrently exiting child is already in the desired state.
            error_type, error_number, winerror = _safe_exception_fields(exc)
            _launcher_logger.warning(
                "event=child_shutdown_failed service=%s action=terminate "
                "error_type=%s errno=%d winerror=%d",
                _safe_service_name(name),
                error_type,
                error_number,
                winerror,
            )
            continue

    deadline = time.monotonic() + max(0.0, timeout)
    for name, process in processes.items():
        try:
            if process.poll() is None:
                process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except (OSError, subprocess.TimeoutExpired) as exc:
            error_type, error_number, winerror = _safe_exception_fields(exc)
            _launcher_logger.warning(
                "event=child_shutdown_incomplete service=%s action=wait "
                "error_type=%s errno=%d winerror=%d",
                _safe_service_name(name),
                error_type,
                error_number,
                winerror,
            )
            continue

    for name, process in processes.items():
        try:
            if process.poll() is None:
                _launcher_logger.warning(
                    "event=child_shutdown service=%s action=kill",
                    _safe_service_name(name),
                )
                process.kill()
        except OSError as exc:
            error_type, error_number, winerror = _safe_exception_fields(exc)
            _launcher_logger.error(
                "event=child_shutdown_failed service=%s action=kill "
                "error_type=%s errno=%d winerror=%d",
                _safe_service_name(name),
                error_type,
                error_number,
                winerror,
            )
            continue

    # Reap killed children without allowing shutdown to block indefinitely.
    for name, process in processes.items():
        try:
            if process.poll() is None:
                process.wait(timeout=1.0)
        except (OSError, subprocess.TimeoutExpired) as exc:
            error_type, error_number, winerror = _safe_exception_fields(exc)
            _launcher_logger.error(
                "event=child_shutdown_incomplete service=%s action=reap "
                "error_type=%s errno=%d winerror=%d",
                _safe_service_name(name),
                error_type,
                error_number,
                winerror,
            )
            continue

    for name, process in processes.items():
        try:
            if process.poll() is None:
                _launcher_logger.error(
                    "event=child_shutdown_incomplete service=%s "
                    "action=final_check state=still_running",
                    _safe_service_name(name),
                )
        except OSError as exc:
            error_type, error_number, winerror = _safe_exception_fields(exc)
            _launcher_logger.error(
                "event=child_shutdown_failed service=%s action=final_check "
                "error_type=%s errno=%d winerror=%d",
                _safe_service_name(name),
                error_type,
                error_number,
                winerror,
            )


def _print_banner() -> None:
    print("=====================================================================")
    print("   STARTING UP POLICE CYBER CELL OSINT SOC PLATFORM (Beta-v2)")
    print("=====================================================================")


def main() -> int:
    """Launch, verify, and supervise both Beta-v2 local servers."""

    global _launcher_run_id

    _launcher_run_id = uuid.uuid4().hex[:12]
    _last_health_failure.clear()
    log_available = configure_launcher_logging()
    _print_banner()
    if not log_available:
        print(
            "[WARN] Persistent launcher logging is unavailable; console output will continue.",
            file=sys.stderr,
        )
    else:
        log_path = _launcher_log_destination or LAUNCHER_LOG_PATH.resolve()
        print(f"[LOG] Launcher diagnostics: {log_path}")
    _launcher_logger.info(
        "event=launcher_started backend_port=%d frontend_port=%d",
        BACKEND_PORT,
        FRONTEND_PORT,
    )
    processes: dict[str, subprocess.Popen[bytes]] = {}

    blocked = find_unavailable_ports()
    if blocked:
        for name, port in blocked:
            _launcher_logger.error(
                "event=launcher_port_unavailable service=%s port=%d",
                _safe_service_name(name),
                port,
            )
            print(
                f"[ERROR] Cannot start {name}: {HOST}:{port} is already in use "
                "or could not be checked safely.",
                file=sys.stderr,
            )
        _launcher_logger.error("event=launcher_failed reason=port_unavailable")
        _launcher_logger.info("event=launcher_stopped")
        shutdown_launcher_logging()
        return 1

    try:
        print(f"\n[1/2] Launching FastAPI Backend Server on {BACKEND_URL}...")
        backend_cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            HOST,
            "--port",
            str(BACKEND_PORT),
            "--no-access-log",
        ]
        processes["backend"] = subprocess.Popen(
            backend_cmd,
            cwd=str(BACKEND_DIR),
        )
        backend_pid = processes["backend"].pid
        _launcher_logger.info(
            "event=child_started service=backend pid=%d",
            backend_pid if isinstance(backend_pid, int) else 0,
        )

        print(f"[2/2] Launching Frontend Web Server on {FRONTEND_URL}...")
        frontend_cmd = [
            sys.executable,
            "-m",
            "http.server",
            str(FRONTEND_PORT),
            "--bind",
            HOST,
        ]
        processes["frontend"] = subprocess.Popen(
            frontend_cmd,
            cwd=str(FRONTEND_DIR),
        )
        frontend_pid = processes["frontend"].pid
        _launcher_logger.info(
            "event=child_started service=frontend pid=%d",
            frontend_pid if isinstance(frontend_pid, int) else 0,
        )

        print("Waiting for bounded backend and frontend health checks...")
        wait_for_services(processes)

        print("\n=====================================================================")
        print("   BOTH SERVERS STARTED SUCCESSFULLY!")
        print(f"   Backend API:  {BACKEND_URL}")
        print(f"   Frontend UI:  {FRONTEND_URL}")
        print("   Opening browser...")
        print("   Press Ctrl+C to terminate both servers.")
        print("=====================================================================\n")

        try:
            if not webbrowser.open(FRONTEND_URL):
                _launcher_logger.warning(
                    "event=browser_open_failed reason=returned_false"
                )
                print(f"[WARN] Browser did not open automatically. Visit {FRONTEND_URL}.")
            else:
                _launcher_logger.info("event=browser_open_succeeded")
        except (OSError, webbrowser.Error) as exc:
            _launcher_logger.warning(
                "event=browser_open_failed reason=exception error_type=%s",
                type(exc).__name__,
            )
            print(f"[WARN] Browser did not open automatically. Visit {FRONTEND_URL}.")

        monitor_processes(processes)
        return 0
    except KeyboardInterrupt:
        _launcher_logger.info("event=shutdown_requested reason=keyboard_interrupt")
        print("\nShutdown requested. Stopping Beta-v2 servers...")
        return 130
    except LauncherError as exc:
        _launcher_logger.error(
            "event=launcher_failed reason=service_supervision error_type=%s",
            type(exc).__name__,
        )
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        if "backend" in str(exc).casefold():
            print(
                "[HINT] Set distinct AUTH_SESSION_SECRET and AUDIT_HMAC_KEY values "
                "in backend/.env and provision an active SOC investigator; see README.md.",
                file=sys.stderr,
            )
        return 1
    except OSError as exc:
        reason, error_number, winerror = _os_error_fields(exc)
        _launcher_logger.error(
            "event=launcher_failed reason=process_launch_%s errno=%d winerror=%d",
            reason,
            error_number,
            winerror,
        )
        print("\n[ERROR] A server process could not be launched.", file=sys.stderr)
        return 1
    finally:
        if processes:
            terminate_processes(processes)
        _launcher_logger.info("event=launcher_stopped")
        shutdown_launcher_logging()


if __name__ == "__main__":
    raise SystemExit(main())

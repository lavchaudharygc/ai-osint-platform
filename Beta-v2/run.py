"""Reliable local launcher for the Beta-v2 backend and frontend.

The launcher performs read-only port probes before starting either child,
waits for bounded HTTP health checks, and keeps supervising both processes.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence


BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"

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
    except OSError:
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
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.getcode() != 200:
                return False
            if target.expected_json_status is None:
                return True
            payload = json.loads(response.read(4097))
            return (
                isinstance(payload, dict)
                and payload.get("status") == target.expected_json_status
            )
    except (OSError, ValueError, urllib.error.URLError):
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
    deadline = time.monotonic() + max(0.0, timeout)

    while pending:
        for name, process in processes.items():
            exit_code = process.poll()
            if exit_code is not None:
                raise LauncherError(
                    f"{name.capitalize()} server exited during startup "
                    f"(exit code {exit_code})."
                )

        for name, target in tuple(pending.items()):
            if checker(target):
                pending.pop(name)

        if not pending:
            return

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            names = ", ".join(sorted(pending))
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

    for process in processes.values():
        try:
            if process.poll() is None:
                process.terminate()
        except OSError:
            # A concurrently exiting child is already in the desired state.
            continue

    deadline = time.monotonic() + max(0.0, timeout)
    for process in processes.values():
        try:
            if process.poll() is None:
                process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except (OSError, subprocess.TimeoutExpired):
            continue

    for process in processes.values():
        try:
            if process.poll() is None:
                process.kill()
        except OSError:
            continue

    # Reap killed children without allowing shutdown to block indefinitely.
    for process in processes.values():
        try:
            if process.poll() is None:
                process.wait(timeout=1.0)
        except (OSError, subprocess.TimeoutExpired):
            continue


def _print_banner() -> None:
    print("=====================================================================")
    print("   STARTING UP POLICE CYBER CELL OSINT SOC PLATFORM (Beta-v2)")
    print("=====================================================================")


def main() -> int:
    """Launch, verify, and supervise both Beta-v2 local servers."""

    _print_banner()
    processes: dict[str, subprocess.Popen[bytes]] = {}

    blocked = find_unavailable_ports()
    if blocked:
        for name, port in blocked:
            print(
                f"[ERROR] Cannot start {name}: {HOST}:{port} is already in use "
                "or could not be checked safely.",
                file=sys.stderr,
            )
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
                print(f"[WARN] Browser did not open automatically. Visit {FRONTEND_URL}.")
        except (OSError, webbrowser.Error):
            print(f"[WARN] Browser did not open automatically. Visit {FRONTEND_URL}.")

        monitor_processes(processes)
        return 0
    except KeyboardInterrupt:
        print("\nShutdown requested. Stopping Beta-v2 servers...")
        return 130
    except LauncherError as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        if "backend" in str(exc).casefold():
            print(
                "[HINT] Set distinct AUTH_SESSION_SECRET and AUDIT_HMAC_KEY values "
                "in backend/.env and provision an active SOC investigator; see README.md.",
                file=sys.stderr,
            )
        return 1
    except OSError:
        print("\n[ERROR] A server process could not be launched.", file=sys.stderr)
        return 1
    finally:
        if processes:
            terminate_processes(processes)


if __name__ == "__main__":
    raise SystemExit(main())

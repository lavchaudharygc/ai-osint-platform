"""Unit tests for the Beta-v2 launcher without starting real processes."""

from __future__ import annotations

from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

import run


class PortPreflightTests(unittest.TestCase):
    @patch("run.socket.socket")
    def test_port_probe_binds_then_closes_and_reports_free(
        self,
        socket_factory: MagicMock,
    ) -> None:
        probe = socket_factory.return_value.__enter__.return_value

        self.assertTrue(run.port_is_free(run.HOST, run.BACKEND_PORT))
        probe.bind.assert_called_once_with((run.HOST, run.BACKEND_PORT))
        probe.connect_ex.assert_not_called()

    @patch("run.socket.socket")
    def test_listening_port_is_not_free(self, socket_factory: MagicMock) -> None:
        probe = socket_factory.return_value.__enter__.return_value
        probe.bind.side_effect = OSError("address already in use")

        self.assertFalse(run.port_is_free(run.HOST, run.FRONTEND_PORT))

    @patch("run.socket.socket")
    def test_ambiguous_probe_error_is_not_treated_as_free(self, socket_factory: MagicMock) -> None:
        probe = socket_factory.return_value.__enter__.return_value
        probe.bind.side_effect = OSError("permission denied")

        self.assertFalse(run.port_is_free(run.HOST, run.FRONTEND_PORT))


class HealthAndMonitorTests(unittest.TestCase):
    @patch("run.urllib.request.urlopen")
    def test_backend_readiness_requires_explicit_ready_payload(self, urlopen: MagicMock) -> None:
        response = urlopen.return_value.__enter__.return_value
        response.getcode.return_value = 200
        response.read.return_value = b'{"status":"ready"}'

        self.assertTrue(run.http_is_healthy(run.HEALTH_TARGETS[0], timeout=0.1))
        urlopen.assert_called_once()
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 0.1)

        response.read.return_value = b'{"status":"not_ready"}'
        self.assertFalse(run.http_is_healthy(run.HEALTH_TARGETS[0], timeout=0.1))

    @patch("run.urllib.request.urlopen")
    def test_backend_readiness_rejects_malformed_json(self, urlopen: MagicMock) -> None:
        response = urlopen.return_value.__enter__.return_value
        response.getcode.return_value = 200
        response.read.return_value = b'{"status":'

        self.assertFalse(run.http_is_healthy(run.HEALTH_TARGETS[0], timeout=0.1))

    @patch("run.urllib.request.urlopen")
    def test_wrapped_socket_timeout_is_classified_as_timeout(
        self,
        urlopen: MagicMock,
    ) -> None:
        urlopen.side_effect = urllib.error.URLError(
            socket.timeout("HEALTH-TIMEOUT-SENTINEL")
        )

        self.assertFalse(run.http_is_healthy(run.HEALTH_TARGETS[0], timeout=0.1))
        self.assertEqual(run._last_health_failure["backend"], ("timeout", 0))

    def test_wait_requires_both_services(self) -> None:
        processes = {"backend": MagicMock(), "frontend": MagicMock()}
        for process in processes.values():
            process.poll.return_value = None
        checked: list[str] = []

        def healthy(target: run.HealthTarget) -> bool:
            checked.append(target.name)
            return True

        run.wait_for_services(
            processes,
            timeout=0.1,
            poll_interval=0.0,
            healthcheck=healthy,
        )

        self.assertCountEqual(checked, ["backend", "frontend"])

    def test_startup_fails_immediately_when_either_child_exits(self) -> None:
        backend = MagicMock()
        frontend = MagicMock()
        backend.poll.return_value = None
        frontend.poll.return_value = 7

        with self.assertRaisesRegex(run.LauncherError, "Frontend.*exit code 7"):
            run.wait_for_services(
                {"backend": backend, "frontend": frontend},
                timeout=1.0,
                healthcheck=lambda _target: False,
            )

    def test_health_wait_is_bounded(self) -> None:
        processes = {"backend": MagicMock(), "frontend": MagicMock()}
        for process in processes.values():
            process.poll.return_value = None

        with self.assertRaisesRegex(run.LauncherError, "Timed out"):
            run.wait_for_services(
                processes,
                timeout=0.0,
                healthcheck=lambda _target: False,
            )

    @patch("run.time.sleep")
    def test_monitor_detects_frontend_exit(self, _sleep: MagicMock) -> None:
        backend = MagicMock()
        frontend = MagicMock()
        backend.poll.return_value = None
        frontend.poll.return_value = 3

        with self.assertRaisesRegex(run.LauncherError, "Frontend.*exit code 3"):
            run.monitor_processes({"backend": backend, "frontend": frontend})


class ShutdownTests(unittest.TestCase):
    def test_shutdown_terminates_all_and_kills_stragglers(self) -> None:
        processes = {"backend": MagicMock(), "frontend": MagicMock()}
        for process in processes.values():
            process.poll.return_value = None
            process.wait.side_effect = subprocess.TimeoutExpired("server", 0)

        run.terminate_processes(processes, timeout=0.0)

        for process in processes.values():
            process.terminate.assert_called_once_with()
            process.kill.assert_called_once_with()


class MainFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        # These are control-flow tests, so keep them entirely away from the
        # developer's real backend/runtime/launcher.log file.
        run.shutdown_launcher_logging()
        logging_patch = patch("run.configure_launcher_logging", return_value=False)
        logging_patch.start()
        self.addCleanup(logging_patch.stop)

    @patch("run.webbrowser.open")
    @patch("run.subprocess.Popen")
    @patch("run.find_unavailable_ports", return_value=[("frontend", run.FRONTEND_PORT)])
    def test_busy_port_starts_nothing(
        self,
        _ports: MagicMock,
        popen: MagicMock,
        browser: MagicMock,
    ) -> None:
        self.assertEqual(run.main(), 1)
        popen.assert_not_called()
        browser.assert_not_called()

    @patch("run.terminate_processes")
    @patch("run.monitor_processes")
    @patch("run.webbrowser.open", return_value=True)
    @patch("run.wait_for_services")
    @patch("run.subprocess.Popen")
    @patch("run.find_unavailable_ports", return_value=[])
    def test_browser_opens_only_after_both_health_checks(
        self,
        _ports: MagicMock,
        popen: MagicMock,
        wait_for_services: MagicMock,
        browser: MagicMock,
        monitor: MagicMock,
        terminate: MagicMock,
    ) -> None:
        backend = MagicMock()
        frontend = MagicMock()
        popen.side_effect = [backend, frontend]
        events: list[str] = []
        wait_for_services.side_effect = lambda _processes: events.append("healthy")
        browser.side_effect = lambda _url: events.append("browser") or True

        def interrupt_after_monitoring(_processes: object) -> None:
            events.append("monitor")
            raise KeyboardInterrupt

        monitor.side_effect = interrupt_after_monitoring

        self.assertEqual(run.main(), 130)

        self.assertEqual(events, ["healthy", "browser", "monitor"])
        terminate.assert_called_once()
        self.assertEqual(set(terminate.call_args.args[0]), {"backend", "frontend"})
        backend_command = popen.call_args_list[0].args[0]
        frontend_command = popen.call_args_list[1].args[0]
        self.assertNotIn("--reload", backend_command)
        self.assertIn("--no-access-log", backend_command)
        self.assertEqual(backend_command[backend_command.index("--host") + 1], run.HOST)
        self.assertEqual(frontend_command[frontend_command.index("--bind") + 1], run.HOST)

    @patch("run.terminate_processes")
    @patch("run.webbrowser.open")
    @patch("run.wait_for_services", side_effect=run.LauncherError("health failed"))
    @patch("run.subprocess.Popen")
    @patch("run.find_unavailable_ports", return_value=[])
    def test_health_failure_cleans_up_without_opening_browser(
        self,
        _ports: MagicMock,
        popen: MagicMock,
        _wait: MagicMock,
        browser: MagicMock,
        terminate: MagicMock,
    ) -> None:
        popen.side_effect = [MagicMock(), MagicMock()]

        self.assertEqual(run.main(), 1)

        browser.assert_not_called()
        terminate.assert_called_once()
        self.assertEqual(set(terminate.call_args.args[0]), {"backend", "frontend"})

    @patch("run.terminate_processes")
    @patch("run.subprocess.Popen")
    @patch("run.find_unavailable_ports", return_value=[])
    def test_partial_launch_failure_still_cleans_up_started_child(
        self,
        _ports: MagicMock,
        popen: MagicMock,
        terminate: MagicMock,
    ) -> None:
        backend = MagicMock()
        popen.side_effect = [backend, OSError("frontend launch failed")]

        self.assertEqual(run.main(), 1)

        terminate.assert_called_once_with({"backend": backend})


class AlternateLauncherTests(unittest.TestCase):
    def test_alternate_launchers_delegate_to_verified_launcher(self) -> None:
        for filename in ("start.ps1", "start.bat", "start.sh"):
            content = (Path(run.BASE_DIR) / filename).read_text(encoding="utf-8").casefold()
            with self.subTest(filename=filename):
                self.assertEqual(content.count("run.py"), 1)
                self.assertNotIn("uvicorn", content)
                self.assertNotIn("http.server", content)
                self.assertNotIn("--reload", content)
                self.assertNotIn("start-process", content)
                self.assertNotIn("sleep ", content)


class LauncherLoggingTests(unittest.TestCase):
    def tearDown(self) -> None:
        run.shutdown_launcher_logging()

    def test_configure_opens_destination_eagerly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "launcher.log"

            self.assertTrue(run.configure_launcher_logging(log_path))
            self.assertTrue(log_path.is_file())
            run.shutdown_launcher_logging()

    def test_log_path_that_is_a_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "not-a-file"
            log_path.mkdir()

            self.assertFalse(run.configure_launcher_logging(log_path))
            self.assertIsNone(run._launcher_handler)

    @patch("run.socket.socket")
    def test_port_probe_log_does_not_store_os_error_text(
        self,
        socket_factory: MagicMock,
    ) -> None:
        probe = socket_factory.return_value.__enter__.return_value
        probe.bind.side_effect = OSError(10048, "PORT-ERROR-SENTINEL")
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "launcher.log"
            self.assertTrue(run.configure_launcher_logging(log_path))
            self.assertFalse(run.port_is_free(run.HOST, run.BACKEND_PORT))
            run.shutdown_launcher_logging()
            content = log_path.read_text(encoding="utf-8")

        self.assertIn("event=port_probe_failed", content)
        self.assertIn("reason=address_in_use", content)
        self.assertNotIn("PORT-ERROR-SENTINEL", content)

    @patch("run.find_unavailable_ports", return_value=[("backend", run.BACKEND_PORT)])
    def test_blocked_port_is_persisted(self, _ports: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "launcher.log"
            with patch.object(run, "LAUNCHER_LOG_PATH", log_path):
                self.assertEqual(run.main(), 1)
            content = log_path.read_text(encoding="utf-8")

        self.assertIn("event=launcher_port_unavailable service=backend port=8010", content)
        self.assertIn("event=launcher_failed reason=port_unavailable", content)

    @patch("run.find_unavailable_ports", return_value=[("backend", run.BACKEND_PORT)])
    @patch("builtins.print")
    def test_main_prints_absolute_active_log_path(
        self,
        output: MagicMock,
        _ports: MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "diagnostics" / "launcher.log"
            with patch.object(run, "LAUNCHER_LOG_PATH", log_path):
                self.assertEqual(run.main(), 1)

            expected = f"[LOG] Launcher diagnostics: {log_path.resolve()}"
            self.assertTrue(
                any(call.args == (expected,) for call in output.call_args_list),
                output.call_args_list,
            )

    def test_shutdown_failures_are_safe_and_report_still_running_child(self) -> None:
        process = MagicMock()
        process.poll.return_value = None
        process.terminate.side_effect = OSError(5, "TERMINATE-ERROR-SENTINEL")
        process.wait.side_effect = [
            subprocess.TimeoutExpired("WAIT-COMMAND-SENTINEL", 0),
            OSError(6, "REAP-ERROR-SENTINEL"),
        ]
        process.kill.side_effect = OSError(13, "KILL-ERROR-SENTINEL")

        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "launcher.log"
            self.assertTrue(run.configure_launcher_logging(log_path))
            run.terminate_processes({"backend": process}, timeout=0.0)
            run.shutdown_launcher_logging()
            content = log_path.read_text(encoding="utf-8")

        self.assertIn(
            "event=child_shutdown_failed service=backend action=terminate "
            "error_type=OSError errno=5 winerror=0",
            content,
        )
        self.assertIn(
            "event=child_shutdown_incomplete service=backend action=wait "
            "error_type=TimeoutExpired errno=0 winerror=0",
            content,
        )
        self.assertIn(
            "event=child_shutdown_failed service=backend action=kill "
            "error_type=PermissionError errno=13 winerror=0",
            content,
        )
        self.assertIn("action=final_check state=still_running", content)
        self.assertNotIn("SENTINEL", content)


if __name__ == "__main__":
    unittest.main()

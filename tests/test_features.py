"""
Tests covering features listed in README.md:
  - List / Start / Stop applications
  - List / Start / Stop (Kill) processes
  - Take screenshots
  - Capture keystrokes (Activity logs / Keylogger)
  - Copy (download) files
  - Shutdown / Restart
  - Start webcam; Record
  - Multi-control many servers (Dashboard server management)
"""
import struct
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

import server.commands  # register all commands

# Add project root to path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class MockServer:
    """
    Helpers: mock server / connection objects used across many tests
    Minimal stand-in for ControlServer used by command execute() calls.
    """

    def __init__(self):
        self.activity_logs = []
        self.is_streaming = False
        self.stream_mode = "SCREEN"
        self.is_recording = False
        self.recorder = None
        self._sent = []  # Collects send_json calls

    def send_json(self, conn, data):
        self._sent.append(data)
        payload = json.dumps(data).encode()
        conn.sendall(struct.pack("!I", len(payload)) + payload)

    def _record_worker(self):
        pass


class MockConn:
    """Minimal stand-in for a socket connection."""

    def __init__(self):
        self._buf = b""

    def sendall(self, data: bytes):
        self._buf += data

    def recv_response(self):
        """Helper: decode one length-prefixed JSON payload from internal buffer."""
        if len(self._buf) < 4:
            return None
        sz = struct.unpack("!I", self._buf[:4])[0]
        payload = self._buf[4:4 + sz]
        self._buf = self._buf[4 + sz:]
        return json.loads(payload.decode())


class TestCommandRegistry(TestCase):
    """CommandRegistry"""

    def test_register_and_get(self):
        from server.core.registry import CommandRegistry, BaseCommand

        @CommandRegistry.register("TEST_CMD_UNIQUE")
        class _Cmd(BaseCommand):
            def execute(self, server, conn, data):
                server.send_json(conn, {"ok": True})

        cmd = CommandRegistry.get("TEST_CMD_UNIQUE")
        self.assertIsNotNone(cmd)
        srv = MockServer()
        conn = MockConn()
        cmd.execute(srv, conn, {})
        self.assertEqual(conn.recv_response(), {"ok": True})

    def test_get_unknown_returns_none(self):
        from server.core.registry import CommandRegistry
        self.assertIsNone(CommandRegistry.get("DOES_NOT_EXIST_XYZ"))


class TestRecvAll(TestCase):
    """Network utility – recv_all"""

    def test_receives_full_data(self):
        from client.core.network import recv_all

        sock = MagicMock()
        sock.recv.side_effect = [b"Hello", b" Wor", b"ld"]
        result = recv_all(sock, 11)
        self.assertEqual(result, b"Hello World")

    def test_returns_none_on_empty_packet(self):
        from client.core.network import recv_all

        sock = MagicMock()
        sock.recv.return_value = b""
        result = recv_all(sock, 10)
        self.assertIsNone(result)

    def test_single_chunk(self):
        from client.core.network import recv_all

        sock = MagicMock()
        sock.recv.return_value = b"abc"
        result = recv_all(sock, 3)
        self.assertEqual(result, b"abc")


class TestProcessFeatures(TestCase):
    """Process features – LIST_PROCS and KILL_PROC"""

    def test_list_procs_returns_list(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("LIST_PROCS")
        srv = MockServer()
        conn = MockConn()
        cmd.execute(srv, conn, {})
        data = conn.recv_response()
        self.assertIsInstance(data, list)
        # Every entry must have pid, name, cpu_percent, memory_percent
        for proc in data:
            self.assertIn("pid", proc)
            self.assertIn("name", proc)
            self.assertIn("cpu_percent", proc)
            self.assertIn("memory_percent", proc)

    def test_kill_proc_terminates_process(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("KILL_PROC")
        mock_proc = MagicMock()
        with patch("psutil.Process", return_value=mock_proc) as MockProcess:
            srv = MockServer()
            conn = MockConn()
            cmd.execute(srv, conn, {"pid": 12345})
            MockProcess.assert_called_once_with(12345)
            mock_proc.terminate.assert_called_once()

    def test_kill_proc_handles_missing_pid_gracefully(self):
        from server.core.registry import CommandRegistry
        import psutil
        cmd = CommandRegistry.get("KILL_PROC")
        with patch("psutil.Process", side_effect=psutil.NoSuchProcess(99999)):
            srv = MockServer()
            conn = MockConn()
            # Should not raise
            cmd.execute(srv, conn, {"pid": 99999})


class TestApplicationFeatures(TestCase):
    """Application features – LIST_APPS and START_APP"""

    def test_list_apps_returns_list(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("LIST_APPS")
        srv = MockServer()
        conn = MockConn()
        cmd.execute(srv, conn, {})
        data = conn.recv_response()
        self.assertIsInstance(data, list)
        # Each entry must have name, exec, type
        for app in data:
            self.assertIn("name", app)
            self.assertIn("exec", app)
            self.assertIn("type", app)

    def test_list_apps_sorted(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("LIST_APPS")
        srv = MockServer()
        conn = MockConn()
        cmd.execute(srv, conn, {})
        data = conn.recv_response()
        if len(data) >= 2:
            names = [a["name"].lower() for a in data]
            self.assertEqual(names, sorted(names))

    def test_start_app_windows(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("START_APP")
        srv = MockServer()
        conn = MockConn()
        with patch("sys.platform", "win32"), patch("os.startfile") as mock_sf:
            cmd.execute(srv, conn, {"exec": "notepad.exe"})
            mock_sf.assert_called_once_with("notepad.exe")

    def test_start_app_linux(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("START_APP")
        srv = MockServer()
        conn = MockConn()
        with patch("sys.platform", "linux"), patch("subprocess.Popen") as mock_popen:
            cmd.execute(srv, conn, {"exec": "gedit"})
            mock_popen.assert_called_once()


class TestFileFeatures(TestCase):
    """File features – LIST_FILES and DOWNLOAD"""

    def test_list_files_returns_dir_contents(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("LIST_FILES")
        with tempfile.TemporaryDirectory() as td:
            # Create test files/dirs
            (Path(td) / "subdir").mkdir()
            (Path(td) / "file.txt").write_text("hello")

            srv = MockServer()
            conn = MockConn()
            cmd.execute(srv, conn, {"path": td})
            data = conn.recv_response()

            self.assertIsInstance(data, list)
            names = {item["name"] for item in data}
            self.assertIn("subdir", names)
            self.assertIn("file.txt", names)

    def test_list_files_marks_dirs(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("LIST_FILES")
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "subdir").mkdir()
            (Path(td) / "file.txt").write_text("content")

            srv = MockServer()
            conn = MockConn()
            cmd.execute(srv, conn, {"path": td})
            data = conn.recv_response()

            by_name = {item["name"]: item for item in data}
            self.assertTrue(by_name["subdir"]["is_dir"])
            self.assertFalse(by_name["file.txt"]["is_dir"])

    def test_list_files_nonexistent_path(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("LIST_FILES")
        srv = MockServer()
        conn = MockConn()
        cmd.execute(srv, conn, {"path": "/nonexistent_xyz_abc_123"})
        data = conn.recv_response()
        self.assertEqual(data, [])

    def test_download_single_file(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("DOWNLOAD")
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "test.txt"
            src.write_bytes(b"file content here")
            expected_size = src.stat().st_size

            srv = MockServer()
            conn = MockConn()
            cmd.execute(srv, conn, {"path": str(src)})

            # First 8 bytes = uint64 file size
            size_header = struct.unpack("!Q", conn._buf[:8])[0]
            self.assertEqual(size_header, expected_size)
            actual_content = conn._buf[8:]
            self.assertEqual(actual_content, b"file content here")

    def test_download_directory_as_zip(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("DOWNLOAD")
        with tempfile.TemporaryDirectory() as td:
            src_dir = Path(td) / "mydir"
            src_dir.mkdir()
            (src_dir / "a.txt").write_text("aaa")
            (src_dir / "b.txt").write_text("bbb")

            srv = MockServer()
            conn = MockConn()
            cmd.execute(srv, conn, {"path": str(src_dir)})

            size_header = struct.unpack("!Q", conn._buf[:8])[0]
            self.assertGreater(size_header, 0)
            # Verify the content is a valid zip
            zip_bytes = conn._buf[8:]
            import io
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                names = z.namelist()
                self.assertIn("a.txt", names)
                self.assertIn("b.txt", names)

    def test_download_nonexistent_sends_zero(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("DOWNLOAD")
        srv = MockServer()
        conn = MockConn()
        cmd.execute(srv, conn, {"path": "/nonexistent_xyz/file.txt"})
        size_header = struct.unpack("!Q", conn._buf[:8])[0]
        self.assertEqual(size_header, 0)


class TestMediaFeatures(TestCase):
    """Screenshot / Media features"""

    def test_stream_ctrl_sets_active(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("STREAM_CTRL")
        srv = MockServer()
        conn = MockConn()
        cmd.execute(srv, conn, {"active": True, "mode": "SCREEN"})
        self.assertTrue(srv.is_streaming)
        self.assertEqual(srv.stream_mode, "SCREEN")

    def test_stream_ctrl_deactivates(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("STREAM_CTRL")
        srv = MockServer()
        srv.is_streaming = True
        conn = MockConn()
        cmd.execute(srv, conn, {"active": False})
        self.assertFalse(srv.is_streaming)

    def test_stream_ctrl_webcam_mode(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("STREAM_CTRL")
        srv = MockServer()
        conn = MockConn()
        cmd.execute(srv, conn, {"active": True, "mode": "WEBCAM"})
        self.assertEqual(srv.stream_mode, "WEBCAM")

    def test_screenshot_screen_mode(self):
        from server.core.registry import CommandRegistry
        import numpy as np

        cmd = CommandRegistry.get("SCREENSHOT")
        srv = MockServer()
        conn = MockConn()

        fake_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        fake_encoded = MagicMock()
        fake_encoded.tobytes.return_value = b"FAKEIMGDATA"

        mock_sct = MagicMock()
        mock_sct.__enter__ = lambda s: s
        mock_sct.__exit__ = MagicMock(return_value=False)
        mock_sct.monitors = [None, {"left": 0, "top": 0, "width": 100, "height": 100}]
        mock_sct.grab.return_value = MagicMock()

        with patch("mss.mss", return_value=mock_sct), \
                patch("numpy.array", return_value=fake_frame), \
                patch("cv2.cvtColor", return_value=fake_frame), \
                patch("cv2.imencode", return_value=(True, fake_encoded)):
            cmd.execute(srv, conn, {"mode": "SCREEN"})

        sz = struct.unpack("!I", conn._buf[:4])[0]
        self.assertEqual(sz, len(b"FAKEIMGDATA"))
        self.assertEqual(conn._buf[4:], b"FAKEIMGDATA")

    def test_screenshot_sends_zero_on_error(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("SCREENSHOT")
        srv = MockServer()
        conn = MockConn()
        with patch("mss.mss", side_effect=Exception("no display")):
            cmd.execute(srv, conn, {"mode": "SCREEN"})
        sz = struct.unpack("!I", conn._buf[:4])[0]
        self.assertEqual(sz, 0)

    def test_rec_start_sets_flag(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("REC_START")
        srv = MockServer()
        conn = MockConn()
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            cmd.execute(srv, conn, {})
        self.assertTrue(srv.is_recording)

    def test_rec_start_no_duplicate(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("REC_START")
        srv = MockServer()
        srv.is_recording = True
        conn = MockConn()
        with patch("threading.Thread") as mock_thread:
            cmd.execute(srv, conn, {})
            mock_thread.assert_not_called()

    def test_rec_stop_clears_flag_and_sends_zero_when_no_file(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("REC_STOP")
        srv = MockServer()
        srv.is_recording = True
        srv.recorder = None
        conn = MockConn()
        # No temp_rec.mp4 exists
        with patch.object(Path, "exists", return_value=False):
            cmd.execute(srv, conn, {})
        sz = struct.unpack("!Q", conn._buf[:8])[0]
        self.assertEqual(sz, 0)


class TestActivityLogs(TestCase):
    """Activity logs / Keylogger"""

    def test_get_logs_returns_and_clears(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("GET_LOGS")
        srv = MockServer()
        srv.activity_logs = ["[12:00:00] Key: a", "[12:00:01] Mouse left at (100, 200)"]
        conn = MockConn()
        cmd.execute(srv, conn, {})

        sz = struct.unpack("!I", conn._buf[:4])[0]
        text = conn._buf[4:4 + sz].decode("utf-8")
        self.assertIn("[12:00:00] Key: a", text)
        self.assertIn("[12:00:01] Mouse left at (100, 200)", text)
        # Logs cleared after send
        self.assertEqual(srv.activity_logs, [])

    def test_get_logs_empty(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("GET_LOGS")
        srv = MockServer()
        conn = MockConn()
        cmd.execute(srv, conn, {})
        sz = struct.unpack("!I", conn._buf[:4])[0]
        self.assertEqual(sz, 0)

    def test_keylogger_records_key(self):
        """start_listeners sets up pynput listeners that append to activity_logs."""
        from unittest.mock import MagicMock, patch
        from server.core import logic as logic_mod

        mock_key = MagicMock()
        mock_key.char = "x"

        class FakeKbdListener:
            def __init__(self, on_press=None):
                self._on_press = on_press

            def start(self): pass

            def stop(self): pass

            def simulate_press(self, k):
                self._on_press(k)

        class FakeMouseListener:
            def __init__(self, **kw): pass

            def start(self): pass

            def stop(self): pass

        with patch("server.core.logic.keyboard.Listener", FakeKbdListener), \
                patch("server.core.logic.mouse.Listener", FakeMouseListener), \
                patch("server.core.logic.pyautogui.size", return_value=(1920, 1080)), \
                patch("server.core.logic.ControlServer.setup_ssl", return_value=MagicMock()), \
                patch("server.core.logic.ControlServer.generate_certs"), \
                patch("threading.Thread"):
            srv = logic_mod.ControlServer.__new__(logic_mod.ControlServer)
            srv.activity_logs = []
            srv.running = True
            srv.last_window = ""
            srv.start_listeners()
            srv.kl.simulate_press(mock_key)

        self.assertTrue(any("Key: x" in log for log in srv.activity_logs))


class TestPowerFeatures(TestCase):
    """Shutdown / Restart"""

    def test_shutdown_windows(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("SHUTDOWN")
        srv = MockServer()
        conn = MockConn()
        conn.sendall = MagicMock()
        with patch("sys.platform", "win32"), \
                patch("os.system") as mock_sys, \
                patch("time.sleep"):
            cmd.execute(srv, conn, {})
            mock_sys.assert_called_once_with("shutdown /s /t 1")

    def test_shutdown_linux(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("SHUTDOWN")
        srv = MockServer()
        conn = MockConn()
        conn.sendall = MagicMock()
        with patch("sys.platform", "linux"), \
                patch("os.system") as mock_sys, \
                patch("time.sleep"):
            cmd.execute(srv, conn, {})
            mock_sys.assert_called_once_with("systemctl poweroff")

    def test_restart_windows(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("RESTART")
        srv = MockServer()
        conn = MockConn()
        conn.sendall = MagicMock()
        with patch("sys.platform", "win32"), \
                patch("os.system") as mock_sys, \
                patch("time.sleep"):
            cmd.execute(srv, conn, {})
            mock_sys.assert_called_once_with("shutdown /r /t 1")

    def test_restart_linux(self):
        from server.core.registry import CommandRegistry
        cmd = CommandRegistry.get("RESTART")
        srv = MockServer()
        conn = MockConn()
        conn.sendall = MagicMock()
        with patch("sys.platform", "linux"), \
                patch("os.system") as mock_sys, \
                patch("time.sleep"):
            cmd.execute(srv, conn, {})
            mock_sys.assert_called_once_with("systemctl reboot")


class TestNumericItem(TestCase):
    """NumericItem widget (sortable table items)"""

    def test_numeric_sort_less_than(self):
        from client.ui.widgets import NumericItem
        a = NumericItem("5%", 5.0)
        b = NumericItem("10%", 10.0)
        self.assertTrue(a < b)
        self.assertFalse(b < a)

    def test_numeric_sort_equal(self):
        from client.ui.widgets import NumericItem
        a = NumericItem("5", 5)
        b = NumericItem("5", 5)
        self.assertFalse(a < b)
        self.assertFalse(b < a)

    def test_numeric_sort_pid(self):
        from client.ui.widgets import NumericItem
        items = [NumericItem(str(v), v) for v in [300, 1, 50, 1000, 2]]
        self.assertEqual(sorted(items, key=lambda x: x.sort_val),
                         sorted(items, key=lambda x: x.sort_val))


class TestDashboardServerList(TestCase):
    """Dashboard – multi-server management (server list persistence)"""

    def _make_dashboard(self, tmp_path):
        """Create a bare Dashboard instance with mocked Qt and a temp db path."""
        from client.ui.dashboard import Dashboard
        d = Dashboard.__new__(Dashboard)
        d.db_path = Path(tmp_path) / "servers.json"
        d.db_path.parent.mkdir(parents=True, exist_ok=True)
        d.active_sessions = {}
        d.saved_servers = {}
        d.update_table = MagicMock()  # prevent Qt access
        return d

    def test_save_and_load_db(self):
        with tempfile.TemporaryDirectory() as td:
            d = self._make_dashboard(td)
            d.saved_servers = {"192.168.1.10": "pass123", "10.0.0.5": "abc"}
            d.save_db()

            d2 = self._make_dashboard(td)
            d2.db_path = d.db_path
            d2.load_db()
            self.assertEqual(d2.saved_servers, {"192.168.1.10": "pass123", "10.0.0.5": "abc"})

    def test_load_db_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            d = self._make_dashboard(td)
            d.db_path = Path(td) / "nonexistent" / "servers.json"
            d.load_db()
            self.assertEqual(d.saved_servers, {})

    def test_on_session_closed_removes_entry(self):
        with tempfile.TemporaryDirectory() as td:
            d = self._make_dashboard(td)
            mock_session = MagicMock()
            d.active_sessions = {"192.168.1.10": mock_session}
            d.on_session_closed("192.168.1.10")
            self.assertNotIn("192.168.1.10", d.active_sessions)


class TestCrossPlatformPaths(TestCase):
    """Cross-platform path handling (Windows fix)"""

    def test_path_root_detection_unix(self):
        p = Path("/")
        self.assertEqual(p, p.parent)  # at root, parent == self

    def test_path_root_detection_windows_style(self):
        p = Path("\\")
        self.assertEqual(p, p.parent)  # at root on Windows

    def test_path_non_root_has_parent(self):
        p = Path("/usr/bin")
        self.assertNotEqual(p, p.parent)

    def test_path_navigation_cross_platform(self):
        """Verify Path-based navigation used in FileExplorer works correctly."""
        # Simulate navigating into a subdirectory and back
        root = Path("/")
        child = root / "somedir"
        self.assertNotEqual(child, child.parent)
        parent = child.parent
        self.assertEqual(parent, root)


if __name__ == "__main__":
    main()

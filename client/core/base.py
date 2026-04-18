import socket
import ssl
import struct
import json
import logging
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import pyqtSlot, QTimer, Qt
from client.core.network import recv_all

class RemoteBase:
    _is_disconnecting = False

    def __init__(self, ip, pwd, controller=None):
        super().__init__()
        self.ip, self.pwd, self.controller = ip, pwd, controller
        self.target_res = (1280, 720)
        self.cmd_s = None
        if not self.init_cmd(): raise ConnectionError(f"Connection to {ip} failed")

    @pyqtSlot()
    def handle_disconnect(self):
        if not RemoteBase._is_disconnecting:
            RemoteBase._is_disconnecting = True
            QMessageBox.warning(None, "Connection Lost", f"Lost connection to server {self.ip}. Closing session.")
            if self.controller: self.controller.close_all_session()
            else: self.close()
            QTimer.singleShot(2000, lambda: setattr(RemoteBase, '_is_disconnecting', False))

    def init_cmd(self):
        try:
            logging.info(f"Connecting to Server {self.ip} on port 9999...")
            raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw.settimeout(10)
            raw.connect((self.ip, 9999))
            ctx = ssl._create_unverified_context()
            ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
            self.cmd_s = ctx.wrap_socket(raw, server_hostname=self.ip)
            self.cmd_s.sendall(self.pwd.encode())
            h = recv_all(self.cmd_s, 4)
            if not h: 
                logging.error("Failed to receive auth response header.")
                return False
            sz = struct.unpack("!I", h)[0]
            data = json.loads(recv_all(self.cmd_s, sz).decode())
            if data.get('status') == "OK":
                self.target_res = (data['w'], data['h'])
                logging.info(f"Auth Success! Native Resolution: {self.target_res}")
                return True
            logging.error(f"Auth Denied: {data.get('msg')}")
            return False
        except socket.timeout:
            logging.error("Connection Timeout!")
            QMessageBox.critical(None, "Timeout", "Connection timed out. Please check server status."); return False
        except Exception as e:
            logging.error(f"Init Connection Error: {e}"); return False

    def send_safe_cmd(self, data):
        try:
            p = json.dumps(data).encode('utf-8')
            self.cmd_s.sendall(struct.pack("!I", len(p)) + p)
            logging.info(f"Command Sent: {data['type']}")
            return True
        except Exception as e:
            logging.error(f"Failed to send command {data.get('type')}: {e}")
            self.handle_disconnect(); return False

    def recv_json(self):
        try:
            h = recv_all(self.cmd_s, 4)
            if not h: return None
            sz = struct.unpack("!I", h)[0]
            data = recv_all(self.cmd_s, sz)
            res = json.loads(data.decode()) if data else None
            if res: logging.info(f"Response Received: {len(data)} bytes")
            return res
        except socket.timeout:
            logging.error("Server response timeout.")
            # We don't have 'self' as a QWidget here necessarily, but it's usually used in QMainWindow subclasses
            # QMessageBox.warning(self, "Timeout", "Server response timed out.") 
            return None
        except Exception as e:
            logging.error(f"Receive Error: {e}")
            self.handle_disconnect(); return None

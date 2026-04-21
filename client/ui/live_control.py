import socket
import ssl
import struct
import cv2
import threading
import numpy as np
from PyQt5.QtWidgets import QLabel, QMainWindow, QMessageBox, QApplication
from PyQt5.QtCore import Qt, QMetaObject, Q_ARG, pyqtSlot
from PyQt5.QtGui import QImage, QPixmap, QKeyEvent
from client.core.base import RemoteBase
from client.core.network import recv_all

class LiveControl(RemoteBase, QMainWindow):
    def __init__(self, ip, pwd, controller=None):
        super().__init__(ip, pwd, controller)
        self.setWindowTitle(f"Live Control - {ip}"); self.resize(1000, 750)
        self.view = QLabel("Loading Stream..."); self.view.setAlignment(Qt.AlignCenter)
        self.view.setStyleSheet("background: black;"); self.setCentralWidget(self.view)
        
        # Enable keyboard focus
        self.setFocusPolicy(Qt.StrongFocus)
        
        self.send_safe_cmd({"type": "STREAM_CTRL", "active": True, "mode": "SCREEN"})
        self.active = True
        threading.Thread(target=self.stream_loop, daemon=True).start()

    def stream_loop(self):
        try:
            raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw.connect((self.ip, 9998))
            ctx = ssl._create_unverified_context()
            ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
            s = ctx.wrap_socket(raw, server_hostname=self.ip)
            while self.active:
                h = recv_all(s, 4)
                if not h: break
                sz = struct.unpack("!I", h)[0]
                b = recv_all(s, sz)
                if not b: break
                img = cv2.imdecode(np.frombuffer(b, np.uint8), 1)
                if img is not None:
                    qi = QImage(img.data, img.shape[1], img.shape[0], img.shape[1]*3, QImage.Format_RGB888).rgbSwapped()
                    pix = QPixmap.fromImage(qi).scaled(self.view.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    QMetaObject.invokeMethod(self.view, "setPixmap", Qt.QueuedConnection, Q_ARG(QPixmap, pix))
            s.close()
        except: pass
        finally:
            if self.active: QMetaObject.invokeMethod(self, "handle_disconnect", Qt.QueuedConnection)

    def mousePressEvent(self, ev):
        p = self.view.mapFromParent(ev.pos())
        if self.view.rect().contains(p) and self.view.pixmap():
            pm = self.view.pixmap()
            ox, oy = (self.view.width()-pm.width())/2, (self.view.height()-pm.height())/2
            rx, ry = p.x()-ox, p.y()-oy
            if 0 <= rx <= pm.width() and 0 <= ry <= pm.height():
                fx, fy = int(rx * self.target_res[0]/pm.width()), int(ry * self.target_res[1]/pm.height())
                self.send_safe_cmd({"type": "MOUSE", "x": fx, "y": fy, "btn": "right" if ev.button()==Qt.RightButton else "left"})

    def keyPressEvent(self, ev: QKeyEvent):
        """Capture key presses and send to server."""
        key_map = {
            Qt.Key_Return: "enter", Qt.Key_Enter: "enter", Qt.Key_Backspace: "backspace",
            Qt.Key_Escape: "esc", Qt.Key_Tab: "tab", Qt.Key_Delete: "delete",
            Qt.Key_Left: "left", Qt.Key_Right: "right", Qt.Key_Up: "up", Qt.Key_Down: "down",
            Qt.Key_PageUp: "pageup", Qt.Key_PageDown: "pagedown", Qt.Key_Home: "home", Qt.Key_End: "end",
            Qt.Key_F1: "f1", Qt.Key_F2: "f2", Qt.Key_F3: "f3", Qt.Key_F4: "f4", Qt.Key_F5: "f5",
            Qt.Key_F6: "f6", Qt.Key_F7: "f7", Qt.Key_F8: "f8", Qt.Key_F9: "f9", Qt.Key_F10: "f10",
            Qt.Key_F11: "f11", Qt.Key_F12: "f12", Qt.Key_Space: "space",
        }
        
        key_text = ev.text()
        if ev.key() in key_map:
            key_to_send = key_map[ev.key()]
        elif key_text:
            key_to_send = key_text
        else:
            return # Ignore unmapped keys without text (like Shift, Ctrl by themselves)

        self.send_safe_cmd({"type": "KEY", "key": key_to_send})

    def closeEvent(self, ev):
        self.active = False; self.send_safe_cmd({"type": "STREAM_CTRL", "active": False}); super().closeEvent(ev)

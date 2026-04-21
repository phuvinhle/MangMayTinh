import socket
import ssl
import struct
import cv2
import threading
import numpy as np
from PyQt5.QtWidgets import QLabel, QMainWindow, QMessageBox, QApplication
from PyQt5.QtCore import Qt, QMetaObject, Q_ARG, pyqtSlot
from PyQt5.QtGui import QImage, QPixmap, QKeyEvent, QMouseEvent
from client.core.base import RemoteBase
from client.core.network import recv_all

class LiveControl(RemoteBase, QMainWindow):
    def __init__(self, ip, pwd, controller=None):
        super().__init__(ip, pwd, controller)
        self.setWindowTitle(f"Live Control - {ip}"); self.resize(1000, 750)
        self.view = QLabel("Loading Stream..."); self.view.setAlignment(Qt.AlignCenter)
        self.view.setStyleSheet("background: black;"); self.setCentralWidget(self.view)
        
        # Enable tracking
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.view.setMouseTracking(True)
        
        self.send_safe_cmd({"type": "STREAM_CTRL", "active": True, "mode": "SCREEN"})
        self.active = True
        threading.Thread(target=self.stream_loop, daemon=True).start()

    def stream_loop(self):
        try:
            raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw.connect((self.ip, 9998))
            ctx = ssl._create_unverified_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
            s = ctx.wrap_socket(raw, server_hostname=self.ip)
            while self.active:
                h = recv_all(s, 4)
                if not h: break
                sz = struct.unpack("!I", h)[0]; b = recv_all(s, sz)
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

    def _get_coords(self, ev_pos):
        if not self.view.pixmap(): return None
        p = self.view.mapFrom(self, ev_pos)
        pm = self.view.pixmap()
        ox = (self.view.width() - pm.width()) / 2
        oy = (self.view.height() - pm.height()) / 2
        rx, ry = p.x() - ox, p.y() - oy
        if 0 <= rx <= pm.width() and 0 <= ry <= pm.height():
            fx = int(rx * self.target_res[0] / pm.width())
            fy = int(ry * self.target_res[1] / pm.height())
            return fx, fy
        return None

    def mousePressEvent(self, ev):
        coords = self._get_coords(ev.pos())
        if coords:
            btn = "right" if ev.button() == Qt.RightButton else "left"
            self.send_safe_cmd({"type": "MOUSE", "action": "down", "x": coords[0], "y": coords[1], "btn": btn})

    def mouseReleaseEvent(self, ev):
        coords = self._get_coords(ev.pos())
        if coords:
            btn = "right" if ev.button() == Qt.RightButton else "left"
            self.send_safe_cmd({"type": "MOUSE", "action": "up", "x": coords[0], "y": coords[1], "btn": btn})

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.LeftButton or ev.buttons() & Qt.RightButton: # While dragging
            coords = self._get_coords(ev.pos())
            if coords:
                self.send_safe_cmd({"type": "MOUSE", "action": "move", "x": coords[0], "y": coords[1]})

    def keyPressEvent(self, ev: QKeyEvent):
        modifiers = []
        if ev.modifiers() & Qt.ControlModifier: modifiers.append("ctrl")
        if ev.modifiers() & Qt.ShiftModifier: modifiers.append("shift")
        if ev.modifiers() & Qt.AltModifier: modifiers.append("alt")
        
        key_map = {
            Qt.Key_Return: "enter", Qt.Key_Enter: "enter", Qt.Key_Backspace: "backspace",
            Qt.Key_Escape: "esc", Qt.Key_Tab: "tab", Qt.Key_Delete: "delete",
            Qt.Key_Left: "left", Qt.Key_Right: "right", Qt.Key_Up: "up", Qt.Key_Down: "down",
            Qt.Key_PageUp: "pageup", Qt.Key_PageDown: "pagedown", Qt.Key_Home: "home", Qt.Key_End: "end",
            Qt.Key_Space: "space",
        }
        
        k = key_map.get(ev.key(), ev.text())
        if not k: return
        
        if modifiers:
            # For combinations like Ctrl+C
            full_key = "+".join(modifiers + [k.lower()])
            self.send_safe_cmd({"type": "KEY", "key": full_key})
        else:
            self.send_safe_cmd({"type": "KEY", "key": k})

    def closeEvent(self, ev):
        self.active = False; self.send_safe_cmd({"type": "STREAM_CTRL", "active": False}); super().closeEvent(ev)

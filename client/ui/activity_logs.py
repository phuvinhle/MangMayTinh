import struct
from PyQt5.QtWidgets import *
from PyQt5.QtCore import QTimer, Qt
from client.core.base import RemoteBase
from client.core.network import recv_all

class ActivityLogs(RemoteBase, QMainWindow):
    def __init__(self, ip, pwd, controller=None):
        super().__init__(ip, pwd, controller)
        self.setWindowTitle(f"Activity Logs - {ip}"); self.resize(500, 400)
        wid = QWidget(); self.setCentralWidget(wid); layout = QVBoxLayout(wid)
        self.logs_area = QTextEdit(); self.logs_area.setReadOnly(True); layout.addWidget(self.logs_area)
        btns = QHBoxLayout(); b1 = QPushButton("CLEAR LOGS"); b1.clicked.connect(self.logs_area.clear)
        b2 = QPushButton("SAVE AS TXT"); b2.clicked.connect(self.save_logs)
        btns.addWidget(b1); btns.addWidget(b2); layout.addLayout(btns)
        
        # Real-time update setup (without auto-scroll)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.load)
        self.timer.start(2000) 
        self.load()

    def load(self):
        # Only fetch if window is active to save bandwidth
        if not self.isVisible(): return
        self.send_safe_cmd({"type": "GET_LOGS"})
        h = recv_all(self.cmd_s, 4)
        if h:
            sz = struct.unpack("!I", h)[0]
            data = recv_all(self.cmd_s, sz).decode('utf-8')
            if data: 
                # Append data (cursor position is preserved by default in QTextEdit unless explicitly moved)
                self.logs_area.append(data)

    def save_logs(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Logs", f"activity_logs_{ip_to_filename(self.ip)}.txt", "Text Files (*.txt)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.logs_area.toPlainText())
                
                if QMessageBox.question(self, "Success", "Logs saved successfully. Open it now?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                    from client.core.network import open_file; open_file(path)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to save logs: {e}")

def ip_to_filename(ip):
    return ip.replace(".", "_")

    def closeEvent(self, ev):
        self.timer.stop(); super().closeEvent(ev)

import cv2
import mss
import numpy as np
import struct
import logging
import threading
import time
from pathlib import Path
from server.core.registry import CommandRegistry, BaseCommand

@CommandRegistry.register("STREAM_CTRL")
class StreamCtrlCommand(BaseCommand):
    def execute(self, server, conn, data):
        server.is_streaming = data['active']
        server.stream_mode = data.get('mode', "SCREEN")

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
        # Wait for worker to finish and release recorder
        for _ in range(30):
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

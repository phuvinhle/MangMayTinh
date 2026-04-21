import socket
import os
import platform
import subprocess

def recv_all(sock, n):
    data = b""
    while len(data) < n:
        try:
            packet = sock.recv(n - len(data))
            if not packet: return None
            data += packet
        except: return None
    return data

def open_file(file_path):
    """Automatically open a file using the system default application."""
    if not os.path.exists(file_path): return
    try:
        sys_name = platform.system()
        if sys_name == "Windows": os.startfile(file_path)
        elif sys_name == "Darwin": subprocess.call(["open", file_path])
        else: subprocess.run(["xdg-open", file_path], check=True)
    except: pass

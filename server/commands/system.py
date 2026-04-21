import pyautogui
import psutil
import sys
import os
import re
import subprocess
import logging
import time
from pathlib import Path

from server.core.registry import CommandRegistry, BaseCommand


@CommandRegistry.register("MOUSE")
class MouseCommand(BaseCommand):
    def execute(self, server, conn, data):
        action = data.get('action', 'click')
        x, y = data['x'], data['y']
        btn = data.get('btn', 'left')
        
        if action == 'click':
            pyautogui.click(x, y, button=btn)
        elif action == 'down':
            pyautogui.mouseDown(x, y, button=btn)
        elif action == 'up':
            pyautogui.mouseUp(x, y, button=btn)
        elif action == 'move':
            pyautogui.moveTo(x, y)


@CommandRegistry.register("KEY")
class KeyCommand(BaseCommand):
    def execute(self, server, conn, data):
        pyautogui.press(data['key'])


@CommandRegistry.register("LIST_PROCS")
class ListProcsCommand(BaseCommand):
    def execute(self, server, conn, data):
        procs = []
        attrs = ['pid', 'name', 'cpu_percent', 'memory_percent', 'cmdline']
        for p in psutil.process_iter(attrs):
            try:
                info = p.info
                name = (
                    " ".join(info['cmdline'])
                    if info['cmdline']
                    else info['name']
                )
                if len(name) > 120:
                    name = name[:117] + "..."
                procs.append({
                    "pid": info['pid'],
                    "name": name,
                    "cpu_percent": info['cpu_percent'],
                    "memory_percent": info['memory_percent'],
                })
            except Exception:
                continue
        server.send_json(conn, procs)


@CommandRegistry.register("KILL_PROC")
class KillProcCommand(BaseCommand):
    def execute(self, server, conn, data):
        try:
            psutil.Process(data['pid']).terminate()
        except Exception:
            pass


@CommandRegistry.register("LIST_APPS")
class ListAppsCommand(BaseCommand):
    def execute(self, server, conn, data):
        apps = []
        if sys.platform == "linux":
            search_paths = [
                Path("/usr/share/applications"),
                Path("/var/lib/snapd/desktop/applications"),
                Path.home() / ".local/share/applications",
            ]
            for p in search_paths:
                if p.exists():
                    for f in p.glob("*.desktop"):
                        try:
                            with open(f, 'r', errors='ignore') as df:
                                content = df.read()
                                name = re.search(
                                    r'^Name=(.*)', content, re.M
                                )
                                exec_c = re.search(
                                    r'^Exec=(.*)', content, re.M
                                )
                                if name and exec_c:
                                    apps.append({
                                        "name": name.group(1).strip(),
                                        "exec": re.sub(
                                            r'%[a-zA-Z]', '',
                                            exec_c.group(1)
                                        ).strip(),
                                        "type": "Application",
                                    })
                        except Exception:
                            continue
        elif sys.platform == "win32":
            search_paths = [
                Path(os.environ["ProgramData"]) / "Microsoft/Windows/Start Menu/Programs",
                Path(os.environ["AppData"]) / "Microsoft/Windows/Start Menu/Programs",
            ]
            for p in search_paths:
                if p.exists():
                    for f in p.rglob("*.lnk"):
                        apps.append({
                            "name": f.stem,
                            "exec": str(f),
                            "type": "Shortcut",
                        })

        apps.sort(key=lambda x: x['name'].lower())
        server.send_json(conn, apps)


@CommandRegistry.register("START_APP")
class StartAppCommand(BaseCommand):
    def execute(self, server, conn, data):
        try:
            if sys.platform == "win32":
                os.startfile(data['exec'])
            else:
                subprocess.Popen(
                    data['exec'], shell=True, start_new_session=True
                )
        except Exception as e:
            logging.error(f"Start App Error: {e}")


@CommandRegistry.register("SHUTDOWN")
class ShutdownCommand(BaseCommand):
    def execute(self, server, conn, data):
        logging.info("Server shutting down...")
        conn.sendall(b"OK")
        time.sleep(2)
        if sys.platform == "win32":
            os.system("shutdown /s /t 1")
        else:
            os.system("systemctl poweroff")


@CommandRegistry.register("RESTART")
class RestartCommand(BaseCommand):
    def execute(self, server, conn, data):
        logging.info("Server restarting...")
        conn.sendall(b"OK")
        time.sleep(2)
        if sys.platform == "win32":
            os.system("shutdown /r /t 1")
        else:
            os.system("systemctl reboot")

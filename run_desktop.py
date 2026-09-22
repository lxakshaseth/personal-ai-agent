"""
Primary launcher for Personal AI Agent Windows Desktop Control Center.

Flow:
1. Ensures the Python FastAPI backend is running on http://127.0.0.1:8000 (starts it if needed).
2. Verifies backend health.
3. Automatically launches the modern Windows Desktop Application.
4. Cleans up background backend process when desktop application closes.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
DESKTOP_DIR = ROOT_DIR / "desktop"
VENV_PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():
    VENV_PYTHON = Path(sys.executable)

BACKEND_URL = "http://127.0.0.1:8000/health"


def is_backend_ready() -> bool:
    """Check if FastAPI backend responds with status ok."""
    try:
        with urllib.request.urlopen(BACKEND_URL, timeout=1.5) as resp:
            if resp.status == 200:
                return True
    except Exception:
        pass
    return False


def start_backend() -> subprocess.Popen | None:
    """Launch backend uvicorn server in a subprocess."""
    print("[Launcher] Starting FastAPI backend on http://127.0.0.1:8000 ...")
    cmd = [
        str(VENV_PYTHON),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


def wait_for_backend(timeout: float = 20.0) -> bool:
    """Poll backend until it responds or timeout is reached."""
    start_time = time.time()
    print("[Launcher] Waiting for agent core to initialize ...")
    while time.time() - start_time < timeout:
        if is_backend_ready():
            print("[Launcher] Agent backend is online and ready.")
            return True
        time.sleep(0.5)
    return False


def launch_desktop():
    """Launch the Electron desktop application."""
    print("[Launcher] Launching Desktop Robot Companion on Home Screen ...")
    npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"

    # Make sure desktop dist exists; if not, build it
    dist_index = DESKTOP_DIR / "dist" / "index.html"
    if not dist_index.exists():
        print("[Launcher] Building desktop bundle ...")
        subprocess.run([npx_cmd, "vite", "build"], cwd=str(DESKTOP_DIR), check=True)

    print("[Launcher] Robot is live on your desktop! Press Ctrl+Shift+R or click 'Dashboard' to expand.")
    # Launch Electron
    electron_proc = subprocess.run(
        [npx_cmd, "electron", "."],
        cwd=str(DESKTOP_DIR),
        shell=(sys.platform == "win32"),
    )
    return electron_proc.returncode


def main():
    print("=" * 60)
    print(" Personal AI Agent — Desktop Robot Companion & Control Center")
    print("=" * 60)

    backend_proc: subprocess.Popen | None = None

    if not is_backend_ready():
        backend_proc = start_backend()
        ready = wait_for_backend(timeout=25.0)
        if not ready:
            print("[Launcher Error] Backend failed to start within timeout.")
            if backend_proc:
                backend_proc.terminate()
            sys.exit(1)
    else:
        print("[Launcher] Detected existing backend running on port 8000.")

    try:
        launch_desktop()
    finally:
        if backend_proc:
            print("[Launcher] Shutting down agent backend process ...")
            backend_proc.terminate()
            try:
                backend_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                backend_proc.kill()
            print("[Launcher] Shutdown complete.")


if __name__ == "__main__":
    main()

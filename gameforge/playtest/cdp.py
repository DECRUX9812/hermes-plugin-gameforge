"""A dependency-free Chrome DevTools Protocol client: launches headless Chrome/Chromium, speaks
CDP over a minimal RFC 6455 websocket, and exposes the handful of calls a playtester needs
(navigate, evaluate, key events, screenshots, console/exception capture)."""

from __future__ import annotations

import base64
import glob
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

BROWSER_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge",
                 "microsoft-edge")
BROWSER_PATHS = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                 "/Applications/Chromium.app/Contents/MacOS/Chromium",
                 r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                 r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                 r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
PLAYWRIGHT_GLOBS = ("/opt/pw-browsers/chromium*/chrome-linux*/chrome", "~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")


def find_browser(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit if os.path.exists(explicit) else shutil.which(explicit)
    for name in BROWSER_NAMES:
        hit = shutil.which(name)
        if hit:
            return hit
    for path in BROWSER_PATHS:
        if os.path.exists(path):
            return path
    for pattern in PLAYWRIGHT_GLOBS:
        hits = sorted(glob.glob(os.path.expanduser(pattern)))
        if hits:
            return hits[-1]
    return None


class WebSocket:
    def __init__(self, url: str, timeout: float = 30.0) -> None:
        u = urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port or 80), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("websocket handshake closed")
            resp += chunk
        if b" 101 " not in resp.split(b"\r\n")[0]:
            raise ConnectionError(f"websocket handshake failed: {resp[:200]!r}")
        self.buf = resp.split(b"\r\n\r\n", 1)[1]

    def send(self, text: str) -> None:
        payload = text.encode()
        header = bytearray([0x81])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        header += mask
        self.sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def _read(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(max(65536, n - len(self.buf)))
            if not chunk:
                raise ConnectionError("websocket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self) -> str:
        message = b""
        while True:
            b0, b1 = self._read(2)
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            data = self._read(n)
            opcode = b0 & 0x0F
            if opcode == 0x8:
                raise ConnectionError("websocket closed by browser")
            if opcode in (0x9, 0xA):
                continue
            message += data
            if b0 & 0x80:
                return message.decode(errors="replace")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class Browser:
    """One headless browser with one page. Events (console, exceptions) are queued in ``events``."""

    def __init__(self, binary: str, width: int = 960, height: int = 720, start_url: str = "about:blank") -> None:
        """``start_url`` loads with the browser, so the page is up before we attach."""
        self.profile = tempfile.mkdtemp(prefix="gameforge-chrome-")
        args = [binary, "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={self.profile}",
                "--no-first-run", "--no-default-browser-check", "--autoplay-policy=no-user-gesture-required",
                "--mute-audio", "--no-proxy-server", "--disable-background-networking", "--disable-component-update",
                "--disable-features=HttpsUpgrades,HttpsFirstBalancedModeAutoEnable,OptimizationHints,MediaRouter", f"--window-size={width},{height}", "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding", "--enable-unsafe-swiftshader", start_url]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            args.insert(1, "--no-sandbox")
        # Headless needs no session bus; on hosts with a stale one every D-Bus call blocks for its 25s timeout.
        env = {**os.environ, "DBUS_SESSION_BUS_ADDRESS": "disabled:"}
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        port_file = Path(self.profile) / "DevToolsActivePort"
        deadline = time.monotonic() + 20
        while not port_file.exists() or not port_file.read_text().strip():
            if self.proc.poll() is not None or time.monotonic() > deadline:
                self.close()
                raise RuntimeError("the browser did not start (no DevToolsActivePort)")
            time.sleep(0.1)
        port = int(port_file.read_text().split()[0])
        targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=10).read())
        page = next(t for t in targets if t.get("type") == "page")
        self.ws = WebSocket(page["webSocketDebuggerUrl"])
        self._id = 0
        self._pending: dict[int, dict] = {}
        self._lock = threading.Lock()
        self.events: list[dict] = []
        self.width, self.height = width, height
        for domain in ("Page", "Runtime", "Log"):
            self.call(f"{domain}.enable")

    def call(self, method: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        with self._lock:
            self._id += 1
            mid = self._id
            self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            deadline = time.monotonic() + timeout
            while True:
                msg = json.loads(self.ws.recv())
                if msg.get("id") == mid:
                    if "error" in msg:
                        raise RuntimeError(f"{method}: {msg['error'].get('message')}")
                    return msg.get("result", {})
                if "method" in msg:
                    self.events.append(msg)
                if time.monotonic() > deadline:
                    raise TimeoutError(method)

    def navigate(self, url: str, wait: float = 1.0) -> None:
        self.call("Page.navigate", {"url": url})
        time.sleep(wait)

    def evaluate(self, expr: str):
        res = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in res:
            return None
        return res.get("result", {}).get("value")

    def key(self, code: str, down: bool) -> None:
        key, vk = _KEYS.get(code, (code, 0))
        params = {"type": "keyDown" if down else "keyUp", "code": code, "key": key, "windowsVirtualKeyCode": vk}
        if down and len(key) == 1:
            params["text"] = key
        self.call("Input.dispatchKeyEvent", params)

    def click(self, x: float, y: float) -> None:
        for kind in ("mousePressed", "mouseReleased"):
            self.call("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": "left", "clickCount": 1})

    def screenshot(self, fmt: str = "png", quality: int = 70) -> bytes:
        params = {"format": fmt}
        if fmt == "jpeg":
            params["quality"] = quality
        return base64.b64decode(self.call("Page.captureScreenshot", params)["data"])

    def drain_console(self) -> list[dict]:
        """Console errors/warnings and uncaught exceptions seen so far (and clears them)."""
        out = []
        for ev in self.events:
            m, p = ev["method"], ev.get("params", {})
            if m == "Runtime.exceptionThrown":
                d = p.get("exceptionDetails", {})
                desc = d.get("exception", {}).get("description") or d.get("text")
                out.append({"level": "exception", "text": desc, "line": d.get("lineNumber"), "url": d.get("url")})
            elif m == "Runtime.consoleAPICalled" and p.get("type") in ("error", "warning", "assert"):
                txt = " ".join(str(a.get("value", a.get("description", ""))) for a in p.get("args", []))
                out.append({"level": p["type"], "text": txt})
            elif m == "Log.entryAdded" and p.get("entry", {}).get("level") in ("error", "warning"):
                e = p["entry"]
                out.append({"level": e["level"], "text": e.get("text"), "url": e.get("url")})
        self.events.clear()
        return out

    def close(self) -> None:
        if getattr(self, "ws", None):
            self.ws.close()
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)


_KEYS = {"ArrowUp": ("ArrowUp", 38), "ArrowDown": ("ArrowDown", 40), "ArrowLeft": ("ArrowLeft", 37),
         "ArrowRight": ("ArrowRight", 39), "Space": (" ", 32), "Enter": ("Enter", 13), "Escape": ("Escape", 27),
         "KeyW": ("w", 87), "KeyA": ("a", 65), "KeyS": ("s", 83), "KeyD": ("d", 68), "KeyZ": ("z", 90),
         "KeyX": ("x", 88), "KeyJ": ("j", 74), "KeyK": ("k", 75), "ShiftLeft": ("Shift", 16)}

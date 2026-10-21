"""One-click sharing for web builds:

* ``bundle``     — dist/web: the build plus a PWA layer (manifest, icons, offline service worker), so
                   phones can "Add to Home Screen" and play offline.
* ``zip``        — dist/<slug>-web.zip with index.html at the root (itch.io / Newgrounds / GameJolt upload).
* ``single``     — one self-contained .html (every image/sound/JSON inlined) to send in a chat or email.
* ``capacitor``  — dist/mobile: a Capacitor project wrapping the build for native Android/iOS apps.
* ``itch``       — push the bundle with butler (only when explicitly asked: it publishes publicly).
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from PIL import Image

_PWA_HEAD = ('<link rel="manifest" href="manifest.webmanifest">\n<link rel="apple-touch-icon" href="icons/icon-192.png">\n'
             '<meta name="apple-mobile-web-app-capable" content="yes">\n')
_SW_REGISTER = ('<script>if ("serviceWorker" in navigator) addEventListener("load", () => '
                'navigator.serviceWorker.register("sw.js").catch(() => {}));</script>\n')


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "game"


def _icon(src_sprite: Path | None, size: int, bg=(26, 28, 44)) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), bg + (255,))
    if src_sprite and src_sprite.exists():
        sheet = Image.open(src_sprite).convert("RGBA")
        frame = sheet.crop((0, 0, min(16, sheet.width), min(16, sheet.height)))
        scale = max(1, int(size * 0.7) // frame.width)
        big = frame.resize((frame.width * scale, frame.height * scale), Image.NEAREST)
        canvas.alpha_composite(big, ((size - big.width) // 2, (size - big.height) // 2))
    return canvas


def bundle(web_dir: Path, out_dir: Path, title: str, icon_sprite: Path | None = None) -> dict:
    if not (web_dir / "index.html").exists():
        raise FileNotFoundError(f"{web_dir} has no index.html; scaffold or build the web version first")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(web_dir, out_dir, ignore=shutil.ignore_patterns(".gdignore", "*.map"))
    icons = out_dir / "icons"
    icons.mkdir(exist_ok=True)
    for size in (192, 512):
        _icon(icon_sprite, size).save(icons / f"icon-{size}.png")
    manifest = {"name": title, "short_name": title[:12], "start_url": ".", "display": "fullscreen",
                "orientation": "landscape", "background_color": "#1a1c2c", "theme_color": "#1a1c2c",
                "icons": [{"src": f"icons/icon-{s}.png", "sizes": f"{s}x{s}", "type": "image/png", "purpose": "any maskable"}
                          for s in (192, 512)]}
    (out_dir / "manifest.webmanifest").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    files = sorted(str(p.relative_to(out_dir)).replace(os.sep, "/") for p in out_dir.rglob("*") if p.is_file())
    digest = hashlib.sha256("".join(files).encode() + b"".join((out_dir / f).read_bytes()[:4096] for f in files)).hexdigest()[:12]
    (out_dir / "sw.js").write_text(
        f"const CACHE = 'gameforge-{digest}';\nconst FILES = {json.dumps(['./'] + files)};\n"
        "self.addEventListener('install', e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES)).then(() => self.skipWaiting())));\n"
        "self.addEventListener('activate', e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))));\n"
        "self.addEventListener('fetch', e => e.respondWith(caches.match(e.request).then(r => r || fetch(e.request))));\n",
        encoding="utf-8")
    index = out_dir / "index.html"
    html = index.read_text(encoding="utf-8")
    if 'rel="manifest"' not in html:
        html = html.replace("</head>", _PWA_HEAD + "</head>", 1)
    if "serviceWorker" not in html:
        html = html.replace("</body>", _SW_REGISTER + "</body>", 1)
    index.write_text(html, encoding="utf-8")
    size = sum(p.stat().st_size for p in out_dir.rglob("*") if p.is_file())
    return {"dir": out_dir, "files": len(files) + 2, "bytes": size, "pwa": True}


def zip_dir(src: Path, dest: Path) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(src))
    return {"zip": dest, "bytes": dest.stat().st_size,
            "upload": "itch.io: Create new project > Kind of project: HTML > upload this zip > 'This file will be played in the browser'"}


def _data_uri(path: Path, compress_audio: bool) -> str:
    if compress_audio and path.suffix == ".wav" and path.stat().st_size > 200_000 and shutil.which("ffmpeg"):
        with tempfile.TemporaryDirectory() as tmp:
            mp3 = Path(tmp) / "a.mp3"
            proc = subprocess.run([shutil.which("ffmpeg"), "-y", "-loglevel", "error", "-i", str(path), "-b:a", "128k", str(mp3)],
                                  capture_output=True, timeout=120)
            if proc.returncode == 0:
                return "data:audio/mpeg;base64," + base64.b64encode(mp3.read_bytes()).decode()
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def single_file(web_dir: Path, dest: Path, compress_audio: bool = True) -> dict:
    """Inline game.json (with every asset as a data URI) and game.js into one HTML file."""
    cfg = json.loads((web_dir / "game.json").read_text(encoding="utf-8"))

    def inline(v):
        if isinstance(v, str) and (web_dir / v).is_file():
            return _data_uri(web_dir / v, compress_audio)
        if isinstance(v, list):
            return [inline(x) for x in v]
        if isinstance(v, dict):
            return {k: inline(x) for k, x in v.items()}
        return v

    cfg["assets"] = inline(cfg["assets"])
    js = (web_dir / "game.js").read_text(encoding="utf-8")
    js = js.replace('cfg = await loadJSON("game.json");', "cfg = window.__GF_CONFIG;")
    html = (web_dir / "index.html").read_text(encoding="utf-8")
    payload = json.dumps(cfg, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace('<script src="game.js"></script>',
                        f"<script>window.__GF_CONFIG = {payload};</script>\n<script>\n{js}\n</script>")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")
    return {"html": dest, "bytes": dest.stat().st_size}


def capacitor(bundle_dir: Path, dest: Path, title: str, app_id: str) -> dict:
    """A ready-to-sync Capacitor project; native builds need Node + Android Studio/Xcode on the machine."""
    www = dest / "www"
    if www.exists():
        shutil.rmtree(www)
    shutil.copytree(bundle_dir, www)
    (dest / "package.json").write_text(json.dumps({
        "name": slug(title), "version": "1.0.0", "private": True,
        "scripts": {"android": "cap add android && cap sync android && cd android && ./gradlew assembleDebug",
                    "ios": "cap add ios && cap sync ios"},
        "dependencies": {"@capacitor/core": ">=7,<8", "@capacitor/android": ">=7,<8", "@capacitor/ios": ">=7,<8"},
        "devDependencies": {"@capacitor/cli": ">=7,<8"}}, indent=1), encoding="utf-8")
    (dest / "capacitor.config.json").write_text(json.dumps({
        "appId": app_id, "appName": title, "webDir": "www",
        "android": {"backgroundColor": "#1a1c2c"}, "ios": {"backgroundColor": "#1a1c2c"}}, indent=1), encoding="utf-8")
    return {"dir": dest, "next": ["cd " + str(dest), "npm install", "npm run android   # APK at android/app/build/outputs/apk/debug/",
                                  "npm run ios       # then open ios/App/App.xcworkspace in Xcode"]}


def itch_push(src: Path, target: str, version: str | None = None) -> dict:
    butler = shutil.which("butler")
    if not butler:
        raise RuntimeError("butler is not installed (https://itch.io/docs/butler/); upload the zip by hand instead")
    cmd = [butler, "push", str(src), target]
    if version:
        cmd += ["--userversion", version]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    return {"ok": proc.returncode == 0, "target": target, "log_tail": (proc.stdout + proc.stderr)[-1500:]}

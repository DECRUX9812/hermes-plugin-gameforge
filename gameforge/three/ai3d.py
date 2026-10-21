"""AI text/image → 3D through hosted providers (fal.ai queue, Meshy). Opt-in: nothing is sent
anywhere unless the user configured the provider's key. Results are downloaded as .glb."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.request
from pathlib import Path

FAL_TEXT_DEFAULT = "tripo3d/p1/text-to-3d"
FAL_IMAGE_DEFAULT = "fal-ai/trellis"
PROVIDERS = ("fal", "meshy")


class ProviderError(RuntimeError):
    pass


def available() -> dict[str, bool]:
    return {"fal": bool(os.environ.get("FAL_KEY")), "meshy": bool(os.environ.get("MESHY_API_KEY"))}


def _request(url: str, headers: dict, body: dict | None = None, method: str | None = None, timeout: int = 60) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"),
                                 headers={**headers, "Content-Type": "application/json", "User-Agent": "hermes-gameforge"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"{url} → HTTP {exc.code}: {exc.read()[:300].decode(errors='replace')}") from exc


def data_uri(path: str | Path) -> str:
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def _image_ref(image: str) -> str:
    return image if image.startswith(("http://", "https://", "data:")) else data_uri(image)


def _find_glb(obj) -> str | None:
    """Provider outputs differ (model_glb, model_mesh, model_urls.glb, ...): take the first GLB."""
    if isinstance(obj, dict):
        for key in ("model_glb", "glb", "model_mesh", "model_urls", "model_file", "mesh"):
            if key in obj:
                hit = _find_glb(obj[key])
                if hit:
                    return hit
        url = obj.get("url")
        if isinstance(url, str) and (".glb" in url or obj.get("content_type") == "model/gltf-binary"):
            return url
        for v in obj.values():
            hit = _find_glb(v)
            if hit:
                return hit
    elif isinstance(obj, list):
        for v in obj:
            hit = _find_glb(v)
            if hit:
                return hit
    elif isinstance(obj, str) and obj.startswith("http") and ".glb" in obj:
        return obj
    return None


def fal_generate(prompt: str | None, image: str | None, model: str | None, extra: dict,
                 timeout_s: int = 600) -> tuple[str, dict]:
    key = os.environ.get("FAL_KEY")
    if not key:
        raise ProviderError("FAL_KEY is not set")
    model = model or (FAL_IMAGE_DEFAULT if image else FAL_TEXT_DEFAULT)
    body = dict(extra)
    if image:
        body.setdefault("image_url" if "trellis" in model else "input_image_url", _image_ref(image))
    if prompt:
        body.setdefault("prompt", prompt)
    headers = {"Authorization": f"Key {key}"}
    sub = _request(f"https://queue.fal.run/{model}", headers, body)
    status_url = sub.get("status_url") or f"https://queue.fal.run/{model}/requests/{sub['request_id']}/status"
    result_url = sub.get("response_url") or f"https://queue.fal.run/{model}/requests/{sub['request_id']}"
    deadline = time.monotonic() + timeout_s
    while True:
        st = _request(status_url, headers)
        if st.get("status") == "COMPLETED":
            break
        if st.get("status") in ("FAILED", "ERROR", "CANCELLED"):
            raise ProviderError(f"fal request failed: {st}")
        if time.monotonic() > deadline:
            raise ProviderError(f"fal request still {st.get('status')} after {timeout_s}s (request {sub.get('request_id')})")
        time.sleep(4)
    result = _request(result_url, headers)
    url = _find_glb(result)
    if not url:
        raise ProviderError(f"no .glb in fal result: {json.dumps(result)[:400]}")
    return url, {"provider": "fal", "model": model, "request_id": sub.get("request_id")}


def meshy_generate(prompt: str | None, image: str | None, extra: dict, timeout_s: int = 900) -> tuple[str, dict]:
    key = os.environ.get("MESHY_API_KEY")
    if not key:
        raise ProviderError("MESHY_API_KEY is not set")
    headers = {"Authorization": f"Bearer {key}"}
    if image:
        base = "https://api.meshy.ai/openapi/v1/image-to-3d"
        body = {"image_url": _image_ref(image), **extra}
    else:
        base = "https://api.meshy.ai/openapi/v2/text-to-3d"
        body = {"mode": "preview", "prompt": prompt, **extra}
    task = _request(base, headers, body)["result"]
    deadline = time.monotonic() + timeout_s
    while True:
        st = _request(f"{base}/{task}", headers)
        if st.get("status") == "SUCCEEDED":
            url = (st.get("model_urls") or {}).get("glb")
            if not url:
                raise ProviderError("Meshy task succeeded without a glb url")
            return url, {"provider": "meshy", "task": task}
        if st.get("status") in ("FAILED", "CANCELED", "EXPIRED"):
            raise ProviderError(f"Meshy task {task} {st.get('status')}: {st.get('task_error')}")
        if time.monotonic() > deadline:
            raise ProviderError(f"Meshy task {task} still {st.get('status')} after {timeout_s}s")
        time.sleep(5)


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-gameforge"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        dest.write_bytes(resp.read())
    return dest


def generate(provider: str, prompt: str | None, image: str | None, dest: Path, model: str | None = None,
             extra: dict | None = None, timeout_s: int = 600) -> dict:
    if not prompt and not image:
        raise ProviderError("give a prompt, an image, or both")
    if provider == "fal":
        url, meta = fal_generate(prompt, image, model, extra or {}, timeout_s)
    elif provider == "meshy":
        url, meta = meshy_generate(prompt, image, extra or {}, timeout_s)
    else:
        raise ProviderError(f"unknown provider {provider!r}; choose from {', '.join(PROVIDERS)}")
    download(url, dest)
    return {**meta, "source_url": url, "path": str(dest)}

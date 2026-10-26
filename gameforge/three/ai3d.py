"""AI text/image → 3D through hosted providers (Tripo, fal.ai queue, Meshy) plus rigging and
animation retargeting on Tripo. Opt-in: nothing is sent anywhere unless the user configured the
provider's key. Results are downloaded as .glb.

Tripo speaks the V3 openapi (``https://openapi.tripo3d.ai/v3``): dedicated endpoints per capability
and a unified ``input`` field. V2 (``api.tripo3d.ai/v2/openapi``) stops accepting requests in
November 2026, so this module only targets V3.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from ..secrets import get_secret

FAL_TEXT_DEFAULT = "tripo3d/p1/text-to-3d"
FAL_IMAGE_DEFAULT = "fal-ai/trellis"
PROVIDERS = ("tripo", "fal", "meshy")

TRIPO_BASE = "https://openapi.tripo3d.ai/v3"
TRIPO_RIG_MODEL = "v3.0-20260909"
# Biped presets published for rig v2.5/v3.0. Retarget also accepts quadruped/hexapod/etc. forms
# such as "preset:quadruped:walk"; anything the API rejects comes back as a task error.
TRIPO_PRESETS = ("idle", "walk", "run", "dive", "climb", "jump", "slash", "shoot", "hurt", "fall", "turn")
TRIPO_ENV_KEYS = {"tripo": "TRIPO_API_KEY", "fal": "FAL_KEY", "meshy": "MESHY_API_KEY"}


class ProviderError(RuntimeError):
    pass


def available() -> dict[str, bool]:
    return {name: bool(get_secret(env)) for name, env in TRIPO_ENV_KEYS.items()}


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


IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def validated_image_ref(image: str, root: Path | None = None) -> str:
    """Resolve an ``image`` argument for a provider call.

    URLs and data URIs pass through. A local path is accepted only when it lives inside the
    project directory (when one is given) and the bytes really are an image — a model-named
    path must not be able to upload an arbitrary file from the host.
    """
    if image.startswith(("http://", "https://", "data:")):
        return image
    path = Path(image).expanduser()
    if not path.is_file():
        raise ProviderError(f"image {path} is not a file")
    resolved = path.resolve()
    if root is not None:
        base = Path(root).resolve()
        if resolved != base and base not in resolved.parents:
            raise ProviderError(f"image {resolved} is outside the project directory {base}")
    if resolved.suffix.lower() not in IMAGE_SUFFIXES:
        raise ProviderError(f"image {resolved.name} must be one of {', '.join(IMAGE_SUFFIXES)}")
    head = resolved.open("rb").read(12)
    looks_like_image = (
        head.startswith(b"\x89PNG\r\n\x1a\n")
        or head.startswith(b"\xff\xd8\xff")
        or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")
    )
    if not looks_like_image:
        raise ProviderError(f"image {resolved.name} does not look like a png/jpeg/webp")
    return data_uri(resolved)


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
    key = get_secret("FAL_KEY")
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
    key = get_secret("MESHY_API_KEY")
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


def _tripo_headers() -> dict:
    key = get_secret("TRIPO_API_KEY")
    if not key:
        raise ProviderError("TRIPO_API_KEY is not set")
    return {"Authorization": f"Bearer {key}"}


def _tripo_upload(path: str | Path) -> str:
    """POST /files (multipart) → file_token, so image-to-3D can take a local file."""
    p = Path(path)
    boundary = f"----gameforge{uuid.uuid4().hex}"
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{p.name}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n").encode()
    body = head + p.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{TRIPO_BASE}/files", data=body, method="POST",
                                 headers={**_tripo_headers(), "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"Tripo upload → HTTP {exc.code}: {exc.read()[:300].decode(errors='replace')}") from exc
    token = (payload.get("data") or {}).get("file_token") or payload.get("file_token")
    if not token:
        raise ProviderError(f"Tripo upload returned no file_token: {json.dumps(payload)[:300]}")
    return token


def _tripo_start(path: str, body: dict) -> str:
    payload = _request(f"{TRIPO_BASE}{path}", _tripo_headers(), body)
    task = (payload.get("data") or {}).get("task_id") or payload.get("task_id")
    if not task:
        raise ProviderError(f"Tripo {path} returned no task_id: {json.dumps(payload)[:300]}")
    return task


def _tripo_wait(task: str, timeout_s: int, label: str) -> dict:
    deadline = time.monotonic() + timeout_s
    while True:
        payload = _request(f"{TRIPO_BASE}/tasks/{task}", _tripo_headers())
        data = payload.get("data") or payload
        status = data.get("status")
        if status == "success":
            return data
        if status in ("failed", "cancelled", "banned", "expired", "unknown"):
            detail = data.get("error_message") or data.get("error_code") or ""
            raise ProviderError(f"Tripo {label} task {task} {status}: {detail}")
        if time.monotonic() > deadline:
            raise ProviderError(f"Tripo {label} task {task} still {status} after {timeout_s}s")
        time.sleep(4)


def tripo_generate(prompt: str | None, image: str | None, model: str | None, extra: dict,
                   timeout_s: int = 900, rig: bool = False,
                   animations: list[str] | None = None) -> tuple[str, dict]:
    """Text/image → model, optionally rigged and retargeted onto preset animations.

    Tripo splits the old single "animate" task into rig + retarget, and a retarget takes the *rig*
    task id as its input, so the chain is generation → rig → retarget, each polled to completion.
    """
    if not get_secret("TRIPO_API_KEY"):
        raise ProviderError("TRIPO_API_KEY is not set")
    body_extra = dict(extra or {})
    if model:
        body_extra.setdefault("model", model)
    preset_list = [a if a.startswith("preset:") else f"preset:{a}" for a in (animations or [])]

    if image:
        ref = image if image.startswith(("http://", "https://")) else _tripo_upload(image)
        task = _tripo_start("/generation/image-to-model", {**body_extra, "input": ref})
        kind = "image-to-model"
    else:
        if not prompt:
            raise ProviderError("give a prompt, an image, or both")
        task = _tripo_start("/generation/text-to-model", {"prompt": prompt, **body_extra})
        kind = "text-to-model"
    data = _tripo_wait(task, timeout_s, kind)
    chain = [task]

    if rig:
        rig_task = _tripo_start("/animations/rig", {"input": task, "model": TRIPO_RIG_MODEL,
                                                    "rig_type": "biped", "spec": "mixamo", "out_format": "glb"})
        data = _tripo_wait(rig_task, timeout_s, "rig")
        chain.append(rig_task)
        if preset_list:
            retarget = {"input": rig_task, "out_format": "glb", "animate_in_place": True}
            if len(preset_list) == 1:
                retarget["animation"] = preset_list[0]
            else:
                retarget["animations"] = preset_list[:5]      # the API rejects more than five
            anim_task = _tripo_start("/animations/retarget", retarget)
            data = _tripo_wait(anim_task, timeout_s, "retarget")
            chain.append(anim_task)

    url = _find_glb(data.get("output") or data)
    if not url:
        raise ProviderError(f"no .glb in Tripo task output: {json.dumps(data)[:400]}")
    return url, {"provider": "tripo", "task": task, "tasks": chain, "rigged": bool(rig),
                 "animations": preset_list}


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-gameforge"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        dest.write_bytes(resp.read())
    return dest


def generate(provider: str, prompt: str | None, image: str | None, dest: Path, model: str | None = None,
             extra: dict | None = None, timeout_s: int = 600, rig: bool = False,
             animations: list[str] | None = None) -> dict:
    if not prompt and not image:
        raise ProviderError("give a prompt, an image, or both")
    if provider == "tripo":
        url, meta = tripo_generate(prompt, image, model, extra or {}, timeout_s, rig, animations)
    elif provider == "fal":
        url, meta = fal_generate(prompt, image, model, extra or {}, timeout_s)
    elif provider == "meshy":
        url, meta = meshy_generate(prompt, image, extra or {}, timeout_s)
    else:
        raise ProviderError(f"unknown provider {provider!r}; choose from {', '.join(PROVIDERS)}")
    download(url, dest)
    return {**meta, "source_url": url, "path": str(dest)}

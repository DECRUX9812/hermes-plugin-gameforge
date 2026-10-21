"""Tripo provider: the rig/retarget chain and request shapes, verified against a fake transport.

No network: ``ai3d._request`` is replaced with a recorder that answers like the V3 open API
(code/data envelopes, task ids, queued → success), so these tests lock the contract we send.
"""

import pytest

from gameforge.three import ai3d


class FakeTripo:
    """Answers create-task and task-query calls the way openapi.tripo3d.ai/v3 does."""

    def __init__(self, outputs=None, statuses=None):
        self.calls: list[tuple[str, dict | None]] = []
        self.tasks: dict[str, dict] = {}
        self.n = 0
        self.outputs = outputs or ["https://cdn.tripo3d.ai/output/model_pbr.glb"]
        self.statuses = statuses or ["queued", "running", "success"]

    def __call__(self, url, headers, body=None, method=None, timeout=60):
        self.calls.append((url, body))
        if "/tasks/" in url:
            task = url.rsplit("/", 1)[-1]
            state = self.tasks[task]
            status = self.statuses[min(state["polls"], len(self.statuses) - 1)]
            state["polls"] += 1
            data = {"task_id": task, "type": state["type"], "status": status, "progress": 50}
            if status == "success":
                data["output"] = {"model_url": state["output"]}
            return {"code": 0, "data": data}
        # a create-task call: mint an id and remember what it produces
        self.n += 1
        task = f"task_{self.n:03d}"
        kind = url.rsplit("/", 1)[-1]
        self.tasks[task] = {"polls": 0, "type": kind, "output": self.outputs[min(self.n - 1, len(self.outputs) - 1)]}
        return {"code": 0, "data": {"task_id": task}}


@pytest.fixture(autouse=True)
def tripo_key(monkeypatch):
    monkeypatch.setenv("TRIPO_API_KEY", "sk-test-tripo")
    monkeypatch.setattr(ai3d.time, "sleep", lambda _s: None)


def test_text_to_model_hits_the_v3_generation_endpoint(monkeypatch):
    fake = FakeTripo()
    monkeypatch.setattr(ai3d, "_request", fake)
    url, meta = ai3d.tripo_generate("a brass goblin chieftain", None, None, {}, 60)
    assert url.endswith(".glb")
    create_url, create_body = fake.calls[0]
    assert create_url == f"{ai3d.TRIPO_BASE}/generation/text-to-model"
    assert create_body == {"prompt": "a brass goblin chieftain"}
    assert meta["provider"] == "tripo" and meta["rigged"] is False


def test_rig_and_retarget_chain_inputs_point_at_the_previous_task(monkeypatch):
    fake = FakeTripo()
    monkeypatch.setattr(ai3d, "_request", fake)
    url, meta = ai3d.tripo_generate("a goblin chief", None, None, {}, 60, rig=True,
                                    animations=["walk", "jump"])
    creates = [c for c in fake.calls if c[1] and ("prompt" in c[1] or "input" in c[1])]
    gen_url, gen_body = creates[0]
    rig_url, rig_body = creates[1]
    anim_url, anim_body = creates[2]
    assert gen_url.endswith("/generation/text-to-model")
    assert rig_url.endswith("/animations/rig")
    assert rig_body["input"] == meta["task"]
    assert rig_body["rig_type"] == "biped" and rig_body["spec"] == "mixamo"
    assert anim_url.endswith("/animations/retarget")
    assert anim_body["input"] == meta["tasks"][1]          # retarget takes the RIG task id
    assert anim_body["animations"] == ["preset:walk", "preset:jump"]
    assert anim_body["animate_in_place"] is True
    assert meta["rigged"] is True and len(meta["tasks"]) == 3


def test_single_animation_uses_the_singular_field(monkeypatch):
    fake = FakeTripo()
    monkeypatch.setattr(ai3d, "_request", fake)
    ai3d.tripo_generate("a knight", None, None, {}, 60, rig=True, animations=["run"])
    anim_body = [c[1] for c in fake.calls if c[1] and "animation" in c[1]][0]
    assert anim_body["animation"] == "preset:run"
    assert "animations" not in anim_body


def test_more_than_five_animations_are_truncated_to_the_api_limit(monkeypatch):
    fake = FakeTripo()
    monkeypatch.setattr(ai3d, "_request", fake)
    _, meta = ai3d.tripo_generate("a knight", None, None, {}, 60, rig=True,
                                  animations=["idle", "walk", "run", "jump", "turn", "slash"])
    assert meta["animations"][-1] == "preset:slash"
    anim_body = [c[1] for c in fake.calls if c[1] and "animations" in c[1]][0]
    assert len(anim_body["animations"]) == 5


def test_failed_task_raises_with_the_provider_message(monkeypatch):
    class Failing(FakeTripo):
        def __call__(self, url, headers, body=None, method=None, timeout=60):
            self.calls.append((url, body))
            if "/tasks/" in url:
                return {"code": 0, "data": {"task_id": "task_001", "status": "failed",
                                            "error_code": 3001, "error_message": "content policy"}}
            return {"code": 0, "data": {"task_id": "task_001"}}

    monkeypatch.setattr(ai3d, "_request", Failing())
    with pytest.raises(ai3d.ProviderError, match="content policy"):
        ai3d.tripo_generate("something disallowed", None, None, {}, 5)


def test_missing_key_is_reported_not_silently_skipped(monkeypatch):
    monkeypatch.delenv("TRIPO_API_KEY", raising=False)
    assert ai3d.available()["tripo"] is False
    with pytest.raises(ai3d.ProviderError, match="TRIPO_API_KEY"):
        ai3d.tripo_generate("a cat", None, None, {}, 5)


def test_image_url_passes_through_as_the_input_field(monkeypatch):
    fake = FakeTripo()
    monkeypatch.setattr(ai3d, "_request", fake)
    ai3d.tripo_generate(None, "https://example.com/hero.png", None, {}, 60)
    url, body = fake.calls[0]
    assert url.endswith("/generation/image-to-model")
    assert body == {"input": "https://example.com/hero.png"}


def test_local_image_is_uploaded_and_its_token_is_sent(monkeypatch, tmp_path):
    png = tmp_path / "hero.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    monkeypatch.setattr(ai3d, "_tripo_upload", lambda path: "file_token_abc")
    fake = FakeTripo()
    monkeypatch.setattr(ai3d, "_request", fake)
    ai3d.tripo_generate(None, str(png), None, {}, 60)
    assert fake.calls[0][1] == {"input": "file_token_abc"}


def test_generate_dispatches_tripo_and_downloads(monkeypatch, tmp_path):
    called = {}

    def fake_tripo(prompt, image, model, extra, timeout_s, rig, animations):
        called.update(prompt=prompt, rig=rig, animations=animations)
        return "https://cdn.tripo3d.ai/x.glb", {"provider": "tripo", "tasks": ["t1"]}

    monkeypatch.setattr(ai3d, "tripo_generate", fake_tripo)
    monkeypatch.setattr(ai3d, "download", lambda url, dest: dest.write_bytes(b"glTF") or dest)
    dest = tmp_path / "m.glb"
    out = ai3d.generate("tripo", "a robot", None, dest, None, None, 60, rig=True, animations=["walk"])
    assert dest.read_bytes() == b"glTF"
    assert out["provider"] == "tripo" and called["rig"] is True and called["animations"] == ["walk"]

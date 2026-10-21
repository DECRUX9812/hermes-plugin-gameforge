"""NPC voices: a cast of characters, each a TTS voice plus a DSP character chain (goblin, giant,
robot, ghost, radio...), and an offline "babble" voice in the Animal Crossing / Undertale tradition
that needs no TTS at all.

Every rendered line also gets per-character timings so a dialogue box can type in sync.
"""

from __future__ import annotations

import asyncio
import math
import random
import re
import shutil
import subprocess
from pathlib import Path

from . import dsp

# DSP chains: (effect, kwargs) applied in order
CHARACTER_FX: dict[str, list[tuple[str, dict]]] = {
    "none": [],
    "hero": [("reverb", {"room": 0.2, "wet": 0.15})],
    "goblin": [("pitch", {"semitones": 6}), ("bandpass", {"low_hz": 250, "high_hz": 4500}),
               ("distort", {"drive": 1.6})],
    "giant": [("pitch", {"semitones": -6}), ("lowpass", {"cutoff": 3200}), ("reverb", {"room": 0.6, "wet": 0.35})],
    "robot": [("ring_mod", {"freq": 55, "depth": 0.7}), ("bitcrush", {"bits": 8, "hold": 2})],
    "ghost": [("pitch", {"semitones": 2}), ("tremolo", {"freq": 5, "depth": 0.4}),
              ("delay", {"seconds": 0.22, "feedback": 0.45, "wet": 0.4}), ("reverb", {"room": 0.95, "wet": 0.7})],
    "radio": [("bandpass", {"low_hz": 450, "high_hz": 3000}), ("distort", {"drive": 3.0}), ("hiss", {"level": 0.02})],
    "demon": [("octave_down", {"mix": 0.7}), ("distort", {"drive": 2.5}), ("reverb", {"room": 0.7, "wet": 0.4})],
    "fairy": [("pitch", {"semitones": 9}), ("tremolo", {"freq": 11, "depth": 0.25}), ("reverb", {"room": 0.6, "wet": 0.4})],
    "elder": [("pitch", {"semitones": -2}), ("tremolo", {"freq": 5.5, "depth": 0.15}), ("reverb", {"room": 0.3, "wet": 0.2})],
    "cave": [("reverb", {"room": 0.9, "wet": 0.6}), ("delay", {"seconds": 0.35, "feedback": 0.3, "wet": 0.25})],
    "announcer": [("highpass", {"cutoff": 120}), ("distort", {"drive": 1.3}), ("delay", {"seconds": 0.09, "feedback": 0.2, "wet": 0.2})],
}

# A small default palette of distinct Edge neural voices so a cast sounds like different people.
EDGE_VOICES = {
    "male": ["en-US-GuyNeural", "en-GB-RyanNeural", "en-US-ChristopherNeural", "en-AU-WilliamNeural",
             "en-US-EricNeural", "en-IE-ConnorNeural"],
    "female": ["en-US-JennyNeural", "en-GB-SoniaNeural", "en-US-AriaNeural", "en-AU-NatashaNeural",
               "en-US-MichelleNeural", "en-IE-EmilyNeural"],
    "child": ["en-US-AnaNeural", "en-GB-MaisieNeural"],
}

ENGINES = ("babble", "edge", "hermes")


def apply_fx(buf: list[float], chain: list[tuple[str, dict]], rate: int, seed: int = 0) -> list[float]:
    rng = random.Random(seed)
    for name, kw in chain:
        if name == "pitch":
            buf = dsp.pitch_shift(buf, kw["semitones"], rate)
        elif name == "octave_down":
            low = dsp.pitch_shift(buf, -12, rate)
            buf = [a * (1 - kw["mix"]) + b * kw["mix"] for a, b in zip(buf, low)]
        elif name == "bandpass":
            buf = dsp.bandpass(buf, kw["low_hz"], kw["high_hz"], rate)
        elif name in ("lowpass", "highpass"):
            buf = getattr(dsp, name)(buf, kw["cutoff"], rate)
        elif name == "hiss":
            buf = [s + rng.uniform(-1, 1) * kw["level"] for s in buf]
        elif name in ("reverb", "delay", "tremolo", "ring_mod"):
            buf = getattr(dsp, name)(buf, **kw, rate=rate)
        elif name in ("distort", "bitcrush"):
            buf = getattr(dsp, name)(buf, **kw)
        else:
            raise ValueError(f"unknown voice effect {name!r}")
    return dsp.normalize(buf, 0.9)


# ---------------------------------------------------------------------------- babble (offline)

_VOWELS = set("aeiouy")


def babble(text: str, pitch_hz: float = 220.0, speed: float = 1.0, timbre: str = "warm",
           seed: int = 0, rate: int = 22050) -> tuple[list[float], list[dict]]:
    """Speak ``text`` as pitched syllable blips; returns audio and per-character reveal times."""
    rng = random.Random(seed)
    step = 0.055 / max(0.25, speed)
    out: list[float] = []
    timings: list[dict] = []
    t = 0.0
    question = text.rstrip().endswith("?")
    for idx, ch in enumerate(text):
        timings.append({"i": idx, "char": ch, "t": round(t, 3)})
        low = ch.lower()
        if low.isalpha():
            base = pitch_hz * (1.12 if low in _VOWELS else 1.0)
            f = base * 2 ** (((ord(low) * 7) % 5 - 2) / 12) * (1 + rng.uniform(-0.02, 0.02))
            if question and idx > len(text) * 0.75:  # questions rise at the end
                f *= 1.15
            dsp.mix_into(out, _blip(f, step * 0.9, timbre, rate, low in _VOWELS), int(t * rate))
            t += step
        elif ch in ",;:":
            t += step * 3
        elif ch in ".!?":
            t += step * 5
        else:
            t += step * 0.8
    out.extend([0.0] * int(rate * 0.1))
    return dsp.normalize(out, 0.85), timings


def _blip(f: float, dur: float, timbre: str, rate: int, vowel: bool) -> list[float]:
    n = int(dur * rate)
    w = 2 * math.pi * f / rate
    out = []
    for i in range(n):
        env = math.sin(math.pi * i / n) ** (0.6 if vowel else 1.4)
        if timbre == "square":
            s = 0.5 if math.sin(w * i) > 0 else -0.5
        elif timbre == "bright":
            s = math.sin(w * i) + 0.5 * math.sin(2 * w * i) + 0.25 * math.sin(3 * w * i)
        else:  # warm: two formant-ish partials
            s = math.sin(w * i) + 0.35 * math.sin(2.01 * w * i) + 0.12 * math.sin(3.98 * w * i)
        out.append(s * env)
    return out


# ---------------------------------------------------------------------------- TTS engines

def edge_available() -> bool:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False
    return True


def edge_tts_to_file(text: str, voice: str, out_path: Path, rate_pct: int = 0, pitch_hz: int = 0) -> Path:
    import edge_tts

    kwargs = {"voice": voice}
    if rate_pct:
        kwargs["rate"] = f"{rate_pct:+d}%"
    if pitch_hz:
        kwargs["pitch"] = f"{pitch_hz:+d}Hz"

    async def _go() -> None:
        await edge_tts.Communicate(text, **kwargs).save(str(out_path))

    asyncio.run(_go())
    return out_path


def decode_to_wav(src: Path, dest: Path, rate: int = 22050) -> Path | None:
    """Any audio → mono WAV via ffmpeg; ``None`` when ffmpeg is absent."""
    if src.suffix.lower() == ".wav":
        return src
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", str(rate), str(dest)],
                   check=True, timeout=120)
    return dest


def estimate_timings(text: str, duration: float) -> list[dict]:
    """Spread character reveal times over a TTS clip, pausing on punctuation like a speaker does."""
    weights = [3.0 if c in ".!?" else 2.0 if c in ",;:" else 1.0 if c.strip() else 0.6 for c in text]
    total = sum(weights) or 1.0
    t, out = 0.0, []
    for i, (c, w) in enumerate(zip(text, weights)):
        out.append({"i": i, "char": c, "t": round(t, 3)})
        t += duration * w / total
    return out


def slug(text: str, limit: int = 32) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:limit] or "line"

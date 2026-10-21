"""Pure-Python DSP: WAV I/O, mixing and the effects every GameForge audio path shares.

Buffers are plain ``list[float]`` in [-1, 1], mono unless a function says otherwise. Nothing here
needs numpy: game SFX are short and music renders at 22.05 kHz, so the stdlib keeps the plugin
installable everywhere Hermes runs.
"""

from __future__ import annotations

import array
import math
import random
import struct
import wave
from pathlib import Path

RATE = 44100


def write_wav(path: str | Path, samples: list[float], rate: int = RATE, stereo: list[float] | None = None) -> Path:
    """Write 16-bit PCM. ``stereo`` (the right channel) makes ``samples`` the left channel."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = array.array("h")
    if stereo is None:
        pcm.extend(_to_i16(s) for s in samples)
        channels = 1
    else:
        for left, right in zip(samples, stereo):
            pcm.append(_to_i16(left))
            pcm.append(_to_i16(right))
        channels = 2
    if pcm.itemsize != 2 or struct.pack("=h", 1) != struct.pack("<h", 1):
        pcm.byteswap()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return path


def read_wav(path: str | Path) -> tuple[list[float], int]:
    """Read a PCM WAV as mono floats (channels averaged)."""
    with wave.open(str(path), "rb") as w:
        width, channels, rate = w.getsampwidth(), w.getnchannels(), w.getframerate()
        raw = w.readframes(w.getnframes())
    if width == 2:
        data = array.array("h")
        data.frombytes(raw)
        scale = 32768.0
    elif width == 1:
        data = array.array("B", raw)
        data = array.array("h", ((b - 128) << 8 for b in data))
        scale = 32768.0
    elif width == 4:
        data = array.array("i")
        data.frombytes(raw)
        scale = 2147483648.0
    else:
        raise ValueError(f"unsupported sample width {width}")
    if channels == 1:
        return [v / scale for v in data], rate
    return [sum(data[i:i + channels]) / (channels * scale) for i in range(0, len(data), channels)], rate


def _to_i16(s: float) -> int:
    return int(max(-1.0, min(1.0, s)) * 32767)


def normalize(buf: list[float], peak: float = 0.9) -> list[float]:
    top = max((abs(s) for s in buf), default=0.0)
    if top < 1e-9:
        return buf
    g = peak / top
    return [s * g for s in buf]


def fade(buf: list[float], fade_in: float = 0.0, fade_out: float = 0.0, rate: int = RATE) -> list[float]:
    out = list(buf)
    n_in, n_out = int(fade_in * rate), int(fade_out * rate)
    for i in range(min(n_in, len(out))):
        out[i] *= i / n_in
    for i in range(min(n_out, len(out))):
        out[-1 - i] *= i / n_out
    return out


def mix_into(dest: list[float], src: list[float], offset: int, gain: float = 1.0) -> None:
    """Add ``src`` into ``dest`` at sample ``offset``, growing ``dest`` as needed."""
    end = offset + len(src)
    if end > len(dest):
        dest.extend([0.0] * (end - len(dest)))
    dest[offset:end] = [d + s * gain for d, s in zip(dest[offset:end], src)]


def soft_clip(buf: list[float]) -> list[float]:
    return [math.tanh(s) for s in buf]


def lowpass(buf: list[float], cutoff: float, rate: int = RATE) -> list[float]:
    a = 1.0 - math.exp(-2.0 * math.pi * cutoff / rate)
    y, out = 0.0, []
    for s in buf:
        y += a * (s - y)
        out.append(y)
    return out


def highpass(buf: list[float], cutoff: float, rate: int = RATE) -> list[float]:
    low = lowpass(buf, cutoff, rate)
    return [s - l for s, l in zip(buf, low)]


def bandpass(buf: list[float], low_hz: float, high_hz: float, rate: int = RATE) -> list[float]:
    return lowpass(highpass(buf, low_hz, rate), high_hz, rate)


def bitcrush(buf: list[float], bits: int = 6, hold: int = 2) -> list[float]:
    steps = 2 ** max(1, bits - 1)
    out, last = [], 0.0
    for i, s in enumerate(buf):
        if i % max(1, hold) == 0:
            last = round(s * steps) / steps
        out.append(last)
    return out


def delay(buf: list[float], seconds: float, feedback: float = 0.35, wet: float = 0.35, rate: int = RATE) -> list[float]:
    d = max(1, int(seconds * rate))
    out = list(buf) + [0.0] * int(d * 4)
    line = [0.0] * len(out)
    for i in range(len(out)):
        echo = line[i - d] if i >= d else 0.0
        dry = out[i]
        line[i] = dry + echo * feedback
        out[i] = dry + echo * wet
    return out


def reverb(buf: list[float], room: float = 0.5, wet: float = 0.25, rate: int = RATE) -> list[float]:
    tail = reverb_wet(buf, room, rate)
    return [d + t * wet for d, t in zip(buf + [0.0] * (len(tail) - len(buf)), tail)]


def reverb_wet(buf: list[float], room: float = 0.5, rate: int = RATE) -> list[float]:
    """Schroeder reverb, wet signal only (longer than ``buf`` by the tail): four parallel damped
    combs into two series allpasses."""
    scale = rate / 44100
    fb = 0.7 + 0.28 * max(0.0, min(1.0, room))
    src = list(buf) + [0.0] * int(rate * (0.4 + room * 1.6))
    n = len(src)
    acc = [0.0] * n
    for d in (int(t * scale) for t in (1557, 1617, 1491, 1422)):
        line = [0.0] * n
        damp = 0.0
        for i in range(n):
            y = line[i - d] if i >= d else 0.0
            damp = y * 0.8 + damp * 0.2
            line[i] = src[i] + damp * fb
        acc = [a + y for a, y in zip(acc, [0.0] * d + line[:n - d])]
    for d in (int(225 * scale), int(556 * scale)):
        out = [0.0] * n
        for i in range(n):
            if i >= d:
                out[i] = -0.5 * acc[i] + acc[i - d] + 0.5 * out[i - d]
            else:
                out[i] = -0.5 * acc[i]
        acc = out
    return [a * 0.25 for a in acc]


def resample(buf: list[float], factor: float) -> list[float]:
    """Linear-interpolated speed change: ``factor`` > 1 plays faster (higher, shorter)."""
    if factor <= 0:
        raise ValueError("factor must be positive")
    n = int(len(buf) / factor)
    out = []
    last = len(buf) - 1
    for i in range(n):
        pos = i * factor
        j = int(pos)
        frac = pos - j
        a = buf[j] if j <= last else 0.0
        b = buf[j + 1] if j + 1 <= last else a
        out.append(a + (b - a) * frac)
    return out


def time_stretch(buf: list[float], ratio: float, rate: int = RATE) -> list[float]:
    """Overlap-add time stretch (``ratio`` > 1 = longer) that keeps pitch.

    The grain adapts to the buffer: a fixed 40 ms grain (1764 samples at 44.1 kHz) is longer
    than a short click, and the old ``pos_in + grain < len(buf)`` loop then never ran at all,
    returning silence. Short buffers get a shorter grain, and a buffer too short for even one
    grain is resampled instead of being dropped.
    """
    if not buf:
        return []
    grain = int(rate * 0.04)
    grain = max(8, min(grain, len(buf) // 2)) if len(buf) >= 16 else len(buf)
    hop_out = max(1, grain // 2)
    hop_in = max(1, int(hop_out / ratio))
    win = [0.5 - 0.5 * math.cos(2 * math.pi * i / grain) for i in range(grain)]
    n_out = int(len(buf) * ratio) + grain
    out, norm = [0.0] * n_out, [0.0] * n_out
    pos_in = pos_out = 0
    while pos_in + grain <= len(buf) and pos_out + grain <= n_out:
        for i in range(grain):
            out[pos_out + i] += buf[pos_in + i] * win[i]
            norm[pos_out + i] += win[i]
        pos_in += hop_in
        pos_out += hop_out
    if pos_out == 0:
        # Too short for one grain: resampling preserves the length contract and stays audible.
        return resample(buf, 1.0 / ratio) if ratio > 0 else list(buf)
    return [o / n if n > 1e-3 else o for o, n in zip(out[:pos_out], norm[:pos_out])]


def pitch_shift(buf: list[float], semitones: float, rate: int = RATE) -> list[float]:
    """Shift pitch, keep duration: resample, then stretch back."""
    if abs(semitones) < 1e-3:
        return list(buf)
    factor = 2 ** (semitones / 12)
    return time_stretch(resample(buf, factor), factor, rate)


def ring_mod(buf: list[float], freq: float, depth: float = 1.0, rate: int = RATE) -> list[float]:
    w = 2 * math.pi * freq / rate
    return [s * ((1 - depth) + depth * math.sin(w * i)) for i, s in enumerate(buf)]


def tremolo(buf: list[float], freq: float, depth: float = 0.5, rate: int = RATE) -> list[float]:
    w = 2 * math.pi * freq / rate
    return [s * (1 - depth * (0.5 + 0.5 * math.sin(w * i))) for i, s in enumerate(buf)]


def distort(buf: list[float], drive: float = 4.0) -> list[float]:
    return [math.tanh(s * drive) / math.tanh(drive) for s in buf]


def white_noise(n: int, rng: random.Random) -> list[float]:
    return [rng.uniform(-1, 1) for _ in range(n)]


def peak_db(buf: list[float]) -> float:
    top = max((abs(s) for s in buf), default=0.0)
    return 20 * math.log10(top) if top > 0 else -120.0


def rms_db(buf: list[float]) -> float:
    if not buf:
        return -120.0
    rms = math.sqrt(sum(s * s for s in buf) / len(buf))
    return 20 * math.log10(rms) if rms > 0 else -120.0

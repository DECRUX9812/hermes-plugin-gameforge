"""Procedural game music: mood → mode, progression, motif-based melody, bass, arpeggio and drums,
rendered as a seamless loop (WAV) plus a multi-track MIDI file the user can open in any DAW or
engine.

The composer is deterministic per seed. Melodies are built from a two-bar motif that is repeated,
varied and resolved, which is the difference between "random notes" and something you can hum.
"""

from __future__ import annotations

import math
import random
import struct
from dataclasses import dataclass, field
from pathlib import Path

from . import dsp

RATE = 22050

MODES = {
    "major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10], "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10], "mixolydian": [0, 2, 4, 5, 7, 9, 10], "lydian": [0, 2, 4, 6, 7, 9, 11],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
}

NOTE_NAMES = {"C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5, "F#": 6, "GB": 6,
              "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11}

# progressions are scale degrees (0 = tonic), one chord per bar
MOODS: dict[str, dict] = {
    "heroic": {"mode": "major", "bpm": 132, "progs": [[0, 4, 5, 3], [0, 3, 4, 4], [5, 3, 0, 4]],
               "drums": "march", "density": 0.7, "arp": True},
    "happy": {"mode": "major", "bpm": 120, "progs": [[0, 5, 3, 4], [0, 3, 0, 4], [3, 4, 2, 5]],
              "drums": "bounce", "density": 0.75, "arp": True},
    "adventure": {"mode": "mixolydian", "bpm": 126, "progs": [[0, 6, 3, 0], [0, 3, 6, 4]],
                  "drums": "drive", "density": 0.7, "arp": True},
    "sad": {"mode": "minor", "bpm": 78, "progs": [[0, 5, 2, 6], [0, 3, 5, 4]],
            "drums": "sparse", "density": 0.45, "arp": False},
    "mysterious": {"mode": "dorian", "bpm": 92, "progs": [[0, 1, 0, 6], [0, 3, 1, 0]],
                   "drums": "sparse", "density": 0.5, "arp": True},
    "tense": {"mode": "harmonic_minor", "bpm": 140, "progs": [[0, 0, 5, 4], [0, 5, 3, 4]],
              "drums": "drive", "density": 0.6, "arp": True},
    "boss": {"mode": "phrygian", "bpm": 168, "progs": [[0, 1, 0, 6], [0, 1, 5, 4]],
             "drums": "blast", "density": 0.85, "arp": True},
    "chill": {"mode": "major", "bpm": 84, "progs": [[0, 2, 3, 5], [3, 4, 2, 5]],
              "drums": "lofi", "density": 0.45, "arp": False, "sevenths": True},
    "spooky": {"mode": "harmonic_minor", "bpm": 96, "progs": [[0, 5, 0, 4], [0, 1, 5, 4]],
               "drums": "sparse", "density": 0.4, "arp": True},
    "victory": {"mode": "major", "bpm": 140, "progs": [[0, 3, 4, 0]], "drums": "march", "density": 0.8,
                "arp": True},
}

DRUMS = {  # 16 steps per bar: K kick, S snare, H hat, O open hat
    "march": ["K...S...K.K.S...", "H.H.H.H.H.H.H.H."],
    "bounce": ["K.....K.S.......", "..H...H...H...H."],
    "drive": ["K...S...K...S...", "HHHHHHHHHHHHHHHH"],
    "sparse": ["K.......S.......", "....H.......H..."],
    "blast": ["K.K.SK.KK.K.S.KK", "HHHHHHHHHHHHHHHH"],
    "lofi": ["K......K..K.S...", "H.H.H.HHH.H.H.H."],
}

RHYTHMS = [  # melody rhythm cells in 16ths, sum = 16
    [4, 4, 4, 4], [2, 2, 4, 4, 4], [4, 2, 2, 8], [6, 2, 4, 4], [3, 3, 2, 4, 4], [2, 2, 2, 2, 8],
    [8, 4, 4], [4, 4, 8], [2, 2, 2, 2, 4, 4], [12, 4],
]

STYLES = ("chiptune", "synthwave", "ambient", "orchestral")


@dataclass
class Note:
    start: float  # beats
    length: float  # beats
    pitch: int  # MIDI
    velocity: float = 0.8


@dataclass
class Score:
    bpm: int
    bars: int
    tracks: dict[str, list[Note]] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


def _root_midi(key: str) -> int:
    key = key.strip().upper().replace("♯", "#").replace("♭", "B")
    name = key[:2] if len(key) > 1 and key[1] in "#B" else key[:1]
    if name not in NOTE_NAMES:
        raise ValueError(f"unknown key {key!r}")
    return 48 + NOTE_NAMES[name]


def _scale_pitch(root: int, mode: list[int], degree: int) -> int:
    octave, idx = divmod(degree, 7)
    return root + 12 * octave + mode[idx]


def compose(mood: str = "adventure", key: str = "C", bars: int = 16, bpm: int | None = None,
            seed: int = 1, mode: str | None = None) -> Score:
    if mood not in MOODS:
        raise ValueError(f"unknown mood {mood!r}; choose from {', '.join(MOODS)}")
    m = MOODS[mood]
    rng = random.Random(seed)
    scale = MODES[mode or m["mode"]]
    root = _root_midi(key)
    bars = max(4, min(64, bars - bars % 4 or 4))
    prog_a = rng.choice(m["progs"])
    prog_b = rng.choice(m["progs"])
    chords = [(prog_a if (b // 4) % 2 == 0 or bars <= 8 else prog_b)[b % 4] for b in range(bars)]
    score = Score(bpm=bpm or m["bpm"], bars=bars,
                  meta={"mood": mood, "key": key, "mode": mode or m["mode"], "progression": chords})

    score.tracks["melody"] = _melody(rng, root, scale, chords, m["density"])
    score.tracks["bass"] = _bass(rng, root, scale, chords, mood)
    score.tracks["pad"] = _pad(root, scale, chords, m.get("sevenths", False))
    if m["arp"]:
        score.tracks["arp"] = _arp(rng, root, scale, chords)
    score.tracks["drums"] = _drums(m["drums"], bars, rng)
    return score


def _chord_degrees(deg: int, sevenths: bool = False) -> list[int]:
    return [deg, deg + 2, deg + 4] + ([deg + 6] if sevenths else [])


def _melody(rng: random.Random, root: int, scale: list[int], chords: list[int], density: float) -> list[Note]:
    notes: list[Note] = []

    def phrase(bar0: int, motif: list[list[int]] | None, final: bool) -> list[list[int]]:
        cells = motif or [rng.choice(RHYTHMS) for _ in range(2)]
        cursor = 7 + rng.choice([0, 2, 4])  # degree in the octave above root
        for k in range(4):
            bar = bar0 + k
            cell = cells[k % 2] if k < 3 else ([8, 8] if final else rng.choice(RHYTHMS))
            chord = _chord_degrees(chords[bar])
            pos = 0
            for i, dur in enumerate(cell):
                strong = pos % 8 == 0
                if strong:  # land on a chord tone near the cursor
                    targets = [c + 7 * o for c in chord for o in (0, 1, 2)]
                    cursor = min(targets, key=lambda t: (abs(t - cursor), rng.random()))
                else:
                    cursor += rng.choice([-2, -1, -1, 1, 1, 2])
                cursor = max(4, min(16, cursor))
                last = final and k == 3 and i == len(cell) - 1
                deg = 7 if last else cursor
                if rng.random() < density or strong or last:
                    notes.append(Note(bar * 4 + pos / 4, dur / 4 * 0.92, _scale_pitch(root, scale, deg),
                                      0.9 if strong else 0.7))
                pos += dur
        return cells

    for start in range(0, len(chords), 8):
        motif = phrase(start, None, False)
        if start + 4 < len(chords):
            phrase(start + 4, motif, True)
    return notes


def _bass(rng: random.Random, root: int, scale: list[int], chords: list[int], mood: str) -> list[Note]:
    patterns = {
        "boss": [(0, .5), (.5, .5), (1, .5), (1.5, .5), (2, .5), (2.5, .5), (3, .5), (3.5, .5)],
        "tense": [(0, .5), (.5, .5), (1, .5), (1.5, .5), (2, .5), (2.5, .5), (3, .5), (3.5, .5)],
        "sad": [(0, 2), (2, 2)], "chill": [(0, 1.5), (1.5, .5), (2, 2)], "mysterious": [(0, 3), (3, 1)],
        "spooky": [(0, 2), (2, 1), (3, 1)],
    }
    pat = patterns.get(mood, [(0, 1), (1, .5), (1.5, .5), (2, 1), (3, .5), (3.5, .5)])
    notes = []
    for bar, deg in enumerate(chords):
        base = _scale_pitch(root - 12, scale, deg)
        fifth = _scale_pitch(root - 12, scale, deg + 4)
        for i, (beat, length) in enumerate(pat):
            pitch = fifth if (i % 4 == 3 and rng.random() < 0.6) else base
            notes.append(Note(bar * 4 + beat, length * 0.9, pitch, 0.85))
    return notes


def _pad(root: int, scale: list[int], chords: list[int], sevenths: bool) -> list[Note]:
    return [Note(bar * 4, 4, _scale_pitch(root, scale, d), 0.5)
            for bar, deg in enumerate(chords) for d in _chord_degrees(deg, sevenths)]


def _arp(rng: random.Random, root: int, scale: list[int], chords: list[int]) -> list[Note]:
    shape = rng.choice([[0, 1, 2, 1], [0, 1, 2, 3], [0, 2, 1, 2], [2, 1, 0, 1]])
    notes = []
    for bar, deg in enumerate(chords):
        tones = [_scale_pitch(root + 12, scale, d) for d in _chord_degrees(deg)] + \
                [_scale_pitch(root + 24, scale, deg)]
        for step in range(8):
            notes.append(Note(bar * 4 + step * 0.5, 0.4, tones[shape[step % 4]], 0.45))
    return notes


def _drums(style: str, bars: int, rng: random.Random) -> list[Note]:
    kick_snare, hats = DRUMS[style]
    gm = {"K": 36, "S": 38, "H": 42, "O": 46}
    notes = []
    for bar in range(bars):
        fill = bar % 4 == 3 and rng.random() < 0.6
        for step in range(16):
            beat = bar * 4 + step / 4
            for lane in (kick_snare, hats):
                ch = lane[step]
                if ch != ".":
                    notes.append(Note(beat, 0.25, gm[ch], 0.9 if ch in "KS" else 0.5))
            if fill and step >= 12 and step % 2 == 0:
                notes.append(Note(beat, 0.25, 38, 0.7))
    return notes


# ---------------------------------------------------------------------------- rendering

def _midi_hz(p: int) -> float:
    return 440.0 * 2 ** ((p - 69) / 12)


_TABLE = 2048


def _table(kind: str) -> list[float]:
    """One cycle of each oscillator, sampled once; notes then cost one lookup per sample."""
    t = [i / _TABLE for i in range(_TABLE)]
    if kind == "pulse25":
        return [0.5 if x < 0.25 else -0.5 for x in t]
    if kind == "pulse50":
        return [0.5 if x < 0.5 else -0.5 for x in t]
    if kind == "triangle":  # 4-bit stepped like the NES
        return [(round((1 - abs(x * 2 - 1)) * 15) / 15 - 0.5) * 1.2 for x in t]
    if kind == "saw":
        return [sum(math.sin(2 * math.pi * h * x) / h for h in range(1, 24)) * -0.55 for x in t]
    if kind == "sine":
        return [math.sin(2 * math.pi * x) + 0.15 * math.sin(4 * math.pi * x) for x in t]
    if kind == "strings":
        return [sum(math.sin(2 * math.pi * h * x) / h ** 1.3 for h in range(1, 9)) * 0.6 for x in t]
    raise ValueError(kind)


_TABLES = {k: _table(k) for k in ("pulse25", "pulse50", "triangle", "saw", "sine", "strings")}
_DETUNED = {"saw": 1.006, "strings": 1.004}


def _osc(kind: str, f: float, n: int) -> list[float]:
    table = _TABLES[kind]
    inc = f * _TABLE / RATE
    mask = _TABLE - 1
    out = [table[int(i * inc) & mask] for i in range(n)]
    if kind in _DETUNED:  # a second, slightly sharp voice gives saws and strings their width
        inc2 = inc * _DETUNED[kind]
        out = [(a + table[int(i * inc2) & mask]) * 0.5 for i, a in enumerate(out)]
    return out


def _adsr(buf: list[float], a: float, d: float, s: float, r: float) -> list[float]:
    n = len(buf)
    na, nd, nr = int(a * RATE), int(d * RATE), int(r * RATE)
    out = []
    for i, x in enumerate(buf):
        if i < na:
            g = i / max(1, na)
        elif i < na + nd:
            g = 1 - (1 - s) * (i - na) / max(1, nd)
        else:
            g = s
        if i > n - nr:
            g *= max(0.0, (n - i) / max(1, nr))
        out.append(x * g)
    return out


def _drum_hit(pitch: int, rng: random.Random, style: str) -> list[float]:
    if pitch == 36:
        n, ph, out = int(RATE * 0.25), 0.0, []
        for i in range(n):
            ph += 2 * math.pi * (50 + 120 * math.exp(-i / (RATE * 0.03))) / RATE
            out.append(math.sin(ph) * math.exp(-i / (RATE * 0.08)))
        return out
    if pitch == 38:
        n = int(RATE * 0.18)
        noise = dsp.white_noise(n, rng)
        if style == "chiptune":
            noise = dsp.bitcrush(noise, 4, 4)
        return [(s * 0.7 + 0.4 * math.sin(2 * math.pi * 190 * i / RATE)) * math.exp(-i / (RATE * 0.05))
                for i, s in enumerate(noise)]
    n = int(RATE * (0.25 if pitch == 46 else 0.05))
    noise = dsp.highpass(dsp.white_noise(n, rng), 6000, RATE)
    return [s * math.exp(-i / (n * 0.3)) * 0.5 for i, s in enumerate(noise)]


INSTRUMENTS = {  # style -> track -> (osc, attack, decay, sustain, release, gain, pan)
    "chiptune": {"melody": ("pulse25", .005, .1, .6, .03, .30, .45), "bass": ("triangle", .002, .05, .9, .02, .45, .5),
                 "pad": ("pulse50", .01, .2, .3, .05, .05, .5), "arp": ("pulse50", .002, .05, .4, .02, .10, .6)},
    "synthwave": {"melody": ("saw", .01, .15, .7, .1, .22, .45), "bass": ("saw", .005, .1, .8, .05, .30, .5),
                  "pad": ("saw", .3, .5, .7, .4, .06, .5), "arp": ("pulse25", .002, .08, .3, .05, .08, .65)},
    "ambient": {"melody": ("sine", .05, .3, .6, .4, .30, .45), "bass": ("sine", .05, .2, .8, .2, .40, .5),
                "pad": ("strings", .8, .5, .8, .8, .10, .5), "arp": ("sine", .01, .2, .2, .2, .08, .6)},
    "orchestral": {"melody": ("strings", .04, .2, .8, .2, .28, .4), "bass": ("strings", .03, .2, .8, .2, .35, .55),
                   "pad": ("strings", .4, .5, .7, .5, .08, .5), "arp": ("sine", .005, .1, .3, .1, .10, .65)},
}


def render(score: Score, style: str = "chiptune", seed: int = 1) -> tuple[list[float], list[float]]:
    """Render to a stereo loop. Reverb/release tails are folded onto the start so the file loops
    sample-accurately."""
    if style not in INSTRUMENTS:
        raise ValueError(f"unknown style {style!r}; choose from {', '.join(STYLES)}")
    rng = random.Random(seed)
    spb = 60 / score.bpm
    loop_len = int(score.bars * 4 * spb * RATE)
    left, right = [0.0] * loop_len, [0.0] * loop_len
    drum_cache: dict[int, list[float]] = {}
    note_cache: dict[tuple, list[float]] = {}
    for name, notes in score.tracks.items():
        if name == "drums":
            for note in notes:
                if note.pitch not in drum_cache:
                    drum_cache[note.pitch] = _drum_hit(note.pitch, rng, style)
                hit = drum_cache[note.pitch]
                off = int(note.start * spb * RATE)
                gain = note.velocity * (0.55 if note.pitch == 36 else 0.35)
                dsp.mix_into(left, hit, off, gain)
                dsp.mix_into(right, hit, off, gain * (0.85 if note.pitch in (42, 46) else 1))
            continue
        osc, a, d, s, r, gain, pan = INSTRUMENTS[style][name]
        for note in notes:
            n = int((note.length * spb + r) * RATE)
            key = (osc, note.pitch, n)
            if key not in note_cache:
                note_cache[key] = _adsr(_osc(osc, _midi_hz(note.pitch), n), a, d, s, r)
            buf = note_cache[key]
            off = int(note.start * spb * RATE)
            g = gain * note.velocity
            dsp.mix_into(left, buf, off, g * (1 - pan) * 2)
            dsp.mix_into(right, buf, off, g * pan * 2)
    room = {"chiptune": 0.2, "synthwave": 0.5, "ambient": 0.9, "orchestral": 0.7}[style]
    wet = {"chiptune": 0.15, "synthwave": 0.3, "ambient": 0.6, "orchestral": 0.45}[style]
    # one reverb on the mid signal, added back to both sides: half the cost of two, same space
    tail = dsp.reverb_wet([(a + b) * 0.5 for a, b in zip(left, right)], room, RATE)
    pad = [0.0] * (len(tail) - loop_len)
    left = [a + w * wet for a, w in zip(left + pad, tail)]
    right = [b + w * wet * 0.9 for b, w in zip(right + pad, tail)]
    left, right = _fold(left, loop_len), _fold(right, loop_len)
    peak = max(max(abs(x) for x in left), max(abs(x) for x in right), 1e-9)
    g = 0.89 / peak
    return [math.tanh(x * g * 1.1) for x in left], [math.tanh(x * g * 1.1) for x in right]


def _fold(buf: list[float], loop_len: int) -> list[float]:
    out = buf[:loop_len] + [0.0] * max(0, loop_len - len(buf))
    for i, s in enumerate(buf[loop_len:]):
        out[i % loop_len] += s
    return out


# ---------------------------------------------------------------------------- MIDI export

GM_PROGRAMS = {"chiptune": {"melody": 80, "bass": 38, "pad": 81, "arp": 80},
               "synthwave": {"melody": 81, "bass": 38, "pad": 89, "arp": 80},
               "ambient": {"melody": 88, "bass": 32, "pad": 91, "arp": 98},
               "orchestral": {"melody": 40, "bass": 42, "pad": 48, "arp": 46}}


def write_midi(score: Score, path: str | Path, style: str = "chiptune") -> Path:
    """Standard MIDI File, type 1: tempo track + one track per part, drums on channel 10."""
    tpq = 480
    tracks = [_vlq(0) + b"\xff\x51\x03" + struct.pack(">I", int(60_000_000 / score.bpm))[1:]
              + _vlq(0) + b"\xff\x58\x04\x04\x02\x18\x08"]
    progs = GM_PROGRAMS.get(style, GM_PROGRAMS["chiptune"])
    channel = 0
    for name, notes in score.tracks.items():
        ch = 9 if name == "drums" else channel
        if name != "drums":
            channel += 1
        events: list[tuple[int, int, bytes]] = []
        for nt in notes:
            on = int(nt.start * tpq)
            off = int((nt.start + nt.length) * tpq)
            vel = max(1, min(127, int(nt.velocity * 127)))
            events.append((on, 1, bytes([0x90 | ch, nt.pitch, vel])))
            events.append((off, 0, bytes([0x80 | ch, nt.pitch, 0])))
        events.sort(key=lambda e: (e[0], e[1]))
        data = _vlq(0) + b"\xff\x03" + _vlq(len(name)) + name.encode()
        if name != "drums":
            data += _vlq(0) + bytes([0xC0 | ch, progs.get(name, 0)])
        t = 0
        for tick, _, msg in events:
            data += _vlq(tick - t) + msg
            t = tick
        tracks.append(data)
    out = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), tpq)
    for tr in tracks:
        tr += _vlq(0) + b"\xff\x2f\x00"
        out += b"MTrk" + struct.pack(">I", len(tr)) + tr
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out)
    return path


def _vlq(v: int) -> bytes:
    buf = [v & 0x7F]
    v >>= 7
    while v:
        buf.append((v & 0x7F) | 0x80)
        v >>= 7
    return bytes(reversed(buf))

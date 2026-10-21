"""Sound effects: an sfxr-compatible synthesizer, its classic generators, layered presets sfxr cannot
make (footsteps, whooshes, magic, impacts), and seeded variations so a game never plays the exact
same coin twice.

Parameters use the sfxr/jsfxr names and ranges, so a preset tuned in jsfxr pastes in unchanged.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, fields

from . import dsp

SQUARE, SAW, SINE, NOISE = 0, 1, 2, 3
WAVE_NAMES = {"square": SQUARE, "saw": SAW, "sawtooth": SAW, "sine": SINE, "noise": NOISE}


@dataclass
class SfxrParams:
    wave_type: int = SQUARE
    env_attack: float = 0.0
    env_sustain: float = 0.3
    env_punch: float = 0.0
    env_decay: float = 0.4
    base_freq: float = 0.3
    freq_limit: float = 0.0
    freq_ramp: float = 0.0
    freq_dramp: float = 0.0
    vib_strength: float = 0.0
    vib_speed: float = 0.0
    arp_mod: float = 0.0
    arp_speed: float = 0.0
    duty: float = 0.0
    duty_ramp: float = 0.0
    repeat_speed: float = 0.0
    pha_offset: float = 0.0
    pha_ramp: float = 0.0
    lpf_freq: float = 1.0
    lpf_ramp: float = 0.0
    lpf_resonance: float = 0.0
    hpf_freq: float = 0.0
    hpf_ramp: float = 0.0
    sound_vol: float = 0.5

    @classmethod
    def from_dict(cls, data: dict) -> "SfxrParams":
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in data.items() if k in known}
        if isinstance(clean.get("wave_type"), str):
            clean["wave_type"] = WAVE_NAMES[clean["wave_type"].lower()]
        return cls(**clean)

    def to_dict(self) -> dict:
        return asdict(self)


def synth(p: SfxrParams, rng: random.Random, max_seconds: float = 4.0) -> list[float]:
    """Render sfxr parameters at 44.1 kHz with 8x supersampling (the reference algorithm)."""
    state = _FreqState(p)
    square_duty = 0.5 - p.duty * 0.5
    square_slide = -p.duty_ramp * 0.00005
    rep_limit = int((1 - p.repeat_speed) ** 2 * 20000 + 32) if p.repeat_speed else 0
    rep_time = 0

    fltp = fltdp = fltphp = 0.0
    fltw = p.lpf_freq ** 3 * 0.1
    fltw_d = 1 + p.lpf_ramp * 0.0001
    fltdmp = min(0.8, 5 / (1 + p.lpf_resonance ** 2 * 20) * (0.01 + fltw))
    flthp = p.hpf_freq ** 2 * 0.1
    flthp_d = 1 + p.hpf_ramp * 0.0003

    vib_phase, vib_speed, vib_amp = 0.0, p.vib_speed ** 2 * 0.01, p.vib_strength * 0.5
    env_length = [max(1, int(p.env_attack ** 2 * 100000)), max(1, int(p.env_sustain ** 2 * 100000)),
                  max(1, int(p.env_decay ** 2 * 100000))]
    env_stage = env_time = 0
    fphase = p.pha_offset ** 2 * 1020 * (-1 if p.pha_offset < 0 else 1)
    fdphase = p.pha_ramp ** 2 * (-1 if p.pha_ramp < 0 else 1)
    phaser = [0.0] * 1024
    ipp = 0
    noise = [rng.uniform(-1, 1) for _ in range(32)]
    phase = 0
    out: list[float] = []
    limit = int(max_seconds * dsp.RATE)

    while len(out) < limit:
        rep_time += 1
        if rep_limit and rep_time >= rep_limit:
            rep_time = 0
            state.reset(p)
        state.arp_time += 1
        if state.arp_limit and state.arp_time >= state.arp_limit:
            state.arp_limit = 0
            state.fperiod *= state.arp_mod
        state.fslide += state.fdslide
        state.fperiod *= state.fslide
        if state.fperiod > state.fmaxperiod:
            state.fperiod = state.fmaxperiod
            if p.freq_limit > 0:
                break
        rfperiod = state.fperiod
        if vib_amp > 0:
            vib_phase += vib_speed
            rfperiod = state.fperiod * (1 + math.sin(vib_phase) * vib_amp)
        period = max(8, int(rfperiod))
        square_duty = min(0.5, max(0.0, square_duty + square_slide))

        env_time += 1
        if env_time > env_length[env_stage]:
            env_time = 0
            env_stage += 1
            if env_stage == 3:
                break
        if env_stage == 0:
            env_vol = env_time / env_length[0]
        elif env_stage == 1:
            env_vol = 1 + (1 - env_time / env_length[1]) * 2 * p.env_punch
        else:
            env_vol = 1 - env_time / env_length[2]

        fphase += fdphase
        iphase = min(1023, abs(int(fphase)))
        if flthp_d != 1:
            flthp = min(0.1, max(0.00001, flthp * flthp_d))

        ssample = 0.0
        for _ in range(8):
            phase += 1
            if phase >= period:
                phase %= period
                if p.wave_type == NOISE:
                    noise = [rng.uniform(-1, 1) for _ in range(32)]
            fp = phase / period
            if p.wave_type == SQUARE:
                sample = 0.5 if fp < square_duty else -0.5
            elif p.wave_type == SAW:
                sample = 1 - fp * 2
            elif p.wave_type == SINE:
                sample = math.sin(fp * 2 * math.pi)
            else:
                sample = noise[int(phase * 32 / period) % 32]
            pp = fltp
            fltw = min(0.1, max(0.0, fltw * fltw_d))
            if p.lpf_freq != 1:
                fltdp += (sample - fltp) * fltw
                fltdp -= fltdp * fltdmp
            else:
                fltp, fltdp = sample, 0.0
            fltp += fltdp
            fltphp += fltp - pp
            fltphp -= fltphp * flthp
            sample = fltphp
            phaser[ipp & 1023] = sample
            sample += phaser[(ipp - iphase + 1024) & 1023]
            ipp = (ipp + 1) & 1023
            ssample += sample * env_vol
        out.append(max(-1.0, min(1.0, ssample / 8 * 2 * p.sound_vol)))
    return out


class _FreqState:
    """The frequency/arpeggio registers sfxr re-initialises on every repeat."""

    def __init__(self, p: SfxrParams) -> None:
        self.reset(p)

    def reset(self, p: SfxrParams) -> None:
        self.fperiod = 100 / (p.base_freq ** 2 + 0.001)
        self.fmaxperiod = 100 / (p.freq_limit ** 2 + 0.001)
        self.fslide = 1 - p.freq_ramp ** 3 * 0.01
        self.fdslide = -p.freq_dramp ** 3 * 0.000001
        self.arp_mod = 1 - p.arp_mod ** 2 * 0.9 if p.arp_mod >= 0 else 1 + p.arp_mod ** 2 * 10
        self.arp_time = 0
        self.arp_limit = 0 if p.arp_speed == 1 else int((1 - p.arp_speed) ** 2 * 20000 + 32)


# ---------------------------------------------------------------------------- sfxr generators

def _gen_coin(r: random.Random) -> SfxrParams:
    p = SfxrParams(base_freq=0.4 + r.uniform(0, 0.5), env_sustain=r.uniform(0, 0.1),
                   env_decay=0.1 + r.uniform(0, 0.4), env_punch=0.3 + r.uniform(0, 0.3))
    if r.random() < 0.5:
        p.arp_speed, p.arp_mod = 0.5 + r.uniform(0, 0.2), 0.2 + r.uniform(0, 0.4)
    return p


def _gen_laser(r: random.Random) -> SfxrParams:
    p = SfxrParams(wave_type=r.choice([SQUARE, SAW, SINE]))
    if p.wave_type == SINE and r.random() < 0.5:
        p.wave_type = r.choice([SQUARE, SAW])
    p.base_freq = 0.5 + r.uniform(0, 0.5)
    p.freq_limit = max(0.2, p.base_freq - 0.2 - r.uniform(0, 0.6))
    p.freq_ramp = -0.15 - r.uniform(0, 0.2)
    if r.randint(0, 2) == 0:
        p.base_freq, p.freq_limit, p.freq_ramp = 0.3 + r.uniform(0, 0.6), r.uniform(0, 0.1), -0.35 - r.uniform(0, 0.3)
    if r.random() < 0.5:
        p.duty, p.duty_ramp = r.uniform(0, 0.5), r.uniform(0, 0.2)
    else:
        p.duty, p.duty_ramp = 0.4 + r.uniform(0, 0.5), -r.uniform(0, 0.7)
    p.env_sustain, p.env_decay = 0.1 + r.uniform(0, 0.2), r.uniform(0, 0.4)
    if r.random() < 0.5:
        p.env_punch = r.uniform(0, 0.3)
    if r.randint(0, 2) == 0:
        p.pha_offset, p.pha_ramp = r.uniform(0, 0.2), -r.uniform(0, 0.2)
    if r.random() < 0.5:
        p.hpf_freq = r.uniform(0, 0.3)
    return p


def _gen_explosion(r: random.Random) -> SfxrParams:
    p = SfxrParams(wave_type=NOISE)
    if r.random() < 0.5:
        p.base_freq, p.freq_ramp = 0.1 + r.uniform(0, 0.4), -0.1 + r.uniform(0, 0.4)
    else:
        p.base_freq, p.freq_ramp = 0.2 + r.uniform(0, 0.7), -0.2 - r.uniform(0, 0.2)
    p.base_freq *= p.base_freq
    if r.randint(0, 4) == 0:
        p.freq_ramp = 0.0
    if r.randint(0, 2) == 0:
        p.repeat_speed = 0.3 + r.uniform(0, 0.5)
    p.env_sustain, p.env_decay = 0.1 + r.uniform(0, 0.3), r.uniform(0, 0.5)
    if r.random() < 0.5:
        p.pha_offset, p.pha_ramp = -0.3 + r.uniform(0, 0.9), -r.uniform(0, 0.3)
    p.env_punch = 0.2 + r.uniform(0, 0.6)
    if r.random() < 0.5:
        p.vib_strength, p.vib_speed = r.uniform(0, 0.7), r.uniform(0, 0.6)
    if r.randint(0, 2) == 0:
        p.arp_speed, p.arp_mod = 0.6 + r.uniform(0, 0.3), 0.8 - r.uniform(0, 1.6)
    return p


def _gen_powerup(r: random.Random) -> SfxrParams:
    p = SfxrParams()
    if r.random() < 0.5:
        p.wave_type = SAW
    else:
        p.duty = r.uniform(0, 0.6)
    p.base_freq = 0.2 + r.uniform(0, 0.3)
    if r.random() < 0.5:
        p.freq_ramp, p.repeat_speed = 0.1 + r.uniform(0, 0.4), 0.4 + r.uniform(0, 0.4)
    else:
        p.freq_ramp = 0.05 + r.uniform(0, 0.2)
        if r.random() < 0.5:
            p.vib_strength, p.vib_speed = r.uniform(0, 0.7), r.uniform(0, 0.6)
    p.env_sustain, p.env_decay = r.uniform(0, 0.4), 0.1 + r.uniform(0, 0.4)
    return p


def _gen_hit(r: random.Random) -> SfxrParams:
    p = SfxrParams(wave_type=r.choice([SQUARE, SAW, SINE]))
    if p.wave_type == SINE:
        p.wave_type = NOISE
    if p.wave_type == SQUARE:
        p.duty = r.uniform(0, 0.6)
    p.base_freq, p.freq_ramp = 0.2 + r.uniform(0, 0.6), -0.3 - r.uniform(0, 0.4)
    p.env_sustain, p.env_decay = r.uniform(0, 0.1), 0.1 + r.uniform(0, 0.2)
    if r.random() < 0.5:
        p.hpf_freq = r.uniform(0, 0.3)
    return p


def _gen_jump(r: random.Random) -> SfxrParams:
    p = SfxrParams(duty=r.uniform(0, 0.6), base_freq=0.3 + r.uniform(0, 0.3), freq_ramp=0.1 + r.uniform(0, 0.2),
                   env_sustain=0.1 + r.uniform(0, 0.3), env_decay=0.1 + r.uniform(0, 0.2))
    if r.random() < 0.5:
        p.hpf_freq = r.uniform(0, 0.3)
    if r.random() < 0.5:
        p.lpf_freq = 1 - r.uniform(0, 0.6)
    return p


def _gen_blip(r: random.Random) -> SfxrParams:
    p = SfxrParams(wave_type=r.choice([SQUARE, SAW]), base_freq=0.2 + r.uniform(0, 0.4),
                   env_sustain=0.1 + r.uniform(0, 0.1), env_decay=r.uniform(0, 0.2), hpf_freq=0.1)
    if p.wave_type == SQUARE:
        p.duty = r.uniform(0, 0.6)
    return p


SFXR_GENERATORS = {
    "coin": _gen_coin, "pickup": _gen_coin, "laser": _gen_laser, "shoot": _gen_laser,
    "explosion": _gen_explosion, "powerup": _gen_powerup, "hit": _gen_hit, "hurt": _gen_hit,
    "jump": _gen_jump, "blip": _gen_blip, "select": _gen_blip,
}


# ---------------------------------------------------------------------------- layered presets

def _footstep(r: random.Random) -> list[float]:
    n = int(dsp.RATE * (0.09 + r.uniform(0, 0.05)))
    body = dsp.bandpass(dsp.white_noise(n, r), 120 + r.uniform(0, 200), 900 + r.uniform(0, 1400))
    env = [math.exp(-i / (n * 0.18)) for i in range(n)]
    thump = [math.sin(2 * math.pi * (70 + r.uniform(0, 30)) * i / dsp.RATE) * math.exp(-i / (n * 0.12))
             for i in range(n)]
    return dsp.normalize([b * e * 1.4 + t * 0.6 for b, e, t in zip(body, env, thump)], 0.8)


def _whoosh(r: random.Random) -> list[float]:
    n = int(dsp.RATE * (0.35 + r.uniform(0, 0.3)))
    noise = dsp.white_noise(n, r)
    out, y, low = [], 0.0, 0.0
    for i, s in enumerate(noise):
        t = i / n
        cutoff = 300 + 5200 * math.sin(math.pi * t) ** 2
        a = 1 - math.exp(-2 * math.pi * cutoff / dsp.RATE)
        y += a * (s - y)
        low += 0.02 * (y - low)
        out.append((y - low) * math.sin(math.pi * t) ** 1.5)
    return dsp.normalize(out, 0.8)


def _magic(r: random.Random) -> list[float]:
    root = r.choice([523.25, 587.33, 659.25, 698.46])
    steps = r.choice([[0, 4, 7, 12, 16], [0, 3, 7, 10, 15], [0, 5, 7, 12, 19]])
    out: list[float] = []
    note_len = int(dsp.RATE * 0.06)
    for k, st in enumerate(steps):
        f = root * 2 ** (st / 12)
        tone = [(math.sin(2 * math.pi * f * i / dsp.RATE) + 0.3 * math.sin(4 * math.pi * f * i / dsp.RATE))
                * math.exp(-i / (dsp.RATE * 0.25)) for i in range(int(dsp.RATE * 0.5))]
        dsp.mix_into(out, tone, k * note_len, 0.4)
    shimmer = dsp.tremolo(out, 18, 0.4)
    return dsp.normalize(dsp.reverb(shimmer, 0.7, 0.6), 0.8)


def _thud(r: random.Random) -> list[float]:
    n = int(dsp.RATE * 0.45)
    f0 = 90 + r.uniform(0, 40)
    ph, body = 0.0, []
    for i in range(n):
        f = f0 * (1 + 2.5 * math.exp(-i / (dsp.RATE * 0.02)))
        ph += 2 * math.pi * f / dsp.RATE
        body.append(math.sin(ph) * math.exp(-i / (dsp.RATE * 0.12)))
    crack = dsp.lowpass(dsp.white_noise(int(dsp.RATE * 0.04), r), 2500)
    crack = [c * math.exp(-i / 300) for i, c in enumerate(crack)]
    dsp.mix_into(body, crack, 0, 0.6)
    return dsp.normalize(dsp.distort(body, 2.0), 0.85)


def _ui_click(r: random.Random) -> list[float]:
    n = int(dsp.RATE * 0.03)
    f = 1800 + r.uniform(0, 1200)
    return dsp.normalize([math.sin(2 * math.pi * f * i / dsp.RATE) * math.exp(-i / (n * 0.2)) for i in range(n)], 0.6)


def _alarm(r: random.Random) -> list[float]:
    out, ph = [], 0.0
    hi, lo = 880 + r.uniform(0, 200), 660 + r.uniform(0, 100)
    for i in range(int(dsp.RATE * 1.2)):
        f = hi if (i // int(dsp.RATE * 0.15)) % 2 == 0 else lo
        ph += 2 * math.pi * f / dsp.RATE
        out.append(0.5 if math.sin(ph) > 0 else -0.5)
    return dsp.normalize(dsp.lowpass(out, 4000), 0.7)


def _heal(r: random.Random) -> list[float]:
    out, ph = [], 0.0
    n = int(dsp.RATE * 0.8)
    for i in range(n):
        t = i / n
        f = 400 * 2 ** (t * 1.5) * (1 + 0.01 * math.sin(2 * math.pi * 6 * i / dsp.RATE))
        ph += 2 * math.pi * f / dsp.RATE
        out.append((math.sin(ph) + 0.25 * math.sin(3 * ph)) * math.sin(math.pi * t))
    return dsp.normalize(dsp.reverb(out, 0.5, 0.4), 0.8)


LAYERED = {
    "footstep": _footstep, "whoosh": _whoosh, "swing": _whoosh, "magic": _magic, "spell": _magic,
    "thud": _thud, "impact": _thud, "ui_click": _ui_click, "click": _ui_click, "alarm": _alarm,
    "heal": _heal,
}

PRESETS = sorted({*SFXR_GENERATORS, *LAYERED})


def mutate(p: SfxrParams, r: random.Random, amount: float = 0.05) -> SfxrParams:
    """sfxr's 'mutate': nudge every continuous parameter, keeping the sound's identity."""
    data = p.to_dict()
    for key, value in data.items():
        if key in ("wave_type", "sound_vol") or not isinstance(value, float):
            continue
        if r.random() < 0.5:
            lo = -1.0 if key in ("freq_ramp", "freq_dramp", "duty_ramp", "pha_offset", "pha_ramp",
                                 "lpf_ramp", "hpf_ramp", "arp_mod") else 0.0
            data[key] = max(lo, min(1.0, value + r.uniform(-amount, amount)))
    return SfxrParams.from_dict(data)


def polish(buf: list[float], style: str) -> list[float]:
    """``retro`` keeps the raw chip sound; ``modern`` softens, adds space; ``crunchy`` bitcrushes."""
    if style == "modern":
        return dsp.normalize(dsp.reverb(dsp.lowpass(buf, 9000), 0.3, 0.3), 0.85)
    if style == "crunchy":
        return dsp.normalize(dsp.bitcrush(buf, 5, 3), 0.85)
    if style == "distant":
        return dsp.normalize(dsp.reverb(dsp.lowpass(buf, 1800), 0.8, 0.8), 0.5)
    return dsp.normalize(buf, 0.85)


def render(preset: str, seed: int, params: dict | None = None, style: str = "retro",
           variation: int = 0) -> tuple[list[float], dict]:
    """One sound. Returns the buffer and the recipe needed to reproduce it exactly."""
    preset = preset.lower()
    rng = random.Random(seed)
    recipe: dict = {"preset": preset, "seed": seed, "style": style, "variation": variation}
    if preset in LAYERED and not params:
        buf = LAYERED[preset](random.Random(seed * 7919 + variation))
        return polish(buf, style), recipe
    if params:
        base = SfxrParams.from_dict({**(SFXR_GENERATORS.get(preset, lambda r: SfxrParams())(rng).to_dict()
                                        if preset in SFXR_GENERATORS else {}), **params})
    elif preset in SFXR_GENERATORS:
        base = SFXR_GENERATORS[preset](rng)
    else:
        raise ValueError(f"unknown preset {preset!r}; choose from {', '.join(PRESETS)}")
    if variation:
        base = mutate(base, random.Random(seed * 104729 + variation))
    buf = synth(base, random.Random(seed + variation))
    recipe["sfxr"] = base.to_dict()
    return polish(buf, style), recipe

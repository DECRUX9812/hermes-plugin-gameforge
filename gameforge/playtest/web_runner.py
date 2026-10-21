"""Plays a web build like a person would and reports where it breaks or gets boring.

Policies:
  * ``explorer`` — holds directions toward unvisited ground, re-routes when blocked, uses the action
    key near trouble, restarts after game over. Uses ``window.__gameforge`` telemetry when the game
    publishes it and falls back to pure pixels (novelty-seeking) when it doesn't.
  * ``monkey``   — random input chaos; finds crashes, not design problems.
  * ``agent``    — a vision LLM (the user's configured model via Hermes) looks at the screen every few
    seconds, chooses inputs and writes observations like a human tester. Costs tokens; opt-in.

Signals: uncaught exceptions/console errors, FPS, input that changes nothing, getting stuck,
visual novelty over time (long low-novelty stretches = boring), deaths/wins/time-to-first-event.
"""

from __future__ import annotations

import io
import json
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageStat

from .cdp import Browser, find_browser
from .serve import StaticServer

# events the player causes directly; they are input, not the game responding, so they don't count as "something happened"
PLAYER_EVENTS = {"event:boot", "event:start", "event:attack", "event:jump", "event:input", "event:move"}
MOVES = ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"]
DIRS = {"ArrowUp": (0, -1), "ArrowDown": (0, 1), "ArrowLeft": (-1, 0), "ArrowRight": (1, 0)}

FPS_PROBE = """(() => { if (window.__gfProbe) return; window.__gfProbe = {n: 0, t: performance.now(), fps: 0};
const f = () => { const p = window.__gfProbe; p.n++; const now = performance.now();
if (now - p.t > 500) { p.fps = Math.round(p.n * 1000 / (now - p.t)); p.n = 0; p.t = now; } requestAnimationFrame(f); };
requestAnimationFrame(f); })()"""


@dataclass
class Moment:
    t: float
    kind: str
    note: str
    shot: str | None = None
    data: dict = field(default_factory=dict)


@dataclass
class Run:
    started: float
    samples: list[dict] = field(default_factory=list)
    moments: list[Moment] = field(default_factory=list)
    console: list[dict] = field(default_factory=list)
    agent_notes: list[dict] = field(default_factory=list)
    visited: dict[tuple[int, int], int] = field(default_factory=dict)
    positions: list[tuple[float, float]] = field(default_factory=list)


def _signature(img: Image.Image) -> Image.Image:
    return img.convert("L").resize((48, 36), Image.BILINEAR)


def _diff(a: Image.Image, b: Image.Image) -> float:
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0] / 255


class WebPlaytester:
    def __init__(self, target: str | Path, out_dir: Path, duration: float = 60.0, policy: str = "explorer",
                 seed: int = 0, browser: str | None = None, llm=None, goal: str = "", viewport=(960, 720)) -> None:
        self.target, self.out, self.duration, self.policy = target, out_dir, duration, policy
        self.rng = random.Random(seed)
        self.browser_bin = find_browser(browser)
        self.llm, self.goal, self.viewport = llm, goal, viewport
        self.held: set[str] = set()
        self.notes: list[str] = []
        self.walls: dict[tuple[int, int, str], float] = {}

    # ------------------------------------------------------------------ plumbing
    def _hold(self, keys: set[str]) -> None:
        for k in self.held - keys:
            self.b.key(k, False)
        for k in keys - self.held:
            self.b.key(k, True)
        self.held = set(keys)

    def _tap(self, key: str) -> None:
        self.b.key(key, True)
        time.sleep(0.05)
        self.b.key(key, False)

    def _shot(self, name: str | None = None) -> tuple[Image.Image, str | None]:
        raw = self.b.screenshot("jpeg", 70)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        if name:
            path = self.out / "shots" / f"{name}.jpg"
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(path, quality=85)
            return img, str(path.relative_to(self.out))
        return img, None

    def _telemetry(self) -> dict | None:
        return self.b.evaluate("window.__gameforge ? JSON.stringify({s: window.__gameforge.state, f: window.__gameforge.fps, "
                           "e: window.__gameforge.events.splice(0)}) : null")

    # ------------------------------------------------------------------ main
    def run(self) -> dict:
        if not self.browser_bin:
            raise RuntimeError("no Chrome/Chromium/Edge found; install one or pass 'browser' with its path")
        self.out.mkdir(parents=True, exist_ok=True)
        server = None
        if isinstance(self.target, Path) or not str(self.target).startswith(("http://", "https://")):
            root = Path(self.target)
            entry = root.name if root.is_file() else ""
            server = StaticServer(root.parent if root.is_file() else root)
            url = server.url + entry
        else:
            url = str(self.target)
        self.b = Browser(self.browser_bin, *self.viewport, start_url=url)
        try:
            return self._play(url)
        finally:
            self.b.close()
            if server:
                server.close()

    def _play(self, url: str) -> dict:
        run = Run(started=time.monotonic())
        self.b.evaluate(FPS_PROBE)
        load_deadline = time.monotonic() + 60
        while time.monotonic() < load_deadline:
            if self.b.evaluate("location.protocol !== 'about:' && document.readyState === 'complete'"):
                break
            time.sleep(0.25)
        else:
            raise RuntimeError(f"{url} did not finish loading within 60s")
        has_tel = False
        start = time.monotonic()
        while time.monotonic() - start < 15:  # wait out asset loading before pressing start
            scene0 = self.b.evaluate("window.__gameforge ? window.__gameforge.state.scene : null")
            has_tel = scene0 is not None
            if (has_tel and scene0 != "boot") or (not has_tel and time.monotonic() - start > 4
                                                   and self.b.evaluate("document.readyState") == "complete"):
                break
            time.sleep(0.25)
        run.started = time.monotonic()  # the clock measures play, not page load
        controls = (self.b.evaluate("JSON.stringify(window.__gameforge && window.__gameforge.controls || null)") or "null")
        controls = json.loads(controls) or {"move": MOVES, "action": ["Space"], "start": ["Enter"]}
        img, shot = self._shot("00_boot")
        run.moments.append(Moment(0, "boot", "first frame after load", shot))
        for k in controls.get("start", ["Enter"]):
            self._tap(k)
        self.b.click(self.viewport[0] / 2, self.viewport[1] / 2)
        time.sleep(0.4)

        sigs: list[Image.Image] = []
        last_sig = _signature(img)
        last_pos, still_since, direction, dir_until = None, None, None, 0.0
        last_change = time.monotonic()
        next_shot = 0.0
        next_agent = 0.0
        scene_prev = None
        deaths = wins = 0
        shots_taken = 1
        while time.monotonic() - run.started < self.duration:
            t = time.monotonic() - run.started
            tel = json.loads(self._telemetry() or "null") if has_tel else None
            state = (tel or {}).get("s") or {}
            fps = (tel or {}).get("f") or self.b.evaluate("window.__gfProbe && window.__gfProbe.fps") or 0
            for ev in (tel or {}).get("e", []):
                run.moments.append(Moment(round(t, 1), f"event:{ev.get('type')}", json.dumps(ev)[:160]))
                if ev.get("type") == "death":
                    deaths += 1
                if ev.get("type") == "win":
                    wins += 1

            sample = {"t": round(t, 2), "fps": fps, "scene": state.get("scene"), "held": sorted(self.held)}
            if t >= next_shot:
                img, _ = self._shot()
                sig = _signature(img)
                change = _diff(sig, last_sig)
                # novelty = distance to the closest screen seen more than ~5s ago ("have I been here before?")
                older = sigs[-130:-10]
                sigs.append(sig)
                last_sig = sig
                sample["change"] = round(change, 4)
                if older:
                    sample["novelty"] = round(min(_diff(sig, s) for s in older), 4)
                if change > 0.004:
                    last_change = time.monotonic()
                next_shot = t + 0.5
            if "score" in state:
                sample["score"] = state["score"]
            run.samples.append(sample)

            for c in self.b.drain_console():
                if "favicon" in str(c.get("url", "")):
                    continue
                run.console.append({**c, "t": round(t, 1)})
                if c["level"] == "exception" or c["level"] == "error":
                    _, s = self._shot(f"{shots_taken:02d}_error")
                    shots_taken += 1
                    run.moments.append(Moment(round(t, 1), "error", str(c.get("text"))[:200], s))

            scene = state.get("scene")
            if scene != scene_prev and scene in ("over", "win", "error"):
                _, s = self._shot(f"{shots_taken:02d}_{scene}")
                shots_taken += 1
                run.moments.append(Moment(round(t, 1), f"scene:{scene}", f"reached '{scene}' after {t:.0f}s", s))
                self._hold(set())
                time.sleep(1.2)
                for k in controls.get("start", ["Enter"]):
                    self._tap(k)
            scene_prev = scene
            if scene == "title":
                for k in controls.get("start", ["Enter"]):
                    self._tap(k)

            pos = (state.get("x"), state.get("y")) if state.get("x") is not None and state.get("y") is not None else None
            if pos and pos[0] is not None:
                run.positions.append(pos)
                cellk = (int(pos[0] // 48), int(pos[1] // 48))
                run.visited[cellk] = run.visited.get(cellk, 0) + 1
                if last_pos and math.dist(pos, last_pos) < 0.5 and any(k in MOVES for k in self.held):
                    still_since = still_since or t
                    if t - still_since > 4.0 and not any(m.kind == "stuck" and abs(m.t - t) < 8 for m in run.moments):
                        _, s = self._shot(f"{shots_taken:02d}_stuck")
                        shots_taken += 1
                        run.moments.append(Moment(round(t, 1), "stuck", f"no movement for {t - still_since:.1f}s while "
                                                  f"holding {sorted(self.held)} at {pos}", s, {"pos": pos}))
                else:
                    still_since = None
                last_pos = pos

            if (self.held and pos is None and time.monotonic() - last_change > 6.0 and scene in (None, "play")
                    and not any(m.kind == "frozen" and abs(m.t - t) < 10 for m in run.moments)):
                _, s = self._shot(f"{shots_taken:02d}_frozen")
                shots_taken += 1
                run.moments.append(Moment(round(t, 1), "frozen", "screen unchanged for 6s while input was held", s))

            # ---------------- choose inputs
            genre = (state.get("genre") or "") if isinstance(state, dict) else ""
            policy = self._effective_policy(genre)
            if policy == "agent" and self.llm is not None and t >= next_agent:
                self._agent_step(run, t, state, controls)
                next_agent = t + 4.0
            elif policy == "monkey":
                if self.rng.random() < 0.3:
                    self._hold({self.rng.choice(MOVES + controls.get("action", []))})
            elif policy in ("platformer", "arena", "roguelike"):
                self._genre_step(run, t, state, controls, policy, still_since)
            elif policy in ("explorer", "agent"):
                blocked = state.get("blocked", 0) > 0.25 or (still_since is not None and t - still_since > 0.6)
                if blocked and direction and pos and pos[0] is not None:
                    self.walls[(int(pos[0] // 48), int(pos[1] // 48), direction)] = t
                if direction is None or t > dir_until or blocked:
                    direction = self._pick_direction(run, pos, blocked, direction)
                    dir_until = t + self.rng.uniform(0.6, 1.8)
                keys = {direction}
                if self.rng.random() < 0.25:  # diagonal wiggle reads as a person, and gets round corners
                    keys.add(self.rng.choice([m for m in MOVES if DIRS[m][0] != DIRS[direction][0] or DIRS[m][1] != DIRS[direction][1]]))
                self._hold(keys)
                if self.rng.random() < 0.08:
                    for k in controls.get("action", []):
                        self._tap(k)
            if t > len([m for m in run.moments if m.kind == "periodic"]) * 15 + 15:
                _, s = self._shot(f"{shots_taken:02d}_t{int(t)}")
                shots_taken += 1
                run.moments.append(Moment(round(t, 1), "periodic", f"snapshot at {t:.0f}s", s))
            time.sleep(0.12)

        self._hold(set())
        _, s = self._shot(f"{shots_taken:02d}_end")
        run.moments.append(Moment(round(time.monotonic() - run.started, 1), "end", "session end", s))
        return self._report(run, has_tel, deaths, wins)

    def _effective_policy(self, genre: str) -> str:
        """``policy="auto"`` (and any genre-less run) resolves to the policy that fits the genre:
        a wanderer never finishes a platformer, so the same run should drive the right inputs."""
        if self.policy not in ("auto", ""):
            return self.policy
        return {"platformer": "platformer", "arena": "arena", "roguelike": "roguelike"}.get(genre, "explorer")

    def _genre_step(self, run: Run, t: float, state: dict, controls: dict, policy: str,
                    still_since: float | None = None) -> None:
        """Genre-shaped input: the difference between 'it moved' and 'it played the game'."""
        action = controls.get("action") or ["Space"]
        if policy == "platformer":
            # A tap-jump is cut short by the variable-jump-height rule (release = shorter hop), so
            # the bot HOLDS the jump key for the better part of a second: the same thing a player does.
            # The jump cadence is re-randomised every life: a fixed cadence against a fixed pit is a
            # deterministic death loop (same phase, same fall, forever).
            jump = action[0]
            deaths = state.get("deaths", 0)
            if deaths != getattr(self, "_pf_deaths", None):
                self._pf_deaths = deaths
                self._pf_gap = self.rng.uniform(0.34, 0.62)
                self._pf_hold, self._pf_cd = 0, 0
            p = state.get("progress", 0) or 0
            if p > getattr(self, "_pf_progress", -1):
                self._pf_progress, self._pf_moved = p, t
            stalled = t - getattr(self, "_pf_moved", t) > 0.8
            keys = {"ArrowRight"}
            if state.get("on_ground") and t >= getattr(self, "_pf_cd", 0) and (t >= getattr(self, "_pf_hold", 0) or stalled):
                self._pf_hold = t + 0.42          # hold long enough to reach full height
                self._pf_cd = t + getattr(self, "_pf_gap", 0.48)
                if stalled:
                    self._pf_moved = t            # give this jump a chance before re-triggering
            if t < getattr(self, "_pf_hold", 0):
                keys.add(jump)
            self._hold(keys)
        elif policy == "arena":
            if t >= getattr(self, "_ar_turn", 0) or state.get("hp", 9) < getattr(self, "_ar_hp", 9):
                self._ar_dir = self.rng.choice(["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"])
                self._ar_turn = t + self.rng.uniform(0.9, 1.7)
                self._ar_hp = state.get("hp", 9)
            self._hold({getattr(self, "_ar_dir", "ArrowRight")} | set(action))   # fire while moving
        else:  # roguelike
            blocked = state.get("blocked", 0) > 0.25 or (still_since is not None and t - still_since > 0.5)
            direction = getattr(self, "_rg_dir", None)
            if direction is None or t >= getattr(self, "_rg_turn", 0) or blocked:
                pos = (state.get("x"), state.get("y"))
                direction = self._pick_direction(run, pos, blocked, direction)
                self._rg_dir, self._rg_turn = direction, t + self.rng.uniform(0.7, 1.4)
            keys = {direction}
            if self.rng.random() < 0.15:
                keys.add(self.rng.choice([m for m in MOVES if m != direction]))
            self._hold(keys)
            if t >= getattr(self, "_rg_swing", 0):
                for k in action:
                    self._tap(k)
                self._rg_swing = t + 0.5

    def _pick_direction(self, run: Run, pos, blocked: bool, current: str | None) -> str:
        if pos and pos[0] is not None:
            cx, cy = int(pos[0] // 48), int(pos[1] // 48)
            scored = []
            for k, (dx, dy) in DIRS.items():
                seen = sum(run.visited.get((cx + dx * s, cy + dy * s), 0) for s in (1, 2, 3))
                penalty = 200 if (cx, cy, k) in self.walls else 0  # remembered dead ends (shores, cliffs)
                penalty += 50 if blocked and k == current else 0
                scored.append((seen + penalty + self.rng.random() * 6, k))
            return min(scored)[1]
        options = [m for m in MOVES if not (blocked and m == current)]
        return self.rng.choice(options)

    def _agent_step(self, run: Run, t: float, state: dict, controls: dict) -> None:
        img, _ = self._shot()
        buf = io.BytesIO()
        img.resize((480, 360)).save(buf, "JPEG", quality=70)
        keys = sorted(set(controls.get("move", MOVES) + controls.get("action", []) + controls.get("start", [])))
        schema = {"type": "object", "properties": {
            "keys": {"type": "array", "items": {"type": "string", "enum": keys}},
            "hold_ms": {"type": "integer"}, "observation": {"type": "string"},
            "issue": {"type": "string"}, "fun": {"type": "integer", "minimum": 1, "maximum": 5}},
            "required": ["keys", "hold_ms", "observation", "fun"]}
        try:
            res = self.llm.complete_structured(
                instructions=("You are a sharp game playtester. Look at the frame, decide which keys to hold next to make "
                              "progress, and note anything broken, confusing, unfair or boring. Be concrete. "
                              f"Goal: {self.goal or 'play the game naturally and try to win'}. Telemetry: {json.dumps(state)[:400]}"),
                input=[{"type": "image", "data": buf.getvalue(), "mime_type": "image/jpeg"},
                       {"type": "text", "text": f"t={t:.0f}s. Available keys: {keys}."}],
                json_schema=schema, schema_name="playtest_step", purpose="gameforge playtest", max_tokens=400)
            step = res.parsed or {}
        except Exception as exc:  # LLM unavailable mid-run: keep playing on the explorer policy
            self.notes.append(f"agent step failed at {t:.0f}s ({exc}); continuing with explorer moves")
            self.policy = "explorer"
            return
        run.agent_notes.append({"t": round(t, 1), **{k: step.get(k) for k in ("observation", "issue", "fun", "keys")}})
        if step.get("issue"):
            _, s = self._shot(f"agent_{int(t)}")
            run.moments.append(Moment(round(t, 1), "agent_issue", step["issue"], s))
        chosen = {k for k in step.get("keys", []) if k in keys}
        taps = chosen & set(controls.get("action", []) + controls.get("start", []))
        for k in taps:
            self._tap(k)
        self._hold(chosen - taps)

    # ------------------------------------------------------------------ analysis
    def _report(self, run: Run, has_tel: bool, deaths: int, wins: int) -> dict:
        dur = round(time.monotonic() - run.started, 1)
        fps = [s["fps"] for s in run.samples if s.get("fps")]
        nov = [(s["t"], s["novelty"]) for s in run.samples if "novelty" in s]
        events = [m for m in run.moments if m.kind.startswith("event:")]
        issues: list[dict] = []

        def issue(sev: str, title: str, detail: str, t: float | None = None, shot: str | None = None) -> None:
            issues.append({"severity": sev, "title": title, "detail": detail, "t": t, "shot": shot})

        stuck_at: set[tuple] = set()
        for m in run.moments:
            if m.kind == "error":
                issue("critical", "Runtime error", m.note, m.t, m.shot)
            elif m.kind == "scene:error":
                issue("critical", "Game entered its error screen", m.note, m.t, m.shot)
            elif m.kind == "stuck":
                where = tuple(round(c / 16) for c in m.data.get("pos", (0, 0)))
                crashed_before = any(e.kind == "error" and e.t <= m.t for e in run.moments)
                if where not in stuck_at and not crashed_before:  # a frozen crash is not also a level bug
                    stuck_at.add(where)
                    issue("major", "Player got stuck", m.note, m.t, m.shot)
            elif m.kind == "frozen":
                issue("major", "Input had no visible effect", m.note, m.t, m.shot)
            elif m.kind == "agent_issue":
                issue("minor", "Tester note", m.note, m.t, m.shot)
        if fps:
            low = sorted(fps)[max(0, len(fps) // 20)]
            if low < 30:
                issue("major", "Frame-rate drops", f"5th-percentile FPS {low} (avg {sum(fps) / len(fps):.0f})")
        if has_tel:
            game_times = [0.0] + [e.t for e in events if e.kind not in PLAYER_EVENTS] + [dur]
            for a, b in zip(game_times, game_times[1:]):
                if b - a >= 20:
                    issue("design", "Nothing happens", f"{a:.0f}s–{b:.0f}s: {b - a:.0f}s of play with no game event "
                          "(no pickup, fight, damage or progress)", a)
        boring = _low_novelty_stretches(nov, events)
        for start, end in boring:
            issue("design", "Low-novelty stretch (likely boring)",
                  f"{start:.0f}s–{end:.0f}s: the screen barely changed and nothing happened", start)
        hurt = sum(1 for e in events if e.kind == "event:hurt")
        first_event = next((e.t for e in events if e.kind not in PLAYER_EVENTS), None)
        if deaths and dur and deaths / (dur / 60) > 2:
            issue("design", "Possibly too hard", f"{deaths} deaths in {dur:.0f}s of play")
        if wins and not hurt and dur < 90:
            issue("design", "Possibly too easy", f"won {wins}x without taking damage")
        if first_event and first_event > 20:
            issue("design", "Slow start", f"first gameplay event only after {first_event:.0f}s")
        if not has_tel:
            self.notes.append("game publishes no window.__gameforge telemetry: deaths/score/stuck detection are pixel-only")
        order = {"critical": 0, "major": 1, "minor": 2, "design": 3}
        issues.sort(key=lambda i: (order[i["severity"]], i["t"] or 0))
        counts: dict[str, int] = {}
        for e in events:
            counts[e.kind[6:]] = counts.get(e.kind[6:], 0) + 1
        verdict = ("BROKEN" if any(i["severity"] == "critical" for i in issues) else
                   "ROUGH" if any(i["severity"] == "major" for i in issues) else
                   "PLAYABLE" if issues else "SOLID")
        report = {
            "verdict": verdict, "policy": self.policy, "duration_s": dur, "telemetry": has_tel,
            "fps": {"avg": round(sum(fps) / len(fps), 1) if fps else None, "min": min(fps) if fps else None,
                    "p5": sorted(fps)[max(0, len(fps) // 20)] if fps else None},
            "events": counts, "deaths": deaths, "wins": wins, "time_to_first_event_s": first_event,
            "coverage_cells": len(run.visited), "mean_novelty": round(sum(n for _, n in nov) / len(nov), 4) if nov else None,
            "issues": issues, "console": run.console[:50], "agent_notes": run.agent_notes, "notes": self.notes,
            "moments": [m.__dict__ for m in run.moments if not m.kind.startswith("event:")],
            "series": {"novelty": nov, "fps": [(s["t"], s["fps"]) for s in run.samples[::4] if s.get("fps")]},
        }
        (self.out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        _timeline(nov, run, self.out / "timeline.png", dur)
        if run.positions:
            _heatmap(run.positions, self.out / "heatmap.png")
        _contact(run, self.out)
        (self.out / "report.md").write_text(_markdown(report), encoding="utf-8")
        (self.out / "report.html").write_text(_html(report), encoding="utf-8")
        return report


def _low_novelty_stretches(nov: list[tuple[float, float]], events: list[Moment], window: float = 10.0) -> list[tuple[float, float]]:
    """Stretches of at least ``window`` seconds where the screen kept looking like places already seen
    and the game produced no event."""
    threshold = 0.004
    out, start = [], None
    ev_times = [e.t for e in events if e.kind not in PLAYER_EVENTS]
    for t, n in nov:
        quiet = n < threshold and not any(abs(t - et) < 2 for et in ev_times)
        if quiet and start is None:
            start = t
        elif not quiet and start is not None:
            if t - start >= window:
                out.append((start, t))
            start = None
    if start is not None and nov and nov[-1][0] - start >= window:
        out.append((start, nov[-1][0]))
    return out


def _timeline(nov, run: Run, path: Path, dur: float) -> None:
    w, h, pad = 900, 220, 30
    img = Image.new("RGB", (w, h), (26, 28, 44))
    d = ImageDraw.Draw(img)
    d.text((pad, 6), "novelty (how new the screen looks) / fps / events", fill=(148, 176, 194))
    if nov:
        top = max(0.02, sorted(n for _, n in nov)[int(len(nov) * 0.95)] * 1.1)
        pts = [(pad + (t / max(dur, 1)) * (w - 2 * pad), h - pad - min(1.0, n / top) * (h - 2 * pad)) for t, n in nov]
        if len(pts) > 1:
            d.line(pts, fill=(115, 239, 247), width=2)
    fps = [(s["t"], s["fps"]) for s in run.samples if s.get("fps")]
    if len(fps) > 1:
        d.line([(pad + (t / max(dur, 1)) * (w - 2 * pad), h - pad - min(f, 70) / 70 * (h - 2 * pad)) for t, f in fps],
               fill=(167, 240, 112), width=1)
    colors = {"coin": (255, 205, 117), "hurt": (239, 125, 87), "death": (177, 62, 83), "win": (56, 183, 100),
              "kill": (65, 166, 246)}
    for m in run.moments:
        x = pad + (m.t / max(dur, 1)) * (w - 2 * pad)
        kind = m.kind.split(":")[-1]
        if m.kind.startswith("event:") and kind in colors:
            d.line([(x, h - pad), (x, h - pad + 8)], fill=colors[kind], width=2)
        elif m.kind in ("error", "stuck", "frozen"):
            d.line([(x, pad), (x, h - pad)], fill=(239, 70, 70), width=1)
    d.line([(pad, h - pad), (w - pad, h - pad)], fill=(86, 108, 134))
    img.save(path)


def _heatmap(positions, path: Path) -> None:
    xs, ys = [p[0] for p in positions], [p[1] for p in positions]
    x0, y0 = min(xs), min(ys)
    w = max(1, int((max(xs) - x0) / 4) + 1)
    h = max(1, int((max(ys) - y0) / 4) + 1)
    grid = [[0] * w for _ in range(h)]
    for x, y in positions:
        grid[int((y - y0) / 4)][int((x - x0) / 4)] += 1
    top = max(max(r) for r in grid)
    img = Image.new("RGB", (w, h), (26, 28, 44))
    px = img.load()
    for y in range(h):
        for x in range(w):
            v = grid[y][x] / top
            if v:
                px[x, y] = (int(80 + 175 * v), int(200 * (1 - v) + 40), int(120 * (1 - v)))
    img.resize((w * 4, h * 4), Image.NEAREST).save(path)


def _contact(run: Run, out: Path) -> None:
    shots = [m for m in run.moments if m.shot][:12]
    if not shots:
        return
    tw, th = 320, 240
    cols = 4
    rows = math.ceil(len(shots) / cols)
    sheet = Image.new("RGB", (cols * tw, rows * (th + 18)), (26, 28, 44))
    d = ImageDraw.Draw(sheet)
    for i, m in enumerate(shots):
        im = Image.open(out / m.shot).convert("RGB")
        im.thumbnail((tw, th))
        x, y = (i % cols) * tw, (i // cols) * (th + 18)
        sheet.paste(im, (x, y))
        d.text((x + 4, y + th + 3), f"{m.t:>5.1f}s {m.kind}", fill=(244, 244, 244))
    sheet.save(out / "moments.jpg", quality=88)


def _markdown(r: dict) -> str:
    lines = [f"# Playtest report — {r['verdict']}", "",
             f"- policy **{r['policy']}**, {r['duration_s']}s, telemetry: {r['telemetry']}",
             f"- FPS avg {r['fps']['avg']} / p5 {r['fps']['p5']} / min {r['fps']['min']}",
             f"- events: {r['events']} · deaths {r['deaths']} · wins {r['wins']} · first event at {r['time_to_first_event_s']}s",
             f"- explored {r['coverage_cells']} map cells · mean novelty {r['mean_novelty']}", "", "## Issues", ""]
    lines += [f"- **[{i['severity']}]** {i['title']} — {i['detail']}" + (f" (t={i['t']}s)" if i["t"] is not None else "")
              + (f" ![]({i['shot']})" if i.get("shot") else "") for i in r["issues"]] or ["- none found"]
    if r["agent_notes"]:
        lines += ["", "## Tester notes", ""] + [f"- {n['t']}s (fun {n.get('fun')}/5): {n.get('observation')}"
                                                for n in r["agent_notes"]]
    lines += ["", "![timeline](timeline.png)", "", "![moments](moments.jpg)"]
    return "\n".join(lines) + "\n"


def _html(r: dict) -> str:
    sev_color = {"critical": "#e43b44", "major": "#f77622", "minor": "#feae34", "design": "#41a6f6"}
    items = "".join(_issue_li(i, sev_color) for i in r["issues"]) or "<li>No issues found.</li>"
    notes = "".join(f"<li><b>{n['t']}s</b> fun {n.get('fun')}/5 — {_esc(n.get('observation') or '')}</li>" for n in r["agent_notes"])
    verdict_color = {"BROKEN": "#e43b44", "ROUGH": "#f77622", "PLAYABLE": "#feae34", "SOLID": "#38b764"}[r["verdict"]]
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Playtest report</title><style>
:root{{--bg:#1a1c2c;--fg:#f4f4f4;--mute:#94b0c2;--card:#262b44}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;max-width:980px;margin:0 auto;padding:16px}}
h1{{font-size:28px}} .verdict{{color:{verdict_color}}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}
.card{{background:var(--card);border-radius:10px;padding:12px}} .card b{{display:block;font-size:22px}} .card span{{color:var(--mute);font-size:13px}}
ul{{padding-left:18px}} li{{margin:10px 0}} li img{{max-width:100%;border-radius:8px;margin-top:6px}}
.tag{{color:#1a1c2c;border-radius:6px;padding:1px 7px;font-size:12px;font-weight:700;text-transform:uppercase}}
img.wide{{width:100%;border-radius:10px}}</style>
<h1>Playtest: <span class=verdict>{r['verdict']}</span></h1>
<div class=grid>
<div class=card><b>{r['duration_s']}s</b><span>played ({r['policy']})</span></div>
<div class=card><b>{r['fps']['avg']}</b><span>avg FPS (p5 {r['fps']['p5']})</span></div>
<div class=card><b>{r['deaths']} / {r['wins']}</b><span>deaths / wins</span></div>
<div class=card><b>{r['coverage_cells']}</b><span>map cells explored</span></div>
<div class=card><b>{r['mean_novelty']}</b><span>mean screen novelty</span></div>
<div class=card><b>{len(r['console'])}</b><span>console errors</span></div></div>
<h2>Issues</h2><ul>{items}</ul>
{f'<h2>Tester notes</h2><ul>{notes}</ul>' if notes else ''}
<h2>Timeline</h2><img class=wide src="timeline.png" alt="novelty and fps over time">
<h2>Key moments</h2><img class=wide src="moments.jpg" alt="screenshots of key moments">
"""


def _issue_li(i: dict, colors: dict) -> str:
    when = f" <i>t={i['t']}s</i>" if i["t"] is not None else ""
    shot = f'<br><img src="{i["shot"]}" alt="">' if i.get("shot") else ""
    return (f"<li><span class=tag style='background:{colors[i['severity']]}'>{i['severity']}</span> "
            f"<b>{_esc(i['title'])}</b> — {_esc(i['detail'])}{when}{shot}</li>")


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

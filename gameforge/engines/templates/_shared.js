// GameForge shared runtime. forge_engine concatenates the genre module FIRST and this file
// SECOND, so a genre's `const GENRE` is already initialised when boot() runs below (declaration
// order inside one script is what keeps that safe). A build stays a single game.js, no imports.
//
// A genre module defines:
//   const GENRE = "platformer";
//   function start()                  // build the level, set the scene to "title"
//   function update(dt, time)         // called while scene === "play" and not paused
//   function renderWorld(time)        // draw the world (camera offset applied by the genre)
//   function hud(time)                // optional overlay
//   function onReset()                // optional: reset state on start / retry
//   function genreState()             // optional: extra telemetry fields
// and may override renderTitle / renderOver / renderWin / overSummary / winSummary.
"use strict";

const W = 320, H = 240, T = 16;
const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");
ctx.imageSmoothingEnabled = false;

const GF = (window.__gameforge = {
  version: 2,
  genre: "unknown",
  controls: { move: ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"], action: ["Space"], start: ["Enter"] },
  state: { scene: "boot" },
  events: [],
  fps: 0,
});

const now = () => performance.now();
const clock = { t: 0 };
function emit(type, data) { GF.events.push({ t: +clock.t.toFixed(2), type, ...(data || {}) }); }
const hash = (x, y) => { let h = x * 374761393 + y * 668265263; h = (h ^ (h >> 13)) * 1274126177; return (h ^ (h >> 16)) >>> 0; };

// ------------------------------------------------------------------ persistence
const store = (() => {
  let mem = {};
  try {
    localStorage.setItem("__gf", "1");
    localStorage.removeItem("__gf");
    return { get: k => localStorage.getItem(k), set: (k, v) => localStorage.setItem(k, v) };
  } catch (e) {
    return { get: k => (k in mem ? mem[k] : null), set: (k, v) => { mem[k] = String(v); } };
  }
})();
function best(key) { return +(store.get("gf_best_" + key) || 0); }
function setBest(key, value) {
  if (value > best(key)) { store.set("gf_best_" + key, value); emit("best", { key, value }); return true; }
  return false;
}

// ------------------------------------------------------------------ pixel font (3x5)
const GLYPHS = {
  A: "010101111101101", B: "110101110101110", C: "011100100100011", D: "110101101101110", E: "111100110100111",
  F: "111100110100100", G: "011100101101011", H: "101101111101101", I: "111010010010111", J: "001001001101010",
  K: "101101110101101", L: "100100100100111", M: "101111111101101", N: "110101101101101", O: "010101101101010",
  P: "110101110100100", Q: "010101101110011", R: "110101110101101", S: "011100010001110", T: "111010010010010",
  U: "101101101101111", V: "101101101101010", W: "101101111111101", X: "101101010101101", Y: "101101010010010",
  Z: "111001010100111", 0: "111101101101111", 1: "010110010010111", 2: "110001010100111", 3: "110001010001110",
  4: "101101111001001", 5: "111100110001110", 6: "011100111101111", 7: "111001010010010", 8: "111101111101111",
  9: "111101111001110", "!": "010010010000010", "?": "110001010000010", ".": "000000000000010", ":": "000010000010000",
  "-": "000000111000000", "/": "001001010100100", "+": "000010111010000", "'": "010010000000000", ",": "000000000010100",
  "(": "001010010010001", ")": "100010010010100", "%": "101001010100101", "<": "001010100010001", ">": "100010001010100",
  " ": "000000000000000",
};
function text(str, x, y, color = "#f4f4f4", scale = 1, align = "left") {
  str = String(str).toUpperCase();
  const w = str.length * 4 * scale - scale;
  if (align === "center") x = Math.round(x - w / 2);
  else if (align === "right") x = Math.round(x - w);
  for (const pass of [["#1a1c2c", 1], [color, 0]]) {
    ctx.fillStyle = pass[0];
    for (let i = 0; i < str.length; i++) {
      const g = GLYPHS[str[i]] || GLYPHS["?"];
      for (let b = 0; b < 15; b++) if (g[b] === "1")
        ctx.fillRect(x + (i * 4 + (b % 3)) * scale + pass[1], y + Math.floor(b / 3) * scale + pass[1], scale, scale);
    }
  }
}

// ------------------------------------------------------------------ assets
const images = {}, sounds = {}, atlases = {};
let audio = null, musicGain = null, musicNode = null, cfg = null, masterGain = null, muted = false;
function loadImage(src) {
  return new Promise((ok, bad) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => bad(new Error("missing image " + src)); i.src = src; });
}
async function loadJSON(src) { const r = await fetch(src); if (!r.ok) throw new Error("missing " + src); return r.json(); }
async function loadSound(src) {
  if (!audio) return null;
  const r = await fetch(src); if (!r.ok) throw new Error("missing sound " + src);
  return audio.decodeAudioData(await r.arrayBuffer());
}
function play(name, gain = 0.6) {
  const pool = sounds[name]; if (!audio || muted || !pool || !pool.length) return;
  const src = audio.createBufferSource(), g = audio.createGain();
  src.buffer = pool[Math.floor(Math.random() * pool.length)];
  g.gain.value = gain;
  src.playbackRate.value = 0.94 + Math.random() * 0.12;
  src.connect(g).connect(masterGain || audio.destination); src.start();
}
function startMusic() {
  if (!audio || muted || !sounds.music || musicNode) return;
  musicNode = audio.createBufferSource(); musicNode.buffer = sounds.music[0]; musicNode.loop = true;
  musicGain = audio.createGain(); musicGain.gain.value = cfg.music_volume ?? 0.35;
  musicNode.connect(musicGain).connect(masterGain || audio.destination); musicNode.start();
}
function stopMusic() { try { if (musicNode) { musicNode.stop(); musicNode = null; } } catch (e) { /* already stopped */ } }
function toggleMute() {
  muted = !muted;
  if (masterGain) masterGain.gain.value = muted ? 0 : 1;
  emit("mute", { muted });
}
function frameRects(json) {
  const names = Object.keys(json.frames);
  const rects = names.map(n => json.frames[n].frame);
  const tags = {};
  const tagsSrc = json.meta && json.meta.frameTags ? json.meta.frameTags : [];
  for (const t of tagsSrc) tags[t.name] = t.frames.map(f => names.indexOf(f));
  return { rects, tags };
}

// ------------------------------------------------------------------ input
// Keyboard/touch and gamepad live in separate sets: a gamepad poll that finds no pad must never
// delete a key the player is holding (that bug made keyboard controls dead on desktop Chrome).
const keys = new Set(), pressed = new Set(), padKeys = new Set();
const GAME_KEYS = new Set(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Space", "KeyZ", "KeyX", "Escape", "KeyP", "KeyM"]);
addEventListener("keydown", e => {
  const k = e.code;
  if (!keys.has(k)) pressed.add(k);
  keys.add(k);
  if (k === "KeyM") toggleMute();
  if (k === "KeyP" || k === "Escape") togglePause();
  unlockAudio();
  if (GAME_KEYS.has(k)) e.preventDefault();
});
addEventListener("keyup", e => keys.delete(e.code));
addEventListener("blur", () => keys.clear());
for (const b of document.querySelectorAll("#pad button")) {
  const k = b.dataset.key;
  b.addEventListener("pointerdown", e => { e.preventDefault(); if (!keys.has(k)) pressed.add(k); keys.add(k); unlockAudio(); });
  for (const ev of ["pointerup", "pointerleave", "pointercancel"]) b.addEventListener(ev, () => keys.delete(k));
}
canvas.addEventListener("pointerdown", () => { pressed.add("Enter"); unlockAudio(); });
function unlockAudio() { if (audio && audio.state === "suspended") audio.resume(); }
const down = k => keys.has(k) || padKeys.has(k);
const hit = k => pressed.has(k) || padKeys.has(k);

let padPrev = {}, padWasStart = false;
function pollGamepad() {
  if (!navigator.getGamepads) return;
  const pads = Array.from(navigator.getGamepads()).filter(p => p && p.connected);
  const next = {};
  if (pads.length) {
    let x = 0, y = 0;
    for (const pad of pads) {
      const ax = pad.axes[0] || 0, ay = pad.axes[1] || 0;
      if (Math.abs(ax) > 0.4) x += Math.sign(ax);
      if (Math.abs(ay) > 0.4) y += Math.sign(ay);
      const b = pad.buttons || [];
      const on = i => !!(b[i] && (b[i].pressed || b[i].value > 0.5));
      next.Space = next.Space || on(0) || on(1) || on(2) || on(3) || on(12);
      next.Enter = next.Enter || on(9);
    }
    next.ArrowLeft = x < 0; next.ArrowRight = x > 0; next.ArrowUp = y < 0; next.ArrowDown = y > 0;
  }
  padKeys.clear();
  for (const k of Object.keys(next)) if (next[k]) { padKeys.add(k); if (!padPrev[k]) pressed.add(k); }
  if (next.Enter && !padWasStart) togglePause();
  padWasStart = !!next.Enter;
  padPrev = next;
}

// ------------------------------------------------------------------ particles, camera, hitstop
let particles = [];
function poof(x, y, color, n = 8, spread = 55) {
  for (let i = 0; i < n; i++) {
    const a = Math.random() * 6.283, s = 20 + Math.random() * spread;
    particles.push({ x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s - 30, life: 0.4 + Math.random() * 0.4, color, g: 60 });
  }
}
function updateParticles(dt) {
  for (const q of particles) { q.x += q.vx * dt; q.y += q.vy * dt; q.vy += (q.g || 0) * dt; q.life -= dt; }
  particles = particles.filter(q => q.life > 0);
}
function drawParticles() {
  for (const q of particles) {
    ctx.globalAlpha = Math.min(1, q.life * 3);
    ctx.fillStyle = q.color;
    ctx.fillRect(Math.round(q.x - cam.x), Math.round(q.y - cam.y), 2, 2);
  }
  ctx.globalAlpha = 1;
}
const cam = { x: 0, y: 0 };
function follow(target, dt, lerp = 6, bounds = null) {
  cam.x += (target.x - W / 2 - cam.x) * Math.min(1, dt * lerp);
  cam.y += (target.y - H / 2 - cam.y) * Math.min(1, dt * lerp);
  if (bounds) {
    cam.x = Math.max(bounds.x0, Math.min(bounds.x1 - W, cam.x));
    cam.y = Math.max(bounds.y0, Math.min(bounds.y1 - H, cam.y));
  }
}
let shake = 0;
function addShake(amount) { shake = Math.max(shake, amount); }
let hitstopT = 0;
function hitstop(seconds) { hitstopT = Math.max(hitstopT, seconds); }

// ------------------------------------------------------------------ scenes
let scene = "boot", paused = false, overT = 0, winT = 0;
const titleBest = () => best(GF.genre || "game");
function togglePause() {
  if (scene !== "play") return;
  paused = !paused;
  emit("pause", { paused });
}
function setScene(next) { scene = next; }

function renderPause() {
  ctx.fillStyle = "#1a1c2ccc"; ctx.fillRect(0, 0, W, H);
  text("PAUSED", W / 2, 96, "#f4f4f4", 3, "center");
  text("P / START TO RESUME", W / 2, 130, "#94b0c2", 1, "center");
  text("M TO " + (muted ? "UNMUTE" : "MUTE"), W / 2, 144, "#566c86", 1, "center");
}

function renderTitle(time) {
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, cfg.sky_top || "#29366f"); g.addColorStop(1, cfg.sky_bottom || "#1a1c2c");
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  for (let i = 0; i < 40; i++) {
    ctx.fillStyle = hash(i, 1) % 7 ? "#566c86" : "#f4f4f4";
    ctx.fillRect(hash(i, 1) % W, hash(i, 2) % 120, 1, 1);
  }
  text(cfg.title, W / 2, 56, "#ffcd75", 3, "center");
  if (cfg.subtitle) text(cfg.subtitle, W / 2, 82, "#94b0c2", 1, "center");
  if (time % 900 < 620) text("PRESS ENTER", W / 2, 150, "#f4f4f4", 1, "center");
  text(cfg.controls_hint || "ARROWS MOVE  SPACE ATTACK", W / 2, 196, "#94b0c2", 1, "center");
  if (cfg.goal_hint) text(cfg.goal_hint, W / 2, 210, "#566c86", 1, "center");
  if (titleBest()) text("BEST " + titleBest(), W / 2, 226, "#ffcd75", 1, "center");
}
function renderOver(time, summary) {
  ctx.fillStyle = "#1a1c2ccc"; ctx.fillRect(0, 0, W, H);
  text("GAME OVER", W / 2, 84, "#ef7d57", 3, "center");
  if (summary) text(summary, W / 2, 122, "#f4f4f4", 2, "center");
  if (time % 800 < 560) text("ENTER TO RETRY", W / 2, 156, "#94b0c2", 1, "center");
}
function renderWin(time, summary) {
  ctx.fillStyle = "#1a1c2ccc"; ctx.fillRect(0, 0, W, H);
  text("VICTORY!", W / 2, 84, "#ffcd75", 3, "center");
  if (summary) text(summary, W / 2, 122, "#f4f4f4", 2, "center");
  if (time % 800 < 560) text("ENTER TO PLAY AGAIN", W / 2, 156, "#94b0c2", 1, "center");
}

function drawSprite(img, rect, x, y, flip) {
  const dx = Math.round(x - rect.w / 2 - cam.x), dy = Math.round(y - rect.h + 6 - cam.y);
  if (flip) { ctx.save(); ctx.scale(-1, 1); ctx.drawImage(img, rect.x, rect.y, rect.w, rect.h, -dx - rect.w, dy, rect.w, rect.h); ctx.restore(); }
  else ctx.drawImage(img, rect.x, rect.y, rect.w, rect.h, dx, dy, rect.w, rect.h);
}

// ------------------------------------------------------------------ loop
function fit() {
  const s = Math.max(1, Math.floor(Math.min(innerWidth / W, innerHeight / H)));
  canvas.style.width = W * s + "px"; canvas.style.height = H * s + "px";
}
addEventListener("resize", fit);

let last = 0, fpsAcc = 0, fpsN = 0, frames = 0;
function loop(time) {
  const rawDt = Math.min(0.05, (time - last) / 1000 || 0); last = time;
  fpsAcc += rawDt; fpsN++;
  if (fpsAcc > 0.5) { GF.fps = Math.round(fpsN / fpsAcc); fpsAcc = 0; fpsN = 0; }
  pollGamepad();

  const frozen = hitstopT > 0;
  if (frozen) hitstopT = Math.max(0, hitstopT - rawDt);
  const dt = frozen ? 0 : rawDt;
  if (dt > 0) clock.t += dt;

  const startPressed = hit("Enter") || hit("Space") || down("Enter") || down("Space");
  if (scene === "play" && !paused) update(dt, time);
  else if (scene === "over" || scene === "win") {
    if (dt > 0) { if (scene === "over") overT += dt; else winT += dt; updateParticles(dt); }
    if ((overT > 0.6 || winT > 0.6) && startPressed) {
      overT = 0; winT = 0;
      if (onReset) onReset();
      scene = "play"; startMusic();
    }
  } else if (scene === "title" && startPressed) {
    if (onReset) onReset();
    scene = "play"; startMusic();
  }
  if (dt > 0 && scene === "play" && !paused) updateParticles(dt);
  shake = Math.max(0, shake - rawDt);

  render(time);
  pressed.clear();
  const extra = typeof genreState === "function" ? genreState(time) : {};
  GF.state = scene === "title" || scene === "boot"
    ? { scene, paused, fps: GF.fps, seconds: +clock.t.toFixed(1) }
    : { scene, paused, fps: GF.fps, seconds: +clock.t.toFixed(1), ...extra };
  frames++;
  requestAnimationFrame(loop);
}

function render(time) {
  ctx.save();
  if (shake > 0) ctx.translate(Math.round((Math.random() - 0.5) * 4), Math.round((Math.random() - 0.5) * 4));
  ctx.fillStyle = "#1a1c2c"; ctx.fillRect(-4, -4, W + 8, H + 8);
  if (scene === "boot") { text("LOADING", W / 2, H / 2, "#94b0c2", 1, "center"); ctx.restore(); return; }
  if (scene === "title") { renderTitle(time); ctx.restore(); return; }
  if (scene === "error") { text("FAILED TO LOAD", W / 2, 110, "#ef7d57", 2, "center"); ctx.restore(); return; }
  if (typeof renderWorld === "function") renderWorld(time);
  if (typeof hud === "function") hud(time);
  if (scene === "over") renderOver(time, typeof overSummary === "function" ? overSummary() : "");
  if (scene === "win") renderWin(time, typeof winSummary === "function" ? winSummary() : "");
  if (paused) renderPause();
  ctx.restore();
}

async function boot() {
  fit();
  try {
    audio = new (window.AudioContext || window.webkitAudioContext)();
    masterGain = audio.createGain(); masterGain.connect(audio.destination);
  } catch (e) { audio = null; }
  cfg = await loadJSON("game.json");
  GF.genre = typeof GENRE === "string" ? GENRE : "unknown";
  const a = cfg.assets;
  const isJson = k => k.endsWith("_json");
  const imageKeys = Object.keys(a).filter(k => typeof a[k] === "string" && a[k] && !isJson(k) && k !== "music");
  await Promise.all(imageKeys.map(async k => { images[k] = await loadImage(a[k]); }));
  await Promise.all(Object.keys(a).filter(isJson).map(async k => {
    atlases[k.slice(0, -"_json".length)] = frameRects(await loadJSON(a[k]));
  }));
  await Promise.all(Object.entries(a.sfx || {}).map(async ([k, list]) => {
    sounds[k] = (await Promise.all(list.map(loadSound))).filter(Boolean);
  }));
  if (a.music) sounds.music = [await loadSound(a.music)].filter(Boolean);
  start();
  scene = "title";
  emit("boot", { genre: GF.genre });
  requestAnimationFrame(loop);
}
boot().catch(err => {
  console.error(err);
  GF.state = { scene: "error", error: String(err) };
  scene = "error";
  ctx.fillStyle = "#1a1c2c"; ctx.fillRect(0, 0, W, H);
  text("FAILED TO LOAD", W / 2, 110, "#ef7d57", 2, "center");
  emit("error", { message: String(err) });
});

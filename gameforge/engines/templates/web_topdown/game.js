// GameForge top-down template. Everything tunable lives in game.json; this file is the runtime.
// Telemetry for the GameForge playtester is published on window.__gameforge.
"use strict";

const W = 320, H = 240, T = 16;
const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");
ctx.imageSmoothingEnabled = false;

const GF = window.__gameforge = {
  version: 1,
  controls: { move: ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"], action: ["Space"], start: ["Enter"] },
  state: { scene: "boot" },
  events: [],
  fps: 0,
};
function emit(type, data) { GF.events.push({ t: +(now() / 1000).toFixed(2), type, ...(data || {}) }); }
const now = () => performance.now();

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
  " ": "000000000000000",
};
function text(str, x, y, color = "#f4f4f4", scale = 1, align = "left") {
  str = String(str).toUpperCase();
  const w = str.length * 4 * scale - scale;
  if (align === "center") x = Math.round(x - w / 2);
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
const images = {}, sounds = {};
let audio = null, musicNode = null, cfg = null, atlases = {};
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
  const pool = sounds[name]; if (!audio || !pool || !pool.length) return;
  const src = audio.createBufferSource(); const g = audio.createGain();
  src.buffer = pool[Math.floor(Math.random() * pool.length)]; g.gain.value = gain;
  src.playbackRate.value = 0.94 + Math.random() * 0.12;
  src.connect(g).connect(audio.destination); src.start();
}
function startMusic() {
  if (!audio || !sounds.music || musicNode) return;
  musicNode = audio.createBufferSource(); musicNode.buffer = sounds.music[0]; musicNode.loop = true;
  const g = audio.createGain(); g.gain.value = cfg.music_volume ?? 0.35;
  musicNode.connect(g).connect(audio.destination); musicNode.start();
}
function frameRects(json) {
  const names = Object.keys(json.frames);
  const rects = names.map(n => json.frames[n].frame);
  const tags = {}; for (const t of json.meta.frameTags || []) tags[t.name] = t.frames.map(f => names.indexOf(f));
  return { rects, tags };
}

// ------------------------------------------------------------------ input
const keys = new Set(), pressed = new Set();
addEventListener("keydown", e => { const k = e.code; if (!keys.has(k)) pressed.add(k); keys.add(k); unlockAudio();
  if (k.startsWith("Arrow") || k === "Space") e.preventDefault(); });
addEventListener("keyup", e => keys.delete(e.code));
for (const b of document.querySelectorAll("#pad button")) {
  const k = b.dataset.key;
  b.addEventListener("pointerdown", e => { e.preventDefault(); if (!keys.has(k)) pressed.add(k); keys.add(k); unlockAudio(); });
  for (const ev of ["pointerup", "pointerleave", "pointercancel"]) b.addEventListener(ev, () => keys.delete(k));
}
canvas.addEventListener("pointerdown", () => { pressed.add("Enter"); unlockAudio(); });
function unlockAudio() { if (audio && audio.state === "suspended") audio.resume(); }
const down = k => keys.has(k), hit = k => pressed.has(k);

// ------------------------------------------------------------------ world
let map, mw, mh, player, enemies, coins, chest, particles, cam, scene = "title", t0 = 0, score = 0, shake = 0;
const SOLID = new Set(["~", "T", "R"]);
const cell = (x, y) => (x < 0 || y < 0 || x >= mw || y >= mh) ? "~" : map[y][x];
const isLand = (x, y) => cell(x, y) !== "~";
const solidAt = (px, py) => SOLID.has(cell(Math.floor(px / T), Math.floor(py / T)));
const hash = (x, y) => { let h = x * 374761393 + y * 668265263; h = (h ^ (h >> 13)) * 1274126177; return (h ^ (h >> 16)) >>> 0; };

function reset() {
  map = cfg.map.map(r => r.split("")); mh = map.length; mw = map[0].length;
  enemies = []; coins = []; particles = []; chest = null; score = 0; shake = 0;
  for (let y = 0; y < mh; y++) for (let x = 0; x < mw; x++) {
    const c = map[y][x], px = x * T + T / 2, py = y * T + T / 2;
    if (c === "@") player = { x: px, y: py, face: "down", anim: 0, hp: cfg.player.hp, inv: 0, cd: 0, burst: 0, moving: false };
    if (c === "c") coins.push({ x: px, y: py, phase: Math.random() * 6 });
    if (c === "s") enemies.push({ x: px, y: py, vx: 0, vy: 0, think: 0, hp: 1, phase: Math.random() * 6 });
    if (c === "X") chest = { x: px, y: py, open: false };
    if ("@csXf".includes(c)) map[y][x] = c === "f" ? "f" : ".";
  }
  cam = { x: player.x - W / 2, y: player.y - H / 2 };
  t0 = now();
  emit("start", { coins: coins.length, enemies: enemies.length });
}

function move(o, dx, dy, r) {
  const tryAxis = (nx, ny) => !solidAt(nx - r, ny - r) && !solidAt(nx + r, ny - r) && !solidAt(nx - r, ny + r) && !solidAt(nx + r, ny + r);
  if (tryAxis(o.x + dx, o.y)) o.x += dx;
  if (tryAxis(o.x, o.y + dy)) o.y += dy;
}

function update(dt) {
  if (scene !== "play") {
    if (hit("Enter") || hit("Space")) { if (scene !== "play") { reset(); scene = "play"; startMusic(); } }
    return;
  }
  const p = player, sp = cfg.player.speed;
  let dx = (down("ArrowRight") || down("KeyD")) - (down("ArrowLeft") || down("KeyA"));
  let dy = (down("ArrowDown") || down("KeyS")) - (down("ArrowUp") || down("KeyW"));
  if (dx && dy) { dx *= 0.7071; dy *= 0.7071; }
  p.moving = !!(dx || dy);
  if (p.moving) {
    p.face = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up");
    const bx = p.x, by = p.y;
    move(p, dx * sp * dt, dy * sp * dt, 5);
    p.anim += dt * 8;
    if (Math.floor(p.anim) % 2 === 0 && Math.floor(p.anim) !== p.lastStep) { p.lastStep = Math.floor(p.anim); play("step", 0.25); }
    if (Math.abs(p.x - bx) + Math.abs(p.y - by) < 0.01) p.blocked = (p.blocked || 0) + dt; else p.blocked = 0;
  }
  p.inv = Math.max(0, p.inv - dt); p.cd = Math.max(0, p.cd - dt); p.burst = Math.max(0, p.burst - dt);
  if ((hit("Space") || hit("KeyZ")) && p.cd === 0) {
    p.cd = cfg.player.attack_cooldown; p.burst = 0.25; play("attack", 0.5); emit("attack");
    for (const e of enemies) if (Math.hypot(e.x - p.x, e.y - p.y) < cfg.player.attack_radius) {
      e.hp = 0; score += 50; play("kill", 0.6); emit("kill"); poof(e.x, e.y, "#a7f070", 12); shake = 0.15;
    }
  }
  enemies = enemies.filter(e => e.hp > 0);
  for (const e of enemies) {
    e.think -= dt; e.phase += dt * 6;
    const d = Math.hypot(p.x - e.x, p.y - e.y);
    if (d < cfg.enemy.chase_radius) { e.vx = (p.x - e.x) / d; e.vy = (p.y - e.y) / d; }
    else if (e.think <= 0) { const a = Math.random() * 6.28; e.vx = Math.cos(a) * 0.5; e.vy = Math.sin(a) * 0.5; e.think = 1 + Math.random() * 2; }
    move(e, e.vx * cfg.enemy.speed * dt, e.vy * cfg.enemy.speed * dt, 5);
    if (d < 11 && p.inv === 0) {
      p.hp -= 1; p.inv = 1.2; shake = 0.25; play("hurt", 0.7); emit("hurt", { hp: p.hp });
      const k = 14 / Math.max(1, d); move(p, (p.x - e.x) * k, (p.y - e.y) * k, 5);
      if (p.hp <= 0) { scene = "over"; emit("death", { score }); play("lose", 0.7); }
    }
  }
  for (const c of coins) {
    c.phase += dt * 5;
    if (!c.got && Math.hypot(c.x - p.x, c.y - p.y) < 11) {
      c.got = true; score += 10; play("coin", 0.55); emit("coin", { left: coins.filter(k => !k.got).length }); poof(c.x, c.y, "#ffcd75", 8);
    }
  }
  if (chest && !chest.open && coins.every(c => c.got) && Math.hypot(chest.x - p.x, chest.y - p.y) < 14) {
    chest.open = true; score += 200 + Math.max(0, Math.round(300 - (now() - t0) / 1000) * 5);
    play("win", 0.8); emit("win", { score, seconds: +((now() - t0) / 1000).toFixed(1) }); poof(chest.x, chest.y, "#73eff7", 30);
    setTimeout(() => { scene = "win"; }, 900);
  }
  for (const q of particles) { q.x += q.vx * dt; q.y += q.vy * dt; q.vy += 60 * dt; q.life -= dt; }
  particles = particles.filter(q => q.life > 0);
  shake = Math.max(0, shake - dt);
  cam.x += (p.x - W / 2 - cam.x) * Math.min(1, dt * 6); cam.y += (p.y - H / 2 - cam.y) * Math.min(1, dt * 6);
  cam.x = Math.max(0, Math.min(mw * T - W, cam.x)); cam.y = Math.max(0, Math.min(mh * T - H, cam.y));
}

function poof(x, y, color, n) {
  for (let i = 0; i < n; i++) { const a = Math.random() * 6.28, s = 20 + Math.random() * 50;
    particles.push({ x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s - 30, life: 0.4 + Math.random() * 0.4, color }); }
}

// ------------------------------------------------------------------ render
function drawTerrain(time) {
  const ts = images.tiles, frame = Math.floor(time / 300) % (cfg.tiles.frames || 1);
  const ox = frame * 4 * T;
  const x0 = Math.floor(cam.x / T), y0 = Math.floor(cam.y / T);
  for (let vy = y0; vy <= y0 + H / T + 1; vy++) for (let vx = x0; vx <= x0 + W / T + 1; vx++) {
    // dual grid: each drawn tile sits on a cell corner and blends the four cells around it
    const tl = +isLand(vx - 1, vy - 1), tr = +isLand(vx, vy - 1), bl = +isLand(vx - 1, vy), br = +isLand(vx, vy);
    let idx = tl * 8 + tr * 4 + bl * 2 + br, sx = (idx % 4) * T, sy = Math.floor(idx / 4) * T;
    const h = hash(vx, vy);
    if (idx === 15 && h % 3 === 0) { sx = (h >> 4) % 4 * T; sy = 4 * T; }
    if (idx === 0 && h % 3 === 0) { sx = (h >> 4) % 4 * T; sy = 5 * T; }
    ctx.drawImage(ts, sx + ox, sy, T, T, Math.round(vx * T - T / 2 - cam.x), Math.round(vy * T - T / 2 - cam.y), T, T);
  }
}

function drawSprite(img, rect, x, y, flip) {
  const dx = Math.round(x - rect.w / 2 - cam.x), dy = Math.round(y - rect.h + 6 - cam.y);
  if (flip) { ctx.save(); ctx.scale(-1, 1); ctx.drawImage(img, rect.x, rect.y, rect.w, rect.h, -dx - rect.w, dy, rect.w, rect.h); ctx.restore(); }
  else ctx.drawImage(img, rect.x, rect.y, rect.w, rect.h, dx, dy, rect.w, rect.h);
}

function render(time) {
  ctx.save();
  if (shake > 0) ctx.translate(Math.round((Math.random() - 0.5) * 4), Math.round((Math.random() - 0.5) * 4));
  ctx.fillStyle = "#1a1c2c"; ctx.fillRect(-4, -4, W + 8, H + 8);
  if (scene === "title") { renderTitle(time); ctx.restore(); return; }
  drawTerrain(time);
  const drawables = [];
  for (let y = 0; y < mh; y++) for (let x = 0; x < mw; x++) {
    const c = map[y][x];
    if (c === "T" || c === "R" || c === "f") drawables.push({ y: y * T + T, draw: () => {
      const im = images[{ T: "tree", R: "rock", f: "flowers" }[c]];
      ctx.drawImage(im, Math.round(x * T + T / 2 - im.width / 2 - cam.x), Math.round(y * T + T - im.height - cam.y + (c === "f" ? 0 : 2)));
    } });
  }
  for (const c of coins) if (!c.got) drawables.push({ y: c.y, draw: () =>
    ctx.drawImage(images.coin, Math.round(c.x - 8 - cam.x), Math.round(c.y - 12 - cam.y + Math.sin(c.phase) * 2)) });
  if (chest) drawables.push({ y: chest.y, draw: () => {
    const locked = !coins.every(c => c.got);
    ctx.globalAlpha = locked ? 0.55 : 1;
    ctx.drawImage(images.chest, Math.round(chest.x - 8 - cam.x), Math.round(chest.y - 12 - cam.y));
    ctx.globalAlpha = 1;
    if (!locked && !chest.open && Math.floor(time / 200) % 2) text("!", chest.x - cam.x - 1, chest.y - 22 - cam.y, "#ffcd75");
  } });
  const ea = atlases.enemy;
  for (const e of enemies) drawables.push({ y: e.y, draw: () =>
    drawSprite(images.enemy, ea.rects[ea.tags.idle[Math.floor(e.phase / 3) % 2]], e.x, e.y, e.vx < 0) });
  const p = player, pa = atlases.player;
  drawables.push({ y: p.y, draw: () => {
    if (p.inv > 0 && Math.floor(time / 80) % 2) return;
    const tag = (p.moving ? "walk_" : "idle_") + p.face;
    const frames = pa.tags[tag] || pa.tags.walk_down;
    const f = frames[Math.floor(p.moving ? p.anim : time / 500) % frames.length];
    drawSprite(images.player, pa.rects[f], p.x, p.y, false);
  } });
  drawables.sort((a, b) => a.y - b.y).forEach(d => d.draw());
  if (p.burst > 0) {
    ctx.strokeStyle = "#73eff7"; ctx.lineWidth = 2; ctx.globalAlpha = p.burst * 4;
    ctx.beginPath(); ctx.arc(Math.round(p.x - cam.x), Math.round(p.y - 4 - cam.y), cfg.player.attack_radius * (1.2 - p.burst * 2), 0, 6.283); ctx.stroke();
    ctx.globalAlpha = 1;
  }
  for (const q of particles) { ctx.fillStyle = q.color; ctx.fillRect(Math.round(q.x - cam.x), Math.round(q.y - cam.y), 2, 2); }
  renderHud(time);
  if (scene === "over" || scene === "win") {
    ctx.fillStyle = "#1a1c2ccc"; ctx.fillRect(0, 0, W, H);
    text(scene === "win" ? "VICTORY!" : "GAME OVER", W / 2, 84, scene === "win" ? "#ffcd75" : "#ef7d57", 4, "center");
    text("SCORE " + score, W / 2, 120, "#f4f4f4", 2, "center");
    if (Math.floor(time / 400) % 2) text("PRESS ENTER", W / 2, 150, "#94b0c2", 1, "center");
  }
  ctx.restore();
}

function renderHud(time) {
  for (let i = 0; i < cfg.player.hp; i++) {
    ctx.globalAlpha = i < player.hp ? 1 : 0.25; ctx.drawImage(images.heart, 4 + i * 14, 4); ctx.globalAlpha = 1;
  }
  ctx.drawImage(images.coin, W - 64, 3);
  const left = coins.filter(c => !c.got).length;
  text(`${coins.length - left}/${coins.length}`, W - 46, 9);
  text(String(score).padStart(5, "0"), W / 2, 9, "#ffcd75", 1, "center");
  if (left === 0 && chest && !chest.open) text("THE CHEST IS OPEN!", W / 2, H - 14, "#73eff7", 1, "center");
}

function renderTitle(time) {
  const g = ctx.createLinearGradient(0, 0, 0, H); g.addColorStop(0, "#29366f"); g.addColorStop(1, "#1a1c2c");
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  for (let i = 0; i < 40; i++) { ctx.fillStyle = (i + Math.floor(time / 300)) % 7 ? "#566c86" : "#f4f4f4";
    ctx.fillRect((hash(i, 1) % W), (hash(i, 2) % 120), 1, 1); }
  text(cfg.title, W / 2, 56, "#ffcd75", 3, "center");
  if (cfg.subtitle) text(cfg.subtitle, W / 2, 80, "#94b0c2", 1, "center");
  const pa = atlases.player, frames = pa.tags.walk_down;
  const r = pa.rects[frames[Math.floor(time / 130) % frames.length]];
  ctx.drawImage(images.player, r.x, r.y, r.w, r.h, W / 2 - r.w, 100, r.w * 2, r.h * 2);
  const ea = atlases.enemy, er = ea.rects[ea.tags.idle[Math.floor(time / 400) % 2]];
  ctx.drawImage(images.enemy, er.x, er.y, er.w, er.h, W / 2 + 30, 108, er.w * 1.5, er.h * 1.5);
  if (Math.floor(time / 450) % 2) text("PRESS ENTER", W / 2, 160, "#f4f4f4", 1, "center");
  text("ARROWS MOVE  SPACE BURST", W / 2, 200, "#566c86", 1, "center");
  text("COLLECT EVERY COIN, THEN OPEN THE CHEST", W / 2, 212, "#566c86", 1, "center");
}

// ------------------------------------------------------------------ loop
function fit() {
  const s = Math.max(1, Math.floor(Math.min(innerWidth / W, innerHeight / H)));
  canvas.style.width = W * s + "px"; canvas.style.height = H * s + "px";
}
addEventListener("resize", fit);

let last = 0, fpsAcc = 0, fpsN = 0;
function loop(time) {
  const dt = Math.min(0.05, (time - last) / 1000 || 0); last = time;
  fpsAcc += dt; fpsN++; if (fpsAcc > 0.5) { GF.fps = Math.round(fpsN / fpsAcc); fpsAcc = 0; fpsN = 0; }
  update(dt); render(time); pressed.clear();
  if (scene !== "title") GF.state = { scene, score, hp: player.hp, x: Math.round(player.x), y: Math.round(player.y),
    coins_left: coins.filter(c => !c.got).length, enemies: enemies.length, seconds: +((now() - t0) / 1000).toFixed(1),
    blocked: +(player.blocked || 0).toFixed(2) };
  else GF.state = { scene };
  requestAnimationFrame(loop);
}

async function boot() {
  fit();
  try { audio = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { audio = null; }
  cfg = await loadJSON("game.json");
  const a = cfg.assets;
  const imgKeys = ["player", "enemy", "tiles", "coin", "heart", "chest", "tree", "rock", "flowers"];
  await Promise.all(imgKeys.map(async k => { images[k] = await loadImage(a[k]); }));
  atlases.player = frameRects(await loadJSON(a.player_json));
  atlases.enemy = frameRects(await loadJSON(a.enemy_json));
  await Promise.all(Object.entries(a.sfx).map(async ([k, list]) => {
    sounds[k] = (await Promise.all(list.map(loadSound))).filter(Boolean); }));
  if (a.music) sounds.music = [await loadSound(a.music)].filter(Boolean);
  scene = "title"; emit("boot");
  requestAnimationFrame(loop);
}
boot().catch(err => { console.error(err); GF.state = { scene: "error", error: String(err) };
  ctx.fillStyle = "#1a1c2c"; ctx.fillRect(0, 0, W, H); text("FAILED TO LOAD", W / 2, 110, "#ef7d57", 2, "center"); });

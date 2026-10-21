// GameForge platformer genre. Physics side-scroller with the feel numbers that matter:
// coyote time, jump buffering, early-release jump cut, asymmetric gravity, stomps and spikes.
//
// map legend:  # solid   . empty   P start   c coin   s slime   b bat   ^ spikes   X goal
const GENRE = "platformer";

const PS = { w: 10, h: 14, speed: 132, accel: 1100, friction: 1500, gravity: 1350, fall_gravity: 1750,
  jump: 390, jump_cut: 0.42, max_fall: 470, coyote: 0.10, buffer: 0.12, turn_boost: 2.5 };

let map, mw, mh, player, enemies, coins, goal, spawn, checkpoint, coinsGot = 0, deaths = 0,
  furthest = 0, winTime = 0, startedAt = 0, score = 0;

// Out of bounds sideways is a wall, but below the map is open air: a pit has to be lethal, and
// treating the bottom edge as solid put the player on an invisible ledge inside the pit.
const at = (x, y) => (y >= mh ? "." : (x < 0 || y < 0 || x >= mw) ? "#" : map[y][x]);
const isSolid = (x, y) => at(x, y) === "#";
function solidRect(px, py, w, h) {
  const x0 = Math.floor(px / T), x1 = Math.floor((px + w - 1) / T);
  const y0 = Math.floor(py / T), y1 = Math.floor((py + h - 1) / T);
  for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) if (isSolid(x, y)) return true;
  return false;
}
// Distance from (x, y+h) down to the first solid tile within `reach` tiles.
function surfaceBelow(x, y, h, reach) {
  const tx = Math.floor(x / T);
  const start = Math.floor((y + h) / T);
  for (let ty = start; ty <= start + reach; ty++) if (isSolid(tx, ty)) return ty * T;
  return mh * T;
}

function respawn() {
  const p = player, from = checkpoint || spawn;
  p.x = from.x; p.y = from.y; p.vx = 0; p.vy = 0; p.onGround = false;
  p.coyoteT = 0; p.bufferT = 0; p.hp = cfg.player.hp; p.inv = 1.4; p.facing = 1; p.anim = 0;
  cam.x = Math.max(0, Math.min(mw * T - W, p.x - W / 2));
}
function onReset() {
  map = cfg.map.map(r => r.split(""));
  mh = map.length; mw = map[0].length;
  enemies = []; coins = []; goal = null; spawn = { x: T, y: T }; particles = [];
  checkpoint = null; coinsGot = 0; furthest = 0; winTime = 0; deaths = 0; score = 0;
  for (let y = 0; y < mh; y++) for (let x = 0; x < mw; x++) {
    const c = map[y][x], px = x * T + T / 2, py = y * T + T / 2;
    if (c === "P") { spawn = { x: px - PS.w / 2, y: py - PS.h }; map[y][x] = "."; }
    if (c === "c") { coins.push({ x: px, y: py, got: false, phase: Math.random() * 6 }); map[y][x] = "."; }
    if (c === "s") { enemies.push({ kind: "slime", x: px, y: py, vy: 0, alive: true, phase: Math.random() * 6, dir: 1 }); map[y][x] = "."; }
    if (c === "b") { enemies.push({ kind: "bat", x: px, y: py, w: 12, h: 10, alive: true, phase: Math.random() * 6, homeY: py, t: 0 }); map[y][x] = "."; }
    if (c === "X") { goal = { x: px, y: py }; map[y][x] = "."; }
  }
  player = { x: spawn.x, y: spawn.y, vx: 0, vy: 0, onGround: false, coyoteT: 0, bufferT: 0,
    hp: cfg.player.hp, inv: 0, facing: 1, anim: 0, facingTag: "right" };
  respawn();
  startedAt = clock.t;
  emit("start", { coins: coins.length, enemies: enemies.length, width: mw });
}
function start() { onReset(); }

function hurt(fatal) {
  const p = player;
  if (p.inv > 0 && !fatal) return;
  p.hp -= 1; p.inv = 1.4; addShake(0.25); play("hurt", 0.65);
  emit("hurt", { hp: p.hp, fatal: !!fatal });
  if (p.hp <= 0 || fatal) {
    deaths += 1;
    emit("death", { progress: furthest, deaths });
    respawn();
  } else {
    p.vy = -PS.jump * 0.5;
  }
}

function update(dt, time) {
  const p = player;
  if (p.inv > 0) p.inv = Math.max(0, p.inv - dt);

  // horizontal: accelerate, then turn-boost, then friction
  const left = down("ArrowLeft") || down("KeyA"), right = down("ArrowRight") || down("KeyD");
  const dir = (right ? 1 : 0) - (left ? 1 : 0);
  if (dir !== 0) {
    const turning = p.vx !== 0 && Math.sign(p.vx) !== dir;
    p.vx += dir * PS.accel * (turning ? PS.turn_boost : 1) * dt;
    p.vx = Math.max(-PS.speed, Math.min(PS.speed, p.vx));
    p.facing = dir; p.facingTag = dir > 0 ? "right" : "left";
  } else {
    const f = PS.friction * dt;
    p.vx = Math.abs(p.vx) <= f ? 0 : p.vx - Math.sign(p.vx) * f;
  }

  // jump: buffered press + coyote window + release-to-cut + heavier fall than rise
  const jumpHeld = down("Space") || down("KeyZ") || down("ArrowUp") || down("KeyW");
  const jumpPressed = hit("Space") || hit("KeyZ") || hit("ArrowUp") || hit("KeyW");
  if (jumpPressed) p.bufferT = PS.buffer;
  if (p.bufferT > 0) p.bufferT = Math.max(0, p.bufferT - dt);
  p.coyoteT = p.onGround ? PS.coyote : Math.max(0, p.coyoteT - dt);
  if (p.bufferT > 0 && p.coyoteT > 0) {
    p.vy = -PS.jump; p.onGround = false; p.coyoteT = 0; p.bufferT = 0;
    play("jump", 0.4); emit("jump", { x: Math.round(p.x) });
  }
  if (!jumpHeld && p.vy < 0) p.vy *= 1 - (1 - PS.jump_cut) * Math.min(1, dt * 30);

  p.vy = Math.min(PS.max_fall, p.vy + (p.vy > 0 ? PS.fall_gravity : PS.gravity) * dt);
  const nx = p.x + p.vx * dt;
  if (!solidRect(nx, p.y, PS.w, PS.h)) p.x = nx; else p.vx = 0;
  const ny = p.y + p.vy * dt;
  p.onGround = false;
  if (!solidRect(p.x, ny, PS.w, PS.h)) p.y = ny;
  else {
    if (p.vy > 0) { p.onGround = true; if (p.vy > 260) poof(p.x + PS.w / 2, p.y + PS.h, "#8a8f9a", 3, 20); }
    p.vy = 0;
  }
  if (Math.abs(p.vx) > 8 && p.onGround) {
    p.anim += dt * 10;
    if (Math.floor(p.anim) !== p.lastStep) { p.lastStep = Math.floor(p.anim); play("step", 0.14); }
  }
  // checkpoints: every ~12 tiles of solid ground, so a death costs a jump, not the level.
  // Never on a hazard: a checkpoint inside a spike is an infinite death loop.
  if (p.onGround && (!checkpoint || p.x > checkpoint.x + 12 * T)) {
    const bx = Math.floor((p.x + PS.w / 2) / T), by = Math.floor((p.y + PS.h + 2) / T);
    const own = at(Math.floor((p.x + PS.w / 2) / T), Math.floor((p.y + PS.h / 2) / T));
    if (isSolid(bx, by) && own !== "^") {
      checkpoint = { x: p.x, y: p.y };
      poof(p.x + PS.w / 2, p.y + PS.h, "#73eff7", 5, 25);
      emit("checkpoint", { x: Math.round(p.x) });
    }
  }

  const cx = Math.floor((p.x + PS.w / 2) / T), cy = Math.floor((p.y + PS.h / 2) / T);
  if (p.y > mh * T + 40) {          // fell out of the world: lethal
    hurt(true);
    return;                         // respawned: the rest of this frame's positions are stale
  }
  if (at(cx, cy) === "^") {         // spikes wound and knock you back, they are not instant death
    hurt(false);
    if (p.hp > 0) p.vy = -PS.jump * 0.65;
  }

  for (const c of coins) {
    if (c.got) continue;
    c.phase += dt * 5;
    if (Math.abs(c.x - (p.x + PS.w / 2)) < 10 && Math.abs(c.y - (p.y + PS.h / 2)) < 12) {
      c.got = true; coinsGot += 1; score += 10;
      play("coin", 0.5); poof(c.x, c.y, "#ffcd75", 6); emit("coin", { left: coins.filter(k => !k.got).length });
    }
  }

  for (const e of enemies) {
    if (!e.alive) continue;
    e.phase += dt * 6;
    if (e.kind === "slime") {
      e.vy = Math.min(400, e.vy + PS.gravity * dt);
      const floor = surfaceBelow(e.x, e.y, 10, 2);
      if (e.y + e.vy * dt + 10 > floor) { e.y = floor - 10; e.vy = 0; } else e.y += e.vy * dt;
      const dx = Math.sign((p.x + PS.w / 2) - e.x);
      const chase = Math.abs((p.x + PS.w / 2) - e.x) < 90 ? (dx || 1) : e.dir;
      e.dir = chase;
      const ex = e.x + e.dir * 26 * dt;
      if (solidRect(ex - 6, e.y, 12, 10)) e.dir *= -1; else e.x = ex;
    } else {
      e.t += dt;
      e.y = e.homeY + Math.sin(e.t * 2.2 + e.phase) * 16;
      const dx = Math.sign((p.x + PS.w / 2) - e.x);
      if (Math.abs((p.x + PS.w / 2) - e.x) < 120) e.x += dx * 22 * dt;
    }
    const overlap = Math.abs((p.x + PS.w / 2) - e.x) < 11 && Math.abs((p.y + PS.h / 2) - e.y) < 13;
    if (!overlap) continue;
    const stomped = p.vy > 40 && (p.y + PS.h) - e.y < 13;
    if (stomped) {
      e.alive = false; p.vy = -PS.jump * 0.62; hitstop(0.05); addShake(0.12); score += 50;
      play("kill", 0.5); poof(e.x, e.y, e.kind === "slime" ? "#a7f070" : "#c078c8", 10);
      emit("stomp", { kind: e.kind });
    } else if (p.inv === 0) hurt(false);
  }

  if (goal && Math.abs((p.x + PS.w / 2) - goal.x) < 12 && Math.abs((p.y + PS.h / 2) - goal.y) < 16) {
    const secs = +(clock.t - startedAt).toFixed(1);
    winTime = secs;
    score += 200 + Math.max(0, 200 - Math.round(secs));
    setBest("platformer", score);
    play("win", 0.8); poof(goal.x, goal.y, "#73eff7", 24);
    emit("win", { seconds: secs, coins: coinsGot, score });
    scene = "win";
  }

  const target = p.x + PS.w / 2 + Math.max(-40, Math.min(40, p.vx * 0.25)) - W / 2;
  cam.x += (target - cam.x) * Math.min(1, dt * 7);
  cam.x = Math.max(0, Math.min(mw * T - W, cam.x));
  cam.y = Math.max(0, mh * T - H);
  furthest = Math.max(furthest, Math.round((p.x / (mw * T)) * 100));
}

// ------------------------------------------------------------------ render
function renderWorld(time) {
  const ts = images.tiles;
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, cfg.sky_top || "#29366f"); g.addColorStop(1, cfg.sky_bottom || "#1a1c2c");
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);

  const x0 = Math.floor(cam.x / T), x1 = x0 + Math.ceil(W / T) + 1;
  const y0 = Math.floor(cam.y / T), y1 = y0 + Math.ceil(H / T) + 1;
  for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
    const px = Math.round(x * T - cam.x), py = Math.round(y * T - cam.y);
    if (!isSolid(x, y)) {
      if (y > mh - 3) continue;
      continue;
    }
    const open = !isSolid(x, y - 1), h = hash(x, y);
    const sx = ((h >> 4) % 4) * T, sy = (open ? 4 : 3) * T;
    ctx.drawImage(ts, sx, sy, T, T, px, py, T, T);
  }
  for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
    if (at(x, y) !== "^") continue;
    const px = Math.round(x * T - cam.x), py = Math.round(y * T - cam.y);
    ctx.fillStyle = "#94b0c2";
    for (let i = 0; i < 3; i++) ctx.fillRect(px + i * 5 + 1, py + T - 7, 3, 7);
    ctx.fillStyle = "#566c86"; ctx.fillRect(px, py + T - 2, T, 2);
  }

  const drawables = [];
  for (const c of coins) if (!c.got) drawables.push({ y: c.y, draw: () =>
    ctx.drawImage(images.coin, Math.round(c.x - 6 - cam.x), Math.round(c.y - 6 - cam.y + Math.sin(c.phase) * 2)) });
  if (goal) drawables.push({ y: goal.y, draw: () => {
    const gx = Math.round(goal.x - cam.x), gy = Math.round(goal.y - cam.y);
    ctx.fillStyle = "#566c86"; ctx.fillRect(gx - 1, gy - 18, 2, 24);
    ctx.fillStyle = "#ffcd75";
    const wave = Math.sin(time / 140) * 1.5;
    ctx.beginPath(); ctx.moveTo(gx + 1, gy - 18); ctx.lineTo(gx + 13 + wave, gy - 14);
    ctx.lineTo(gx + 1, gy - 9); ctx.fill();
  } });
  for (const e of enemies) if (e.alive) drawables.push({ y: e.y, draw: () => {
    const a = e.kind === "bat" ? atlases.bat : atlases.enemy;
    const img = e.kind === "bat" ? images.bat : images.enemy;
    const frames = (a.tags && a.tags.idle) || [0, 1];
    const r = a.rects[frames[Math.floor(e.phase / 3) % frames.length]];
    ctx.drawImage(img, r.x, r.y, r.w, r.h,
      Math.round(e.x - r.w / 2 - cam.x), Math.round(e.y - r.h / 2 - cam.y + (e.kind === "bat" ? -2 : 3)), r.w, r.h);
  } });
  const p = player, pa = atlases.player;
  drawables.push({ y: p.y, draw: () => {
    if (p.inv > 0 && Math.floor(time / 70) % 2) return;
    const moving = Math.abs(p.vx) > 10;
    const tag = (p.onGround ? (moving ? "walk_" : "idle_") : "idle_") + p.facingTag;
    const frames = pa.tags[tag] || pa.tags.idle_right || pa.tags.walk_right || [0];
    const f = frames[Math.floor(moving ? p.anim : time / 400) % frames.length];
    const r = pa.rects[f];
    const dx = Math.round(p.x - r.w / 2 - cam.x), dy = Math.round(p.y + PS.h - r.h - cam.y);
    if (p.facing < 0) {
      ctx.save();
      ctx.translate(dx + r.w, dy);
      ctx.scale(-1, 1);
      ctx.drawImage(images.player, r.x, r.y, r.w, r.h, 0, 0, r.w, r.h);
      ctx.restore();
    } else {
      ctx.drawImage(images.player, r.x, r.y, r.w, r.h, dx, dy, r.w, r.h);
    }
  } });
  drawables.sort((a, b) => a.y - b.y).forEach(d => d.draw());
  drawParticles();
}

function hud() {
  for (let i = 0; i < cfg.player.hp; i++) {
    ctx.globalAlpha = i < player.hp ? 1 : 0.22; ctx.drawImage(images.heart, 4 + i * 13, 4); ctx.globalAlpha = 1;
  }
  ctx.drawImage(images.coin, W - 52, 3);
  text(`${coinsGot}/${coins.length}`, W - 34, 9, "#f4f4f4", 1, "right");
  const pct = Math.min(100, Math.round((player.x / (mw * T)) * 100));
  ctx.fillStyle = "#1a1c2c"; ctx.fillRect(4, H - 8, W - 8, 4);
  ctx.fillStyle = "#73eff7"; ctx.fillRect(4, H - 8, Math.round((W - 8) * pct / 100), 4);
}
function overSummary() { return `PROGRESS ${furthest}%`; }
function winSummary() { return `TIME ${winTime}S`; }
function genreState() {
  return { genre: GENRE, score, progress: furthest, coins: coinsGot, coins_total: coins.length,
    deaths, hp: player.hp, x: Math.round(player.x), y: Math.round(player.y), on_ground: player.onGround,
    enemies_left: enemies.filter(e => e.alive).length, won: scene === "win" };
}

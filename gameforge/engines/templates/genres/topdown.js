// GameForge top-down genre. Collect every coin, then open the chest. Enemies chase, a burst
// attack clears them. Everything tunable lives in game.json.
//
// map legend:  ~ water   . ground   T tree   R rock   f flowers   c coin   s enemy   @ start   X chest
const GENRE = "topdown";

let map, mw, mh, player, enemies, coins, chest, t0 = 0, score = 0;
const SOLID = new Set(["~", "T", "R"]);
const cell = (x, y) => (x < 0 || y < 0 || x >= mw || y >= mh) ? "~" : map[y][x];
const isLand = (x, y) => cell(x, y) !== "~";
const solidAt = (px, py) => SOLID.has(cell(Math.floor(px / T), Math.floor(py / T)));

function onReset() {
  map = cfg.map.map(r => r.split(""));
  mh = map.length; mw = map[0].length;
  enemies = []; coins = []; chest = null; score = 0; particles = [];
  for (let y = 0; y < mh; y++) for (let x = 0; x < mw; x++) {
    const c = map[y][x], px = x * T + T / 2, py = y * T + T / 2;
    if (c === "@") player = { x: px, y: py, face: "down", anim: 0, hp: cfg.player.hp, inv: 0, cd: 0, burst: 0, moving: false };
    if (c === "c") coins.push({ x: px, y: py, phase: Math.random() * 6, got: false });
    if (c === "s") enemies.push({ x: px, y: py, vx: 0, vy: 0, think: 0, hp: 1, phase: Math.random() * 6 });
    if (c === "X") chest = { x: px, y: py, open: false };
    if ("@csX".includes(c)) map[y][x] = ".";
  }
  cam.x = player.x - W / 2; cam.y = player.y - H / 2;
  t0 = clock.t;
  emit("start", { coins: coins.length, enemies: enemies.length });
}
function start() { onReset(); }

function move(o, dx, dy, r) {
  const tryAxis = (nx, ny) => !solidAt(nx - r, ny - r) && !solidAt(nx + r, ny - r) && !solidAt(nx - r, ny + r) && !solidAt(nx + r, ny + r);
  if (tryAxis(o.x + dx, o.y)) o.x += dx;
  if (tryAxis(o.x, o.y + dy)) o.y += dy;
}

function update(dt, time) {
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
    if (Math.floor(p.anim) % 2 === 0 && Math.floor(p.anim) !== p.lastStep) { p.lastStep = Math.floor(p.anim); play("step", 0.22); }
    if (Math.abs(p.x - bx) + Math.abs(p.y - by) < 0.01) p.blocked = (p.blocked || 0) + dt; else p.blocked = 0;
  }
  p.inv = Math.max(0, p.inv - dt); p.cd = Math.max(0, p.cd - dt); p.burst = Math.max(0, p.burst - dt);
  if ((hit("Space") || hit("KeyZ")) && p.cd === 0) {
    p.cd = cfg.player.attack_cooldown; p.burst = 0.25; play("attack", 0.5); emit("attack");
    for (const e of enemies) if (Math.hypot(e.x - p.x, e.y - p.y) < cfg.player.attack_radius) {
      e.hp = 0; score += 50; play("kill", 0.6); emit("kill"); poof(e.x, e.y, "#a7f070", 12); addShake(0.15);
    }
  }
  enemies = enemies.filter(e => e.hp > 0);
  for (const e of enemies) {
    e.think -= dt; e.phase += dt * 6;
    const d = Math.hypot(p.x - e.x, p.y - e.y) || 1;
    if (d < cfg.enemy.chase_radius) { e.vx = (p.x - e.x) / d; e.vy = (p.y - e.y) / d; }
    else if (e.think <= 0) { const a = Math.random() * 6.28; e.vx = Math.cos(a) * 0.5; e.vy = Math.sin(a) * 0.5; e.think = 1 + Math.random() * 2; }
    move(e, e.vx * cfg.enemy.speed * dt, e.vy * cfg.enemy.speed * dt, 5);
    if (d < 11 && p.inv === 0) {
      p.hp -= 1; p.inv = 1.2; addShake(0.25); play("hurt", 0.7); emit("hurt", { hp: p.hp });
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
    chest.open = true; score += 200 + Math.max(0, Math.round(300 - (clock.t - t0)) * 5);
    play("win", 0.8); emit("win", { score, seconds: +(clock.t - t0).toFixed(1) }); poof(chest.x, chest.y, "#73eff7", 30);
    setBest("topdown", score);
    setTimeout(() => { scene = "win"; }, 900);
  }
  follow(p, dt, 6, { x0: 0, y0: 0, x1: mw * T, y1: mh * T });
}

// ------------------------------------------------------------------ render
function drawTerrain(time) {
  const ts = images.tiles, frame = Math.floor(time / 300) % (cfg.tiles.frames || 1);
  const ox = frame * 4 * T;
  const x0 = Math.floor(cam.x / T), y0 = Math.floor(cam.y / T);
  for (let vy = y0; vy <= y0 + H / T + 1; vy++) for (let vx = x0; vx <= x0 + W / T + 1; vx++) {
    const tl = +isLand(vx - 1, vy - 1), tr = +isLand(vx, vy - 1), bl = +isLand(vx - 1, vy), br = +isLand(vx, vy);
    const idx = tl * 8 + tr * 4 + bl * 2 + br;
    let sx = (idx % 4) * T, sy = Math.floor(idx / 4) * T;
    const h = hash(vx, vy);
    if (idx === 15 && h % 3 === 0) { sx = (h >> 4) % 4 * T; sy = 4 * T; }
    if (idx === 0 && h % 3 === 0) { sx = (h >> 4) % 4 * T; sy = 5 * T; }
    ctx.drawImage(ts, sx + ox, sy, T, T, Math.round(vx * T - T / 2 - cam.x), Math.round(vy * T - T / 2 - cam.y), T, T);
  }
}

function renderWorld(time) {
  drawTerrain(time);
  const drawables = [];
  const propImg = { T: images.tree, R: images.rock, f: images.flowers };
  for (let y = 0; y < mh; y++) for (let x = 0; x < mw; x++) {
    const c = map[y][x], im = propImg[c];
    if (!im) continue;
    drawables.push({ y: y * T + T, draw: () =>
      ctx.drawImage(im, Math.round(x * T + T / 2 - im.width / 2 - cam.x), Math.round(y * T + T - im.height - cam.y + (c === "f" ? 0 : 2))) });
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
  const pa = atlases.player, p = player;
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
  drawParticles();
}

function hud() {
  for (let i = 0; i < cfg.player.hp; i++) {
    ctx.globalAlpha = i < player.hp ? 1 : 0.25; ctx.drawImage(images.heart, 4 + i * 14, 4); ctx.globalAlpha = 1;
  }
  ctx.drawImage(images.coin, W - 64, 3);
  const left = coins.filter(c => !c.got).length;
  text(`${coins.length - left}/${coins.length}`, W - 46, 9);
  text(String(score).padStart(5, "0"), W / 2, 9, "#ffcd75", 1, "center");
  if (left === 0 && chest && !chest.open) text("THE CHEST IS OPEN!", W / 2, H - 14, "#73eff7", 1, "center");
}
function overSummary() { return "SCORE " + score; }
function winSummary() { return "SCORE " + score; }
function genreState() {
  return { genre: GENRE, score, hp: player.hp, x: Math.round(player.x), y: Math.round(player.y),
    coins_left: coins.filter(c => !c.got).length, enemies: enemies.length,
    blocked: +(player.blocked || 0).toFixed(2) };
}

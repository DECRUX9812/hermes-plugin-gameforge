// GameForge roguelike genre. Room-to-room dungeon crawl: keys open the exit, potions heal,
// bats chase and ghosts drift through walls. Sword swings in the facing direction.
//
// map legend:  # wall   . floor   P start   k key   c coin   h potion   s bat   g ghost   D exit
const GENRE = "roguelike";

const RG = { w: 9, h: 9, speed: 96, attack_cd: 0.34, attack_reach: 22, inv_time: 1.2 };

let map, mw, mh, player, foes, keys_total = 0, keys_held = 0, coins = 0, score = 0,
  exitPos = null, swing = 0, deaths = 0;

const cellAt = (x, y) => (x < 0 || y < 0 || x >= mw || y >= mh) ? "#" : map[y][x];
const blocked = (px, py) => cellAt(Math.floor(px / T), Math.floor(py / T)) === "#";
function moveBox(o, dx, dy, r) {
  const free = (x, y) => !blocked(x - r, y - r) && !blocked(x + r, y - r) && !blocked(x - r, y + r) && !blocked(x + r, y + r);
  if (free(o.x + dx, o.y)) o.x += dx;
  if (free(o.x, o.y + dy)) o.y += dy;
}

function onReset() {
  map = cfg.map.map(r => r.split(""));
  mh = map.length; mw = map[0].length;
  foes = []; particles = []; keys_total = 0; keys_held = 0; coins = 0; score = 0; swing = 0; deaths = 0;
  let sx = W / 2, sy = H / 2;
  for (let y = 0; y < mh; y++) for (let x = 0; x < mw; x++) {
    const c = map[y][x], px = x * T + T / 2, py = y * T + T / 2;
    if (c === "P") { sx = px; sy = py; map[y][x] = "."; }
    if (c === "k") keys_total += 1;
    if (c === "D") exitPos = { x: px, y: py, open: false };
    if (c === "s") { foes.push({ kind: "bat", x: px, y: py, hp: 1, phase: Math.random() * 6 }); map[y][x] = "."; }
    if (c === "g") { foes.push({ kind: "ghost", x: px, y: py, hp: 2, phase: Math.random() * 6 }); map[y][x] = "."; }
  }
  player = { x: sx, y: sy, face: "down", anim: 0, hp: cfg.player.hp, inv: 0, cd: 0, moving: false, hurtT: 0 };
  cam.x = Math.max(0, Math.min(mw * T - W, sx - W / 2));
  cam.y = Math.max(0, Math.min(mh * T - H, sy - H / 2));
  emit("start", { keys: keys_total, foes: foes.length, exits: exitPos ? 1 : 0 });
}
function start() { onReset(); }

function hitFoe(f) {
  f.hp -= 1;
  if (f.hp > 0) { poof(f.x, f.y, "#c078c8", 5); return; }
  score += f.kind === "ghost" ? 120 : 60;
  play("kill", 0.6); poof(f.x, f.y, f.kind === "ghost" ? "#73eff7" : "#c078c8", 12); hitstop(0.05); addShake(0.12);
  emit("kill", { kind: f.kind, left: foes.filter(k => k.hp > 0).length });
}

function update(dt, time) {
  const p = player;
  p.inv = Math.max(0, p.inv - dt); p.cd = Math.max(0, p.cd - dt); p.hurtT = Math.max(0, p.hurtT - dt);
  swing = Math.max(0, swing - dt);

  let dx = (down("ArrowRight") || down("KeyD")) - (down("ArrowLeft") || down("KeyA"));
  let dy = (down("ArrowDown") || down("KeyS")) - (down("ArrowUp") || down("KeyW"));
  if (dx && dy) { dx *= 0.7071; dy *= 0.7071; }
  p.moving = !!(dx || dy);
  if (dx || dy) {
    p.face = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up");
    const bx = p.x, by = p.y;
    moveBox(p, dx * RG.speed * dt, dy * RG.speed * dt, RG.w);
    p.anim += dt * 8;
    if (Math.floor(p.anim) % 2 === 0 && Math.floor(p.anim) !== p.lastStep) { p.lastStep = Math.floor(p.anim); play("step", 0.16); }
    if (Math.abs(p.x - bx) + Math.abs(p.y - by) < 0.01) p.blocked = (p.blocked || 0) + dt; else p.blocked = 0;
  }

  const faceVec = { right: [1, 0], left: [-1, 0], up: [0, -1], down: [0, 1] }[p.face];
  if ((hit("Space") || hit("KeyZ")) && p.cd === 0) {
    p.cd = RG.attack_cd; swing = 0.16; play("attack", 0.45); emit("attack");
    for (const f of foes) {
      if (f.hp <= 0) continue;
      const d = Math.hypot(f.x - p.x, f.y - p.y);
      const dot = ((f.x - p.x) * faceVec[0] + (f.y - p.y) * faceVec[1]) / (d || 1);
      if (d < RG.attack_reach && dot > 0.35) hitFoe(f);
    }
  }

  // pickups are tiles: step on them to collect
  const tx = Math.floor(p.x / T), ty = Math.floor(p.y / T), here = map[ty] && map[ty][tx];
  if (here === "c") { map[ty][tx] = "."; coins += 1; score += 10; play("coin", 0.5); poof(p.x, p.y, "#ffcd75", 6); emit("coin", { coins }); }
  if (here === "k") { map[ty][tx] = "."; keys_held += 1; score += 40; play("coin", 0.7); poof(p.x, p.y, "#ffcd75", 10); emit("key", { held: keys_held, total: keys_total }); }
  if (here === "h") {
    if (p.hp < cfg.player.hp) { p.hp += 1; map[ty][tx] = "."; play("win", 0.4); poof(p.x, p.y, "#ef7d57", 10); emit("potion", { hp: p.hp }); }
  }

  for (const f of foes) {
    if (f.hp <= 0) continue;
    f.phase += dt * 6;
    const d = Math.hypot(p.x - f.x, p.y - f.y) || 1;
    const sees = d < 130;
    if (f.kind === "ghost") {
      // ghosts ignore walls: a straight drift that keeps constant pressure
      const speed = 26;
      f.x += (p.x - f.x) / d * speed * dt;
      f.y += (p.y - f.y) / d * speed * dt;
    } else if (sees) {
      moveBox(f, (p.x - f.x) / d * 42 * dt, (p.y - f.y) / d * 42 * dt, 5);
    } else if (Math.random() < dt * 0.8) {
      const a = Math.random() * 6.283;
      f.wander = { x: Math.cos(a), y: Math.sin(a) };
    } else if (f.wander) {
      moveBox(f, f.wander.x * 22 * dt, f.wander.y * 22 * dt, 5);
    }
    if (d < 10 && p.inv === 0) {
      p.hp -= 1; p.inv = RG.inv_time; p.hurtT = 0.4; addShake(0.22);
      play("hurt", 0.7); emit("hurt", { hp: p.hp });
      if (p.hp <= 0) {
        deaths += 1; setBest("roguelike", score);
        scene = "over"; emit("death", { score, keys: keys_held }); play("lose", 0.8);
        return;
      }
    }
  }

  if (exitPos) {
    const near = Math.hypot(exitPos.x - p.x, exitPos.y - p.y) < 14;
    const hasAll = keys_held >= keys_total && keys_total > 0;
    if (near && hasAll && !exitPos.open) {
      exitPos.open = true; score += 300; setBest("roguelike", score);
      play("door", 0.7); poof(exitPos.x, exitPos.y, "#73eff7", 26);
      emit("win", { score, keys: keys_held, coins });
      scene = "win";
    } else if (near && !hasAll) {
      p.lockedT = (p.lockedT || 0) + dt;
    }
  }

  const tx2 = p.x - W / 2, ty2 = p.y - H / 2;
  cam.x += (Math.max(0, Math.min(mw * T - W, tx2)) - cam.x) * Math.min(1, dt * 8);
  cam.y += (Math.max(0, Math.min(mh * T - H, ty2)) - cam.y) * Math.min(1, dt * 8);
}

// ------------------------------------------------------------------ render
function renderWorld(time) {
  const ts = images.tiles;
  ctx.fillStyle = "#14121f"; ctx.fillRect(0, 0, W, H);
  const x0 = Math.floor(cam.x / T), y0 = Math.floor(cam.y / T);
  for (let y = y0; y <= y0 + Math.ceil(H / T) + 1; y++) for (let x = x0; x <= x0 + Math.ceil(W / T) + 1; x++) {
    const px = Math.round(x * T - cam.x), py = Math.round(y * T - cam.y);
    if (cellAt(x, y) === "#") {
      const h = hash(x, y);
      ctx.drawImage(ts, ((h >> 4) % 4) * T, 3 * T, T, T, px, py, T, T);
    } else {
      ctx.fillStyle = "#1d1a2b"; ctx.fillRect(px, py, T, T);
      if ((x + y) % 2 === 0) { ctx.fillStyle = "#211e31"; ctx.fillRect(px + 2, py + 2, T - 4, T - 4); }
    }
  }
  // pickups that live in the tile grid
  for (let y = y0; y <= y0 + Math.ceil(H / T) + 1; y++) for (let x = x0; x <= x0 + Math.ceil(W / T) + 1; x++) {
    const c = cellAt(x, y), px = Math.round(x * T + T / 2 - cam.x), py = Math.round(y * T + T / 2 - cam.y);
    const img = c === "c" ? images.coin : c === "k" ? images.key : c === "h" ? images.potion : null;
    if (img) ctx.drawImage(img, px - img.width / 2, py - img.height / 2 + Math.sin(time / 260 + x) * 1.5);
    if (c === "D") {
      const opened = keys_held >= keys_total;
      ctx.fillStyle = opened ? "#73eff7" : "#566c86";
      ctx.fillRect(px - 6, py - 9, 12, 18);
      ctx.fillStyle = "#14121f"; ctx.fillRect(px + 2, py - 1, 2, 2);
    }
  }
  const ea = atlases.enemy, ga = atlases.ghost || atlases.enemy;
  for (const f of foes) {
    if (f.hp <= 0) continue;
    const a = f.kind === "ghost" ? ga : ea, img = f.kind === "ghost" ? (images.ghost || images.enemy) : images.enemy;
    const frames = (a.tags && a.tags.idle) || [0, 1];
    const r = a.rects[frames[Math.floor(f.phase / 3) % frames.length]];
    ctx.globalAlpha = f.kind === "ghost" ? 0.65 : 1;
    ctx.drawImage(img, r.x, r.y, r.w, r.h, Math.round(f.x - r.w / 2 - cam.x), Math.round(f.y - r.h / 2 - cam.y), r.w, r.h);
    ctx.globalAlpha = 1;
  }
  const p = player, pa = atlases.player;
  const tag = (p.moving ? "walk_" : "idle_") + p.face;
  const frames = pa.tags[tag] || pa.tags.idle_down || [0];
  const f = frames[Math.floor(p.moving ? p.anim : time / 500) % frames.length];
  const r = pa.rects[f];
  ctx.save();
  if (p.inv > 0 && Math.floor(time / 80) % 2) ctx.globalAlpha = 0.4;
  else if (p.hurtT > 0) ctx.globalAlpha = 0.75;
  ctx.drawImage(images.player, r.x, r.y, r.w, r.h, Math.round(p.x - r.w / 2 - cam.x), Math.round(p.y - r.h / 2 - cam.y), r.w, r.h);
  ctx.restore();
  if (swing > 0) {
    const [vx, vy] = { right: [1, 0], left: [-1, 0], up: [0, -1], down: [0, 1] }[p.face];
    ctx.strokeStyle = "#f4f4f4"; ctx.lineWidth = 2; ctx.globalAlpha = swing * 5;
    ctx.beginPath();
    ctx.arc(p.x - cam.x + vx * 8, p.y - cam.y + vy * 8, 11, 0, 6.283);
    ctx.stroke(); ctx.globalAlpha = 1;
  }
  drawParticles();
}

function hud() {
  for (let i = 0; i < cfg.player.hp; i++) {
    ctx.globalAlpha = i < player.hp ? 1 : 0.22; ctx.drawImage(images.heart, 4 + i * 13, 4); ctx.globalAlpha = 1;
  }
  ctx.drawImage(images.key, W / 2 - 12, 3);
  text(`${keys_held}/${keys_total}`, W / 2 + 4, 9, keys_held >= keys_total ? "#73eff7" : "#f4f4f4", 1);
  text(`${coins}`, W - 6, 9, "#ffcd75", 1, "right");
  if (exitPos && Math.hypot(exitPos.x - player.x, exitPos.y - player.y) < 14 && keys_held < keys_total) {
    text(`LOCKED ${keys_held}/${keys_total}`, W / 2, H - 16, "#ef7d57", 1, "center");
  }
}
function overSummary() { return `SCORE ${score}`; }
function winSummary() { return `SCORE ${score}`; }
function genreState() {
  return { genre: GENRE, score, hp: player.hp, x: Math.round(player.x), y: Math.round(player.y),
    keys: keys_held, keys_total, coins, foes: foes.filter(f => f.hp > 0).length, won: scene === "win",
    blocked: +(player.blocked || 0).toFixed(2) };
}

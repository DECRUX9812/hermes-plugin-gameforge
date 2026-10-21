// GameForge arena genre. Wave survival in a walled pit: auto-aimed shots, dash-free movement,
// escalating waves, pickups. One screen, so the camera never scrolls.
//
// map legend:  # wall   . floor   P start
const GENRE = "arena";

const AR = { w: 10, h: 10, speed: 118, accel: 1400, friction: 1500, fire_cd: 0.22, bullet_speed: 230,
  bullet_life: 1.1, dash_cd: 1.6, dash_speed: 430, dash_time: 0.14 };

let map, mw, mh, player, bullets, foes, pickups, wave = 1, kills = 0, score = 0,
  waveTimer = 0, waveState = "fight";

const solid = (px, py) => {
  const x = Math.floor(px / T), y = Math.floor(py / T);
  return x < 0 || y < 0 || x >= mw || y >= mh || map[y][x] === "#";
};
function moveCircle(o, dx, dy, r) {
  const free = (x, y) => !solid(x - r, y - r) && !solid(x + r, y - r) && !solid(x - r, y + r) && !solid(x + r, y + r);
  if (free(o.x + dx, o.y)) o.x += dx;
  if (free(o.x, o.y + dy)) o.y += dy;
}

function onReset() {
  map = cfg.map.map(r => r.split(""));
  mh = map.length; mw = map[0].length;
  bullets = []; foes = []; pickups = []; particles = [];
  wave = 1; kills = 0; score = 0; waveTimer = 0; waveState = "fight";
  let sx = W / 2, sy = H / 2;
  for (let y = 0; y < mh; y++) for (let x = 0; x < mw; x++) {
    if (map[y][x] === "P") { sx = x * T + T / 2; sy = y * T + T / 2; map[y][x] = "."; }
  }
  player = { x: sx, y: sy, vx: 0, vy: 0, hp: cfg.player.hp, inv: 0, cd: 0, aim: 0, dash: 0, dashCd: 0, anim: 0 };
  cam.x = 0; cam.y = 0;
  spawnWave();
  emit("start", { wave, foes: foes.length });
}
function start() { onReset(); }

function spawnWave() {
  const count = Math.min(14, 2 + wave * 2);
  const kinds = wave % 3 === 0 ? ["brute", "chaser"] : ["chaser"];
  for (let i = 0; i < count; i++) {
    // spawn on a random free floor tile away from the player
    let x = 0, y = 0, tries = 0;
    do {
      x = (1 + Math.floor(Math.random() * (mw - 2))) * T + T / 2;
      y = (1 + Math.floor(Math.random() * (mh - 2))) * T + T / 2;
      tries++;
    } while (tries < 60 && (map[Math.floor(y / T)][Math.floor(x / T)] === "#" || Math.hypot(x - player.x, y - player.y) < 70));
    const kind = kinds[Math.floor(Math.random() * kinds.length)];
    foes.push({ kind, x, y, hp: kind === "brute" ? 3 : 1, phase: Math.random() * 6,
      speed: (cfg.enemy.speed || 30) * (kind === "brute" ? 0.7 : 1.15) * (1 + wave * 0.05) });
  }
  play("wave", 0.5);
  emit("wave", { wave, foes: foes.length });
}

function shoot() {
  const p = player, a = p.aim;
  bullets.push({ x: p.x + Math.cos(a) * 8, y: p.y + Math.sin(a) * 8,
    vx: Math.cos(a) * AR.bullet_speed, vy: Math.sin(a) * AR.bullet_speed, life: AR.bullet_life });
  p.cd = AR.fire_cd; play("attack", 0.28); emit("shoot");
}

function nearestFoe() {
  let bestFoe = null, bestD = Infinity;
  for (const f of foes) {
    const d = Math.hypot(f.x - player.x, f.y - player.y);
    if (d < bestD) { bestD = d; bestFoe = f; }
  }
  return bestFoe;
}

function update(dt, time) {
  const p = player;
  p.inv = Math.max(0, p.inv - dt); p.cd = Math.max(0, p.cd - dt);
  p.dash = Math.max(0, p.dash - dt); p.dashCd = Math.max(0, p.dashCd - dt);

  let dx = (down("ArrowRight") || down("KeyD")) - (down("ArrowLeft") || down("KeyA"));
  let dy = (down("ArrowDown") || down("KeyS")) - (down("ArrowUp") || down("KeyW"));
  if (dx && dy) { dx *= 0.7071; dy *= 0.7071; }
  if (dx || dy) p.aim = Math.atan2(dy, dx);

  if (p.dash > 0) {
    moveCircle(p, Math.cos(p.aim) * AR.dash_speed * dt, Math.sin(p.aim) * AR.dash_speed * dt, AR.w);
    if (Math.random() < 0.6) poof(p.x, p.y, "#73eff7", 2, 20);
  } else {
    p.vx += dx * AR.accel * dt; p.vy += dy * AR.accel * dt;
    const f = AR.friction * dt;
    p.vx = Math.abs(p.vx) <= f ? 0 : p.vx - Math.sign(p.vx) * f;
    p.vy = Math.abs(p.vy) <= f ? 0 : p.vy - Math.sign(p.vy) * f;
    const sp = AR.speed;
    p.vx = Math.max(-sp, Math.min(sp, p.vx)); p.vy = Math.max(-sp, Math.min(sp, p.vy));
    moveCircle(p, p.vx * dt, p.vy * dt, AR.w);
  }
  if (hit("KeyZ") && p.dashCd === 0) {
    p.dash = AR.dash_time; p.dashCd = AR.dash_cd; play("whoosh", 0.4); emit("dash");
  }

  // auto-aim assists when standing still, otherwise shoot where you face
  const target = nearestFoe();
  if (target && !(dx || dy)) p.aim = Math.atan2(target.y - p.y, target.x - p.x);
  if (down("Space") && p.cd === 0) shoot();

  for (const b of bullets) {
    b.x += b.vx * dt; b.y += b.vy * dt; b.life -= dt;
    if (solid(b.x, b.y)) b.life = 0;
  }
  bullets = bullets.filter(b => b.life > 0);

  for (const f of foes) {
    f.phase += dt * 6;
    const d = Math.hypot(p.x - f.x, p.y - f.y) || 1;
    moveCircle(f, (p.x - f.x) / d * f.speed * dt, (p.y - f.y) / d * f.speed * dt, 6);
    if (d < 11 && p.inv === 0 && p.dash <= 0) {
      p.hp -= 1; p.inv = 1.1; addShake(0.3); hitstop(0.06); play("hurt", 0.7);
      emit("hurt", { hp: p.hp });
      moveCircle(p, (p.x - f.x) / d * 16, (p.y - f.y) / d * 16, AR.w);
      if (p.hp <= 0) {
        setBest("arena", score); scene = "over";
        emit("death", { wave, kills, score }); play("lose", 0.8);
        return;
      }
    }
    let hpLeft = f.hp;
    for (const b of bullets) {
      if (b.life <= 0) continue;
      if (Math.hypot(b.x - f.x, b.y - f.y) < 9) {
        b.life = 0; hpLeft -= 1;
        poof(b.x, b.y, "#ffcd75", 4, 30); hitstop(0.02); addShake(0.06);
      }
    }
    f.hp = hpLeft;
    if (f.hp <= 0) {
      kills += 1; score += f.kind === "brute" ? 150 : 50;
      play("kill", 0.55); poof(f.x, f.y, f.kind === "brute" ? "#ffcd75" : "#a7f070", 12); addShake(0.1);
      emit("kill", { kind: f.kind, kills });
      if (Math.random() < 0.16) pickups.push({ kind: "heart", x: f.x, y: f.y, phase: 0 });
    }
  }
  bullets = bullets.filter(b => b.life > 0);
  foes = foes.filter(f => f.hp > 0);

  for (const pk of pickups) {
    pk.phase += dt * 5;
    if (Math.hypot(pk.x - p.x, pk.y - p.y) < 11) {
      pk.got = true;
      if (pk.kind === "heart" && p.hp < cfg.player.hp) p.hp += 1;
      else score += 25;
      play("coin", 0.5); poof(pk.x, pk.y, "#ef7d57", 8); emit("pickup", { kind: pk.kind });
    }
  }
  pickups = pickups.filter(pk => !pk.got);

  if (waveState === "fight" && foes.length === 0) {
    waveState = "rest"; waveTimer = 1.6;
    score += 100 * wave; emit("wave_clear", { wave, score });
  } else if (waveState === "rest") {
    waveTimer -= dt;
    if (waveTimer <= 0) {
      wave += 1;
      if (wave > 5) {
        setBest("arena", score); scene = "win";
        emit("win", { wave: wave - 1, kills, score }); play("win", 0.8);
      } else {
        waveState = "fight"; spawnWave();
      }
    }
  }
}

// ------------------------------------------------------------------ render
function renderWorld(time) {
  const ts = images.tiles;
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, cfg.sky_top || "#29366f"); g.addColorStop(1, cfg.sky_bottom || "#1a1c2c");
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  for (let y = 0; y < mh; y++) for (let x = 0; x < mw; x++) {
    if (map[y][x] !== "#") continue;
    const h = hash(x, y), sx = ((h >> 4) % 4) * T, sy = 3 * T;
    ctx.drawImage(ts, sx, sy, T, T, x * T, y * T, T, T);
  }
  ctx.strokeStyle = "#566c86"; ctx.lineWidth = 1;
  ctx.strokeRect(0.5, 0.5, W - 1, H - 1);

  for (const pk of pickups) {
    const img = pk.kind === "heart" ? images.heart : images.coin;
    ctx.drawImage(img, Math.round(pk.x - 6), Math.round(pk.y - 6 + Math.sin(pk.phase) * 2));
  }
  const ea = atlases.enemy, ba = atlases.brute || atlases.enemy;
  for (const f of foes) {
    const a = f.kind === "brute" ? ba : ea, img = f.kind === "brute" ? (images.brute || images.enemy) : images.enemy;
    const frames = (a.tags && a.tags.idle) || [0, 1];
    const r = a.rects[frames[Math.floor(f.phase / 3) % frames.length]];
    ctx.drawImage(img, r.x, r.y, r.w, r.h, Math.round(f.x - r.w / 2), Math.round(f.y - r.h / 2), r.w, r.h);
    if (f.hp > 1) { ctx.fillStyle = "#ef7d57"; ctx.fillRect(Math.round(f.x - 5), Math.round(f.y - 10), f.hp * 3, 2); }
  }
  ctx.fillStyle = "#ffcd75";
  for (const b of bullets) ctx.fillRect(Math.round(b.x - 1), Math.round(b.y - 1), 3, 3);

  const p = player, pa = atlases.player;
  const tag = "idle_" + (Math.abs(Math.cos(p.aim)) > 0.4 ? (Math.cos(p.aim) > 0 ? "right" : "left") : "down");
  const frames = pa.tags[tag] || pa.tags.idle_down || [0];
  const r = pa.rects[frames[Math.floor(time / 300) % frames.length]];
  ctx.save();
  if (p.inv > 0 && Math.floor(time / 70) % 2) ctx.globalAlpha = 0.45;
  ctx.translate(Math.round(p.x), Math.round(p.y));
  if (Math.cos(p.aim) < -0.2) { ctx.scale(-1, 1); }
  ctx.drawImage(images.player, r.x, r.y, r.w, r.h, -r.w / 2, -r.h / 2, r.w, r.h);
  ctx.restore();
  // muzzle marker so the aim direction is readable
  ctx.strokeStyle = "#73eff7"; ctx.beginPath();
  ctx.moveTo(p.x + Math.cos(p.aim) * 9, p.y + Math.sin(p.aim) * 9);
  ctx.lineTo(p.x + Math.cos(p.aim) * 13, p.y + Math.sin(p.aim) * 13); ctx.stroke();
  drawParticles();
}

function hud() {
  for (let i = 0; i < cfg.player.hp; i++) {
    ctx.globalAlpha = i < player.hp ? 1 : 0.22; ctx.drawImage(images.heart, 4 + i * 13, 4); ctx.globalAlpha = 1;
  }
  text(`WAVE ${wave}/5`, W / 2, 9, "#ffcd75", 1, "center");
  text(String(score).padStart(5, "0"), W - 6, 9, "#f4f4f4", 1, "right");
  if (waveState === "rest") text("NEXT WAVE", W / 2, H / 2 - 30, "#73eff7", 2, "center");
  if (player.dashCd > 0) {
    ctx.fillStyle = "#1a1c2c"; ctx.fillRect(4, H - 8, 40, 3);
    ctx.fillStyle = "#73eff7"; ctx.fillRect(4, H - 8, Math.round(40 * (1 - player.dashCd / AR.dash_cd)), 3);
  }
}
function overSummary() { return `WAVE ${wave}`; }
function winSummary() { return `SCORE ${score}`; }
function genreState() {
  return { genre: GENRE, score, wave, kills, hp: player.hp, x: Math.round(player.x), y: Math.round(player.y),
    foes: foes.length, bullets: bullets.length, state: waveState, won: scene === "win" };
}

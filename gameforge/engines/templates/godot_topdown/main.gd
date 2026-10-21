extends Node2D
## GameForge top-down template for Godot 4. The level, tuning and asset paths come from
## res://level.json — the same design the web build plays — so one file drives both engines.
## gf_state() and `events` are the telemetry the GameForge playtester reads.

const T := 16

var cfg: Dictionary
var world: Node2D
var player: CharacterBody2D
var player_sprite: AnimatedSprite2D
var enemies: Array = []
var coins: Array = []
var chest: Sprite2D
var chest_open := false
var hud: Label
var banner: Label
var sfx := {}
var music: AudioStreamPlayer
var score := 0
var hp := 3
var inv := 0.0
var cooldown := 0.0
var state := "play"
var elapsed := 0.0
var events: Array = []
var face := "down"
var mw := 0
var mh := 0


func _ready() -> void:
	cfg = JSON.parse_string(FileAccess.get_file_as_string("res://level.json"))
	mh = cfg["map"].size()
	mw = cfg["map"][0].length()
	for key in cfg["assets"]["sfx"]:
		var streams: Array = []
		for path in cfg["godot"]["sfx"][key]:
			streams.append(load(path))
		var p := AudioStreamPlayer.new()
		add_child(p)
		sfx[key] = {"player": p, "streams": streams}
	music = AudioStreamPlayer.new()
	var track: AudioStreamWAV = load(cfg["godot"]["music"])
	track.loop_mode = AudioStreamWAV.LOOP_FORWARD
	track.loop_end = int(track.get_length() * track.mix_rate)
	music.stream = track
	music.volume_db = linear_to_db(cfg.get("music_volume", 0.35))
	add_child(music)
	music.play()
	build()


func cell(x: int, y: int) -> String:
	if x < 0 or y < 0 or x >= mw or y >= mh:
		return "~"
	return cfg["map"][y][x]


func land(x: int, y: int) -> int:
	return 0 if cell(x, y) == "~" else 1


func build() -> void:
	if world:
		world.queue_free()
	enemies.clear()
	coins.clear()
	score = 0
	hp = cfg["player"]["hp"]
	inv = 0.0
	elapsed = 0.0
	chest_open = false
	state = "play"
	world = Node2D.new()
	world.y_sort_enabled = true
	add_child(world)
	_build_ground()
	var walls := StaticBody2D.new()
	world.add_child(walls)
	for y in mh:
		for x in mw:
			var c := cell(x, y)
			var pos := Vector2(x * T + T / 2, y * T + T / 2)
			if c in ["~", "T", "R"]:
				var shape := CollisionShape2D.new()
				var rect := RectangleShape2D.new()
				rect.size = Vector2(T, T)
				shape.shape = rect
				shape.position = pos
				walls.add_child(shape)
			match c:
				"T": _prop("tree", x, y)
				"R": _prop("rock", x, y)
				"f": _prop("flowers", x, y)
				"c": coins.append(_sprite(cfg["godot"]["coin"], pos))
				"X": chest = _sprite(cfg["godot"]["chest"], pos)
				"s": enemies.append(_enemy(pos))
				"@": _spawn_player(pos)
	_build_hud()
	_emit("start", {"coins": coins.size(), "enemies": enemies.size()})


func _build_ground() -> void:
	# Dual grid: each tile sits on a cell corner and blends the four cells around it,
	# using the GameForge Wang sheet (index = tl*8 + tr*4 + bl*2 + br).
	var layer := TileMapLayer.new()
	layer.tile_set = load(cfg["godot"]["tileset"])
	layer.position = Vector2(-T / 2, -T / 2)
	layer.z_index = -10
	for vy in mh + 1:
		for vx in mw + 1:
			var idx := land(vx - 1, vy - 1) * 8 + land(vx, vy - 1) * 4 + land(vx - 1, vy) * 2 + land(vx, vy)
			var atlas := Vector2i(idx % 4, idx / 4)
			var h := (vx * 73856093) ^ (vy * 19349663)
			if (idx == 15 or idx == 0) and h % 3 == 0:
				atlas = Vector2i(abs(h >> 4) % 4, 4 if idx == 15 else 5)
			layer.set_cell(Vector2i(vx, vy), 0, atlas)
	world.add_child(layer)


func _sprite(path: String, pos: Vector2) -> Sprite2D:
	var s := Sprite2D.new()
	s.texture = load(path)
	s.position = pos + Vector2(0, 4)
	s.offset = Vector2(0, -s.texture.get_height() / 2.0)
	world.add_child(s)
	return s


func _prop(kind: String, x: int, y: int) -> void:
	_sprite(cfg["godot"][kind], Vector2(x * T + T / 2, y * T + T - 4))


func _body(frames: String, radius: float, pos: Vector2) -> CharacterBody2D:
	var body := CharacterBody2D.new()
	body.position = pos
	var shape := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = radius
	shape.shape = circle
	body.add_child(shape)
	var spr := AnimatedSprite2D.new()
	spr.sprite_frames = load(frames)
	spr.offset = Vector2(0, -2)
	body.add_child(spr)
	world.add_child(body)
	return body


func _spawn_player(pos: Vector2) -> void:
	player = _body(cfg["godot"]["player_frames"], 5, pos)
	player.add_to_group("player")
	player_sprite = player.get_child(1)
	player_sprite.play("idle_down")
	var cam := Camera2D.new()
	cam.limit_left = 0
	cam.limit_top = 0
	cam.limit_right = mw * T
	cam.limit_bottom = mh * T
	cam.position_smoothing_enabled = true
	player.add_child(cam)


func _enemy(pos: Vector2) -> CharacterBody2D:
	var e := _body(cfg["godot"]["enemy_frames"], 5, pos)
	(e.get_child(1) as AnimatedSprite2D).play("idle")
	e.set_meta("dir", Vector2.ZERO)
	e.set_meta("think", 0.0)
	return e


func _build_hud() -> void:
	if hud:
		hud.get_parent().queue_free()
	var layer := CanvasLayer.new()
	add_child(layer)
	hud = Label.new()
	hud.position = Vector2(4, 2)
	hud.add_theme_font_size_override("font_size", 8)
	layer.add_child(hud)
	banner = Label.new()
	banner.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	banner.size = Vector2(320, 40)
	banner.position = Vector2(0, 100)
	banner.add_theme_font_size_override("font_size", 16)
	layer.add_child(banner)


func play(key: String) -> void:
	if not sfx.has(key):
		return
	var s: Dictionary = sfx[key]
	var p: AudioStreamPlayer = s["player"]
	p.stream = s["streams"][randi() % s["streams"].size()]
	p.pitch_scale = randf_range(0.94, 1.06)
	p.play()


func _emit(type: String, data: Dictionary = {}) -> void:
	var ev := {"t": snappedf(elapsed, 0.01), "type": type}
	ev.merge(data)
	events.append(ev)


func gf_state() -> Dictionary:
	var left := coins.filter(func(c): return is_instance_valid(c) and c.visible).size()
	return {"scene": state, "score": score, "hp": hp, "x": player.position.x, "y": player.position.y,
		"coins_left": left, "enemies": enemies.size(), "seconds": snappedf(elapsed, 0.1)}


func _physics_process(delta: float) -> void:
	if state != "play":
		if Input.is_action_just_pressed("ui_accept"):
			build()
		return
	elapsed += delta
	var dir := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
	player.velocity = dir * float(cfg["player"]["speed"])
	player.move_and_slide()
	if dir != Vector2.ZERO:
		face = ("right" if dir.x > 0 else "left") if abs(dir.x) > abs(dir.y) else ("down" if dir.y > 0 else "up")
	player_sprite.play(("walk_" if dir != Vector2.ZERO else "idle_") + face)
	inv = max(0.0, inv - delta)
	cooldown = max(0.0, cooldown - delta)
	player_sprite.visible = inv == 0.0 or int(elapsed * 12) % 2 == 0
	if Input.is_action_just_pressed("ui_select") and cooldown == 0.0:
		cooldown = cfg["player"]["attack_cooldown"]
		play("attack")
		_emit("attack")
		for e in enemies.duplicate():
			if e.position.distance_to(player.position) < float(cfg["player"]["attack_radius"]):
				enemies.erase(e)
				e.queue_free()
				score += 50
				play("kill")
				_emit("kill")
	_update_enemies(delta)
	for c in coins:
		if c.visible and c.position.distance_to(player.position + Vector2(0, 4)) < 11:
			c.visible = false
			score += 10
			play("coin")
			_emit("coin", {"left": gf_state()["coins_left"]})
	var all_coins: bool = gf_state()["coins_left"] == 0
	chest.modulate.a = 1.0 if all_coins else 0.55
	if all_coins and not chest_open and chest.position.distance_to(player.position) < 16:
		chest_open = true
		score += 200
		play("win")
		_emit("win", {"score": score, "seconds": snappedf(elapsed, 0.1)})
		state = "win"
		banner.text = "VICTORY!  SCORE %d\nENTER TO PLAY AGAIN" % score
	hud.text = "HP %d   COINS %d/%d   SCORE %05d" % [hp, coins.size() - gf_state()["coins_left"], coins.size(), score]


func _update_enemies(delta: float) -> void:
	for e in enemies:
		var to_p: Vector2 = player.position - e.position
		var d := to_p.length()
		var think: float = e.get_meta("think") - delta
		if d < float(cfg["enemy"]["chase_radius"]):
			e.set_meta("dir", to_p.normalized())
		elif think <= 0.0:
			e.set_meta("dir", Vector2.from_angle(randf() * TAU) * 0.5)
			think = randf_range(1.0, 3.0)
		e.set_meta("think", think)
		e.velocity = e.get_meta("dir") * float(cfg["enemy"]["speed"])
		e.move_and_slide()
		if d < 11 and inv == 0.0:
			hp -= 1
			inv = 1.2
			play("hurt")
			_emit("hurt", {"hp": hp})
			player.position += to_p.normalized() * 10
			if hp <= 0:
				state = "over"
				play("lose")
				_emit("death", {"score": score})
				banner.text = "GAME OVER\nENTER TO RETRY"

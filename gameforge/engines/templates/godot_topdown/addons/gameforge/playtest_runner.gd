extends Node
## GameForge playtest bot. Loads the project's main scene as a child and plays it through the input
## map (ui_* actions), exploring toward unvisited ground, attacking near enemies and restarting after
## game over. Works with any game; games that expose gf_state()/events on their root give richer data.
## Run headless with --fixed-fps so minutes of play simulate in seconds:
##   godot --headless --fixed-fps 60 --path <project> res://addons/gameforge/playtest_runner.tscn -- --duration=120 --out=/abs/report.json

var duration := 60.0
var out_path := "user://gameforge_playtest.json"
var game: Node
var t := 0.0
var rng := RandomNumberGenerator.new()
var held: Array[String] = []
var next_change := 0.0
var visited := {}
var walls := {}
var last_pos := Vector2.INF
var still := 0.0
var stuck: Array = []
var frame_ms: Array = []
var samples: Array = []
var restarts := 0
var prev_scene := ""
var shots_dir := ""
var shot_every := 10.0
var next_shot := 1.0
var shots: Array = []
const DIRS := {"ui_up": Vector2(0, -1), "ui_down": Vector2(0, 1), "ui_left": Vector2(-1, 0), "ui_right": Vector2(1, 0)}


func _ready() -> void:
	rng.seed = 1
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--duration="):
			duration = float(arg.get_slice("=", 1))
		elif arg.begins_with("--out="):
			out_path = arg.get_slice("=", 1)
		elif arg.begins_with("--seed="):
			rng.seed = int(arg.get_slice("=", 1))
		elif arg.begins_with("--shots="):
			shots_dir = arg.get_slice("=", 1)
		elif arg.begins_with("--shot-every="):
			shot_every = float(arg.get_slice("=", 1))
	var main_scene: String = ProjectSettings.get_setting("application/run/main_scene")
	game = load(main_scene).instantiate()
	add_child(game)


func _state() -> Dictionary:
	return game.gf_state() if game.has_method("gf_state") else {}


func _cell(p: Vector2) -> Vector2i:
	return Vector2i(int(p.x / 48), int(p.y / 48))


func _hold(actions: Array[String]) -> void:
	for a in held:
		if a not in actions:
			Input.action_release(a)
	for a in actions:
		if a not in held:
			Input.action_press(a)
	held = actions


func _pick(pos: Vector2, blocked: bool) -> String:
	var best := ""
	var best_score := INF
	var c := _cell(pos)
	for a in DIRS:
		var d: Vector2 = DIRS[a]
		var seen := 0
		for s in [1, 2, 3]:
			seen += visited.get(c + Vector2i(d * s), 0)
		var penalty := 200 if walls.has([c, a]) else 0
		if blocked and a in held:
			penalty += 50
		var score := seen + penalty + rng.randf() * 6.0
		if score < best_score:
			best_score = score
			best = a
	return best


func _physics_process(delta: float) -> void:
	t += delta
	frame_ms.append(Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0)
	var st := _state()
	var scene: String = st.get("scene", "play")
	if scene != prev_scene and scene in ["over", "win"]:
		restarts += 1
		_hold([])
	prev_scene = scene
	if scene in ["over", "win"]:
		if int(t * 10) % 10 == 0:
			Input.action_press("ui_accept")
		else:
			Input.action_release("ui_accept")
		return
	var pos := Vector2(st.get("x", 0), st.get("y", 0))
	if st.has("x"):
		var c := _cell(pos)
		visited[c] = visited.get(c, 0) + 1
		if last_pos != Vector2.INF and pos.distance_to(last_pos) < 0.05 and not held.is_empty():
			still += delta
			if still > 4.0 and (stuck.is_empty() or t - stuck[-1]["t"] > 8.0):
				stuck.append({"t": snappedf(t, 0.1), "x": pos.x, "y": pos.y, "holding": held.duplicate()})
		else:
			still = 0.0
		last_pos = pos
	var blocked := still > 0.4
	if blocked and not held.is_empty() and st.has("x"):
		walls[[_cell(pos), held[0]]] = true
	if t > next_change or blocked:
		var choice: Array[String] = [_pick(pos, blocked)]
		if rng.randf() < 0.25:
			choice.append(DIRS.keys()[rng.randi() % 4])
		_hold(choice)
		next_change = t + rng.randf_range(0.6, 1.8)
	if rng.randf() < 0.02:
		Input.action_press("ui_select")
	else:
		Input.action_release("ui_select")
	if int(t * 2) != int((t - delta) * 2):
		samples.append({"t": snappedf(t, 0.1), "state": st})
	if shots_dir != "" and t >= next_shot and DisplayServer.get_name() != "headless":
		next_shot = t + shot_every
		var path := "%s/godot_%04d.png" % [shots_dir, int(t * 10)]
		get_viewport().get_texture().get_image().save_png(path)
		shots.append({"t": snappedf(t, 0.1), "file": path.get_file(), "scene": scene})
	if t >= duration:
		_finish()


func _finish() -> void:
	set_physics_process(false)
	_hold([])
	var events: Array = game.get("events") if game.get("events") != null else []
	frame_ms.sort()
	var report := {
		"duration_s": snappedf(t, 0.1), "engine": "godot " + Engine.get_version_info()["string"],
		"telemetry": game.has_method("gf_state"), "events": events, "stuck": stuck, "restarts": restarts,
		"coverage_cells": visited.size(), "samples": samples, "shots": shots,
		"frame_ms": {"p50": frame_ms[frame_ms.size() / 2], "p95": frame_ms[int(frame_ms.size() * 0.95)],
			"max": frame_ms[-1]},
	}
	var f := FileAccess.open(out_path, FileAccess.WRITE)
	f.store_string(JSON.stringify(report, " "))
	f.close()
	print("GAMEFORGE_PLAYTEST_DONE ", out_path)
	get_tree().quit()

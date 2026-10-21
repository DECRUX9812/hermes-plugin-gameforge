// GameForge top-down template for Unity (2021.3+ / Unity 6). Builds the level at runtime from
// Resources/GameForge/level.json — the same design the web and Godot builds play — and slices the
// sprite sheets at runtime, so no import-time slicing setup is needed. Legacy Input Manager axes.
using System;
using System.Collections.Generic;
using UnityEngine;

namespace GameForge
{
    [Serializable] public class Rect4 { public int x, y, w, h; }
    [Serializable] public class Anim { public string name; public int[] frames; }
    [Serializable] public class SheetInfo { public string texture; public Rect4[] rects; public Anim[] anims; }
    [Serializable] public class PlayerCfg { public float speed = 72; public int hp = 3; public float attack_radius = 26; public float attack_cooldown = 0.6f; }
    [Serializable] public class EnemyCfg { public float speed = 28; public float chase_radius = 70; }
    [Serializable] public class SfxList { public string name; public string[] clips; }
    [Serializable] public class Level
    {
        public string title;
        public string[] map;
        public PlayerCfg player;
        public EnemyCfg enemy;
        public SheetInfo player_sheet, enemy_sheet;
        public string tiles, coin, chest, tree, rock, flowers, music;
        public SfxList[] sfx;
        public float music_volume = 0.35f;
    }

    public class GameForgeTopDown : MonoBehaviour
    {
        const float PPU = 16f;
        Level cfg;
        Transform world;
        Transform player;
        SpriteRenderer playerSr;
        readonly List<Transform> enemies = new List<Transform>();
        readonly List<SpriteRenderer> coins = new List<SpriteRenderer>();
        SpriteRenderer chest;
        Sprite[] playerFrames, enemyFrames;
        readonly Dictionary<string, int[]> playerAnims = new Dictionary<string, int[]>();
        readonly Dictionary<string, AudioClip[]> sfx = new Dictionary<string, AudioClip[]>();
        AudioSource sfxSource;
        int score, hp, mw, mh;
        float inv, cooldown, elapsed, animT;
        string face = "down";
        public string state = "play";
        public readonly List<string> events = new List<string>();

        void Start()
        {
            cfg = JsonUtility.FromJson<Level>(Resources.Load<TextAsset>("GameForge/level").text);
            mh = cfg.map.Length;
            mw = cfg.map[0].Length;
            playerFrames = Slice(cfg.player_sheet);
            enemyFrames = Slice(cfg.enemy_sheet);
            foreach (var a in cfg.player_sheet.anims) playerAnims[a.name] = a.frames;
            sfxSource = gameObject.AddComponent<AudioSource>();
            foreach (var s in cfg.sfx)
            {
                var clips = new List<AudioClip>();
                foreach (var c in s.clips) { var clip = Resources.Load<AudioClip>(c); if (clip) clips.Add(clip); }
                sfx[s.name] = clips.ToArray();
            }
            var music = gameObject.AddComponent<AudioSource>();
            music.clip = Resources.Load<AudioClip>(cfg.music);
            music.loop = true;
            music.volume = cfg.music_volume;
            if (music.clip) music.Play();
            var cam = Camera.main;
            cam.orthographic = true;
            cam.orthographicSize = 240f / PPU / 2f;
            cam.backgroundColor = new Color32(26, 28, 44, 255);
            Build();
        }

        Sprite[] Slice(SheetInfo sheet)
        {
            var tex = Resources.Load<Texture2D>(sheet.texture);
            tex.filterMode = FilterMode.Point;
            var list = new Sprite[sheet.rects.Length];
            for (int i = 0; i < sheet.rects.Length; i++)
            {
                var r = sheet.rects[i];
                // atlas rects are top-left based; Unity textures are bottom-left based
                list[i] = Sprite.Create(tex, new Rect(r.x, tex.height - r.y - r.h, r.w, r.h), new Vector2(0.5f, 0.15f), PPU);
            }
            return list;
        }

        Sprite Single(string path, float pivotY = 0.1f)
        {
            var tex = Resources.Load<Texture2D>(path);
            tex.filterMode = FilterMode.Point;
            return Sprite.Create(tex, new Rect(0, 0, tex.width, tex.height), new Vector2(0.5f, pivotY), PPU);
        }

        char Cell(int x, int y) => (x < 0 || y < 0 || x >= mw || y >= mh) ? '~' : cfg.map[y][x];
        int Land(int x, int y) => Cell(x, y) == '~' ? 0 : 1;
        Vector3 WorldPos(float px, float py) => new Vector3(px / PPU, -py / PPU, 0);

        void Build()
        {
            if (world) Destroy(world.gameObject);
            enemies.Clear(); coins.Clear();
            score = 0; hp = cfg.player.hp; inv = 0; elapsed = 0; state = "play";
            world = new GameObject("World").transform;
            var tileTex = Resources.Load<Texture2D>(cfg.tiles);
            tileTex.filterMode = FilterMode.Point;
            var tiles = new Sprite[24];
            for (int i = 0; i < 24; i++)
                tiles[i] = Sprite.Create(tileTex, new Rect(i % 4 * 16, tileTex.height - (i / 4 + 1) * 16, 16, 16), new Vector2(0.5f, 0.5f), PPU);
            // dual grid: each tile sits on a cell corner and blends the four cells around it
            for (int vy = 0; vy <= mh; vy++)
                for (int vx = 0; vx <= mw; vx++)
                {
                    int idx = Land(vx - 1, vy - 1) * 8 + Land(vx, vy - 1) * 4 + Land(vx - 1, vy) * 2 + Land(vx, vy);
                    Spawn("tile", tiles[idx], WorldPos(vx * 16, vy * 16), -1000);
                }
            Sprite coin = Single(cfg.coin), chestS = Single(cfg.chest), tree = Single(cfg.tree), rock = Single(cfg.rock), flowers = Single(cfg.flowers);
            for (int y = 0; y < mh; y++)
                for (int x = 0; x < mw; x++)
                {
                    var p = WorldPos(x * 16 + 8, y * 16 + 12);
                    switch (cfg.map[y][x])
                    {
                        case 'T': Spawn("tree", tree, p); break;
                        case 'R': Spawn("rock", rock, p); break;
                        case 'f': Spawn("flowers", flowers, p); break;
                        case 'c': coins.Add(Spawn("coin", coin, p)); break;
                        case 'X': chest = Spawn("chest", chestS, p); break;
                        case 's': enemies.Add(Spawn("enemy", enemyFrames[0], p).transform); break;
                        case '@':
                            playerSr = Spawn("player", playerFrames[0], p);
                            player = playerSr.transform;
                            break;
                    }
                }
            events.Add("start");
        }

        SpriteRenderer Spawn(string name, Sprite s, Vector3 pos, int order = 0)
        {
            var go = new GameObject(name);
            go.transform.SetParent(world, false);
            go.transform.position = pos;
            var sr = go.AddComponent<SpriteRenderer>();
            sr.sprite = s;
            sr.sortingOrder = order != 0 ? order : Mathf.RoundToInt(-pos.y * 16);
            return sr;
        }

        bool Solid(Vector3 p)
        {
            int cx = Mathf.FloorToInt(p.x * PPU / 16f), cy = Mathf.FloorToInt(-p.y * PPU / 16f);
            char c = Cell(cx, cy);
            return c == '~' || c == 'T' || c == 'R';
        }

        void Move(Transform t, Vector3 delta)
        {
            const float r = 5f / PPU;
            var nx = t.position + new Vector3(delta.x, 0, 0);
            if (!Solid(nx + new Vector3(r, r)) && !Solid(nx + new Vector3(-r, -r)) && !Solid(nx + new Vector3(r, -r)) && !Solid(nx + new Vector3(-r, r))) t.position = nx;
            var ny = t.position + new Vector3(0, delta.y, 0);
            if (!Solid(ny + new Vector3(r, r)) && !Solid(ny + new Vector3(-r, -r)) && !Solid(ny + new Vector3(r, -r)) && !Solid(ny + new Vector3(-r, r))) t.position = ny;
        }

        void Play(string key)
        {
            if (sfx.TryGetValue(key, out var clips) && clips.Length > 0)
                sfxSource.PlayOneShot(clips[UnityEngine.Random.Range(0, clips.Length)]);
        }

        void Update()
        {
            if (state != "play")
            {
                if (Input.GetKeyDown(KeyCode.Return)) Build();
                return;
            }
            float dt = Time.deltaTime;
            elapsed += dt;
            var dir = new Vector3(Input.GetAxisRaw("Horizontal"), Input.GetAxisRaw("Vertical"), 0);
            if (dir.sqrMagnitude > 1) dir.Normalize();
            if (dir != Vector3.zero)
            {
                face = Mathf.Abs(dir.x) > Mathf.Abs(dir.y) ? (dir.x > 0 ? "right" : "left") : (dir.y > 0 ? "up" : "down");
                Move(player, dir * cfg.player.speed / PPU * dt);
                animT += dt * 8;
            }
            if (playerAnims.TryGetValue((dir != Vector3.zero ? "walk_" : "idle_") + face, out var frames))
                playerSr.sprite = playerFrames[frames[(int)(dir != Vector3.zero ? animT : elapsed * 2) % frames.Length]];
            playerSr.sortingOrder = Mathf.RoundToInt(-player.position.y * 16);
            inv = Mathf.Max(0, inv - dt);
            cooldown = Mathf.Max(0, cooldown - dt);
            playerSr.enabled = inv == 0 || ((int)(elapsed * 12)) % 2 == 0;
            if (Input.GetKeyDown(KeyCode.Space) && cooldown == 0)
            {
                cooldown = cfg.player.attack_cooldown; Play("attack"); events.Add("attack");
                for (int i = enemies.Count - 1; i >= 0; i--)
                    if (Vector3.Distance(enemies[i].position, player.position) * PPU < cfg.player.attack_radius)
                    { Destroy(enemies[i].gameObject); enemies.RemoveAt(i); score += 50; Play("kill"); events.Add("kill"); }
            }
            foreach (var e in enemies)
            {
                var to = player.position - e.position;
                var d = to.magnitude * PPU;
                var step = d < cfg.enemy.chase_radius ? to.normalized : (Vector3)UnityEngine.Random.insideUnitCircle * 0.5f;
                Move(e, step * cfg.enemy.speed / PPU * dt);
                var sr = e.GetComponent<SpriteRenderer>();
                sr.sprite = enemyFrames[(int)(elapsed * 2) % enemyFrames.Length];
                sr.sortingOrder = Mathf.RoundToInt(-e.position.y * 16);
                if (d < 11 && inv == 0)
                {
                    hp--; inv = 1.2f; Play("hurt"); events.Add("hurt");
                    Move(player, -to.normalized * 10f / PPU);
                    if (hp <= 0) { state = "over"; Play("lose"); events.Add("death"); }
                }
            }
            int left = 0;
            foreach (var c in coins)
            {
                if (!c.enabled) continue;
                if (Vector3.Distance(c.transform.position, player.position) * PPU < 11) { c.enabled = false; score += 10; Play("coin"); events.Add("coin"); }
                else left++;
            }
            chest.color = new Color(1, 1, 1, left == 0 ? 1f : 0.55f);
            if (left == 0 && Vector3.Distance(chest.transform.position, player.position) * PPU < 16)
            { state = "win"; score += 200; Play("win"); events.Add("win"); }
            var cam = Camera.main.transform;
            cam.position = Vector3.Lerp(cam.position, new Vector3(player.position.x, player.position.y, -10), Mathf.Min(1, dt * 6));
        }

        void OnGUI()
        {
            if (cfg == null) return;
            int left = 0; foreach (var c in coins) if (c.enabled) left++;
            GUI.Label(new Rect(10, 8, 600, 24), $"HP {hp}   COINS {coins.Count - left}/{coins.Count}   SCORE {score:00000}");
            if (state != "play")
                GUI.Label(new Rect(Screen.width / 2 - 120, Screen.height / 2 - 20, 240, 60),
                    state == "win" ? $"VICTORY!  SCORE {score}\nENTER TO PLAY AGAIN" : "GAME OVER\nENTER TO RETRY");
        }
    }
}

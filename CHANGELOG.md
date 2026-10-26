# Changelog

## 1.1.1 — 2026-10-26

Security fixes from catalog review (NousResearch/hermes-agent#142443), delta from `d88bdd1d`:

- **Profile-scoped secrets.** `FAL_KEY`, `MESHY_API_KEY`, `TRIPO_API_KEY` and
  `ELEVENLABS_API_KEY` resolve through `agent.secret_scope.get_secret`, so one process serving
  several profiles can no longer hand a tool another profile's key. Environment is a fallback
  only when that module is unavailable.
- **`forge_engine` + Blender `action=script`** now goes through the human approval gate via a
  `pre_tool_call` hook (`gameforge/policy.py`); the runner executes a caller-named Python file.
- **`forge_export`** resolves `source` and refuses anything outside the project directory;
  `target=itch` requires an approval before a public upload.
- **`forge_model3d` image upload** accepts a local image only inside the project directory, with a
  real image extension and matching magic bytes.
- **Godot export templates** are verified against `SHA512-SUMS.txt` before extraction (fail
  closed), and `_extract_tpz` skips absolute names and any member resolving outside `dest_root`.

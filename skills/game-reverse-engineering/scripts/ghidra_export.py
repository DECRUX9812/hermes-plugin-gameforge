#!/usr/bin/env python3
"""Headless Ghidra: import + analyze a binary, then export decompiled C per function and an index.

Usage: python ghidra_export.py --ghidra /opt/ghidra_11.x --binary game.exe --out decomp/
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Runs inside Ghidra (Jython/PyGhidra): decompile every function to <out>/<name>@<addr>.c + functions.json
POST_SCRIPT = r'''
import json, os
from ghidra.app.decompiler import DecompInterface
out = getScriptArgs()[0]
if not os.path.isdir(out):
    os.makedirs(out)
iface = DecompInterface()
iface.openProgram(currentProgram)
index = []
fm = currentProgram.getFunctionManager()
for f in fm.getFunctions(True):
    res = iface.decompileFunction(f, 60, monitor)
    name = f.getName()
    addr = str(f.getEntryPoint())
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)[:80]
    path = os.path.join(out, "%s@%s.c" % (safe, addr))
    if res.decompileCompleted():
        with open(path, "w") as fh:
            fh.write(res.getDecompiledFunction().getC())
    index.append({"name": name, "address": addr, "size": f.getBody().getNumAddresses(),
                  "callers": [c.getName() for c in f.getCallingFunctions(monitor)][:20],
                  "file": os.path.basename(path) if res.decompileCompleted() else None})
with open(os.path.join(out, "functions.json"), "w") as fh:
    json.dump(index, fh, indent=1)
print("GAMEFORGE_DECOMP %d functions" % len(index))
'''


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ghidra", required=True, help="Ghidra install directory")
    ap.add_argument("--binary", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    exe = "analyzeHeadless.bat" if os.name == "nt" else "analyzeHeadless"
    headless = Path(a.ghidra).expanduser() / "support" / exe
    if not headless.exists():
        print(f"not found: {headless}", file=sys.stderr)
        return 2
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ghidra-proj-") as proj, tempfile.TemporaryDirectory() as sd:
        script = Path(sd) / "GameForgeExport.py"
        script.write_text(POST_SCRIPT, encoding="utf-8")
        cmd = [str(headless), proj, "gameforge", "-import", str(Path(a.binary).resolve()), "-scriptPath", sd,
               "-postScript", script.name, str(out), "-deleteProject"]
        return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())

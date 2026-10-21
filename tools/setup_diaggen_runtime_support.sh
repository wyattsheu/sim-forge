#!/usr/bin/env bash
# Restore the encoder entrypoint missing from this DiagGen source release.
set -euo pipefail
TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$TOOLS_DIR/diaggen_support/generate_simulation_mp4.sh"
TARGET="$TOOLS_DIR/diaggen/scripts/generate_simulation_mp4.sh"
[[ -f "$SOURCE" && -d "$TOOLS_DIR/diaggen/scripts" ]]
if [[ -e "$TARGET" || -L "$TARGET" ]]; then
    [[ "$(readlink -f "$TARGET")" == "$(readlink -f "$SOURCE")" ]] || {
        echo 'Existing upstream encoder differs; preserve it and test before replacing.' >&2
        exit 1
    }
else
    ln -s "$(realpath --relative-to="$(dirname "$TARGET")" "$SOURCE")" "$TARGET"
fi
chmod +x "$SOURCE"
python3 - "$TOOLS_DIR" <<'PY'
import hashlib
import json
from pathlib import Path
import subprocess
import sys

tools = Path(sys.argv[1])
support = tools / "diaggen_support"
manifest = json.loads((support / "strict_material_coverage.json").read_text())
patch = support / "strict_material_coverage.patch"
target = tools / "diaggen" / manifest["target"]
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
if digest(patch) != manifest["patch_sha256"]:
    raise SystemExit("Verified material-coverage patch hash differs")
current = digest(target)
if current == manifest["before_sha256"]:
    args = ["patch", "--batch", "--forward", "-p1", "--input", str(patch)]
    subprocess.run(args + ["--dry-run"], cwd=tools / "diaggen", check=True)
    subprocess.run(args, cwd=tools / "diaggen", check=True)
elif current != manifest["after_sha256"]:
    raise SystemExit("Native meshing source changed; review upstream before applying patch")
if digest(target) != manifest["after_sha256"]:
    raise SystemExit("Native material-coverage patch verification failed")
print("Strict material coverage patch verified")
PY
printf '%s\n' "$TARGET"

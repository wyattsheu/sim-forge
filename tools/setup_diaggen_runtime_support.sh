#!/usr/bin/env bash
# Restore verified support patches and the missing encoder entrypoint.
# Run only after the DiagGen runtime using these sources has stopped.
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
fi
python3 - "$TOOLS_DIR" <<'PY'
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

tools = Path(sys.argv[1])
support = tools / "diaggen_support"
native = tools / "diaggen"
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
plans = []
for name in ("strict_material_coverage", "diagnostic_history_settlement"):
    manifest = json.loads((support / f"{name}.json").read_text())
    patch = support / f"{name}.patch"
    target = native / manifest["target"]
    if manifest.get("schema_version") != "diaggen-verified-native-patch-v1":
        raise SystemExit(f"Unsupported verified patch manifest: {name}")
    if not target.resolve().is_relative_to(native.resolve()):
        raise SystemExit(f"Verified patch target escapes the native source tree: {name}")
    if digest(patch) != manifest["patch_sha256"]:
        raise SystemExit(f"Verified patch hash differs: {name}")
    current = digest(target)
    if current not in {manifest["before_sha256"], manifest["after_sha256"]}:
        raise SystemExit(f"Native source changed; review upstream before applying patch: {name}")
    args = ["patch", "--batch", "--forward", "--fuzz=0", "-p1", "--input", str(patch)]
    if current == manifest["before_sha256"]:
        # Validate every candidate before changing either native source. This
        # also verifies the declared after-hash without trusting patch output.
        with tempfile.TemporaryDirectory(prefix="diaggen-support-check-") as folder:
            candidate = Path(folder) / manifest["target"]
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(target.read_bytes())
            subprocess.run(args + ["--dry-run"], cwd=folder, check=True)
            subprocess.run(args, cwd=folder, check=True)
            if digest(candidate) != manifest["after_sha256"]:
                raise SystemExit(f"Native patch candidate verification failed: {name}")
    plans.append((name, manifest, patch, target, current, args))

for name, manifest, patch, target, current, args in plans:
    if digest(patch) != manifest["patch_sha256"] or digest(target) != current:
        raise SystemExit(f"Native source or patch changed during verification: {name}")
    if current == manifest["before_sha256"]:
        subprocess.run(args + ["--dry-run"], cwd=native, check=True)
        subprocess.run(args, cwd=native, check=True)
    if digest(target) != manifest["after_sha256"]:
        raise SystemExit(f"Native patch verification failed: {name}")
    print(f"Verified native patch: {name}")
PY
if [[ ! -e "$TARGET" && ! -L "$TARGET" ]]; then
    ln -s "$(realpath --relative-to="$(dirname "$TARGET")" "$SOURCE")" "$TARGET"
fi
chmod +x "$SOURCE"
printf '%s\n' "$TARGET"

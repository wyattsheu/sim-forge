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
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

tools = Path(sys.argv[1])
support = tools / "diaggen_support"
native = tools / "diaggen"
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
series = json.loads((support / "native_patches.json").read_text())
names = series.get("patches")
if (series.get("schema_version") != "diaggen-native-patch-series-v1"
        or not isinstance(names, list) or not names or len(names) != len(set(names))
        or any(not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]+", name) for name in names)):
    raise SystemExit("Invalid verified native patch series")
chains = {}
for name in names:
    manifest = json.loads((support / f"{name}.json").read_text())
    patch = support / f"{name}.patch"
    target = native / manifest["target"]
    if manifest.get("schema_version") != "diaggen-verified-native-patch-v1":
        raise SystemExit(f"Unsupported verified patch manifest: {name}")
    if not target.resolve().is_relative_to(native.resolve()):
        raise SystemExit(f"Verified patch target escapes the native source tree: {name}")
    if digest(patch) != manifest["patch_sha256"]:
        raise SystemExit(f"Verified patch hash differs: {name}")
    chain = chains.setdefault(manifest["target"], [])
    if chain and chain[-1][1]["after_sha256"] != manifest["before_sha256"]:
        raise SystemExit(f"Verified patch chain is discontinuous: {name}")
    chain.append((name, manifest, patch))

plans = []
# Reconstruct each known source from its declared pristine baseline, then
# replay the complete chain in a disposable copy. No native file changes
# until every source, every intermediate hash, and every patch is verified.
with tempfile.TemporaryDirectory(prefix="diaggen-support-check-") as folder:
    for relative, chain in chains.items():
        target = native / relative
        initial = target.read_bytes()
        current = digest(target)
        known = [chain[0][1]["before_sha256"], *[item[1]["after_sha256"] for item in chain]]
        if current not in known or len(known) != len(set(known)):
            raise SystemExit(f"Native source changed; review upstream before applying patch: {relative}")
        position = known.index(current)
        candidate = Path(folder) / relative
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(initial)

        def apply_one(item, reverse=False):
            name, manifest, patch = item
            command = ["patch", "--batch", "--fuzz=0", "-p1", "--input", str(patch),
                       "--reverse" if reverse else "--forward"]
            subprocess.run(command + ["--dry-run"], cwd=folder, check=True, capture_output=True)
            subprocess.run(command, cwd=folder, check=True, capture_output=True)
            expected = manifest["before_sha256"] if reverse else manifest["after_sha256"]
            if digest(candidate) != expected:
                raise SystemExit(f"Native patch candidate verification failed: {name}")

        for item in reversed(chain[:position]):
            apply_one(item, reverse=True)
        for item in chain:
            apply_one(item)
        plans.append((target, initial, candidate.read_bytes(), current))

    # All verified candidates exist before the first native mutation.
    for chain in chains.values():
        for name, manifest, patch in chain:
            if digest(patch) != manifest["patch_sha256"]:
                raise SystemExit(f"Verified patch changed during validation: {name}")
    for target, initial, updated, current in plans:
        if digest(target) != current:
            raise SystemExit(f"Native source changed during validation: {target.name}")
    for target, initial, updated, current in plans:
        if initial != updated:
            fd, temporary = tempfile.mkstemp(prefix=".diaggen-support-", dir=target.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(updated)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary, target.stat().st_mode & 0o777)
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        if digest(target) != hashlib.sha256(updated).hexdigest():
            raise SystemExit(f"Installed native source verification failed: {target.name}")
        print(f"Verified native patch chain: {target.relative_to(native)}")
PY
if [[ ! -e "$TARGET" && ! -L "$TARGET" ]]; then
    ln -s "$(realpath --relative-to="$(dirname "$TARGET")" "$SOURCE")" "$TARGET"
fi
chmod +x "$SOURCE"
printf '%s\n' "$TARGET"

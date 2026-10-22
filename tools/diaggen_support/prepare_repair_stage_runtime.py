#!/usr/bin/env python3
"""Guard the existing native repair-revision terminal recovery call.

Parent bookkeeping only. This does not choose a route, run a stage, touch live
diagnostic ownership, or remove a terminal authored in the current revision.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys


NATIVE_ROOT = Path(__file__).resolve().parents[1] / "diaggen"
RERUN_KEYS = {
    "segmentation": ("segmentation", "omnipart", "material_inference", "mesh_processing", "post_mesh_texture", "final_export"),
    "material_inference": ("material_inference", "mesh_processing", "post_mesh_texture", "final_export"),
    "mesh_processing": ("mesh_processing", "post_mesh_texture", "final_export"),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(run_root: Path, *, apply=False, diaggen_root=None):
    root = Path(diaggen_root or NATIVE_ROOT).resolve()
    run = Path(run_root).absolute()
    require(run == run.resolve() and run.parent == root / "outputs/agentic_asset_refinement",
            "Run must use the canonical native layout without symlinks")
    state_path = run / "state.json"
    before_sha = digest(state_path)
    state = json.loads(state_path.read_text())
    require(state.get("run_root") == str(run) and state.get("status") in ("seeded", "running"),
            "Only an unfinished native run is eligible")
    require(not state.get("accepted_revision") and not state.get("exported_revision"),
            "Accepted or exported runs cannot reopen stage submissions")
    require(all(record.get("status") in ("completed", "failed", "expired", "superseded")
                for record in state.get("diagnostic_runtime_attachments", []))
            and all(record.get("lifecycle_state") in ("closed", "closed_failed")
                    for record in state.get("diagnostic_runtime_sessions", [])),
            "Recovery cannot run while diagnostic ownership is active")
    active = state.get("active_revision")
    repair = state.get("route_state", {}).get("active_repair_revision", {})
    route, base_id = repair.get("route"), repair.get("base_revision")
    require(route in RERUN_KEYS and repair.get("new_revision") == active,
            "Current active repair revision and supported native route are required")
    revisions = state.get("revisions", {})
    metadata = revisions.get(active, {})
    require(metadata.get("status") == "active" and metadata.get("base_revision") == base_id
            and metadata.get("rerun_route") == route, "Repair revision provenance mismatch")
    require(isinstance(base_id, str) and base_id.startswith("revision_")
            and base_id.removeprefix("revision_").isdecimal()
            and active == f"revision_{int(base_id.removeprefix('revision_')) + 1:04d}",
            "Repair must follow its immediate previous revision")
    require(revisions.get(base_id, {}).get("status") == "superseded"
            and revisions[base_id].get("superseded_by") == active, "Base must be superseded by this repair")
    base_path = run / "revisions" / base_id / "state.json"
    require(base_path.resolve() == base_path and base_path.is_file(), "Immutable base snapshot is missing or unsafe")
    base_sha = digest(base_path)
    base = json.loads(base_path.read_text())
    require(base.get("run_root") == str(run) and base.get("active_revision") == base_id,
            "Base snapshot belongs to a different run or revision")
    created = datetime.fromisoformat(metadata["created_at"])
    affected = []
    runtime = state.get("stage_runtime", {})
    for key in RERUN_KEYS[route]:
        record = runtime.get(key, {})
        if "terminal" not in record:
            continue
        terminal = record["terminal"]
        require(isinstance(terminal, dict) and terminal == base.get("stage_runtime", {}).get(key, {}).get("terminal"),
                f"Refusing to remove a current or unproven terminal: {key}")
        require(terminal.get("status") != "halted" and datetime.fromisoformat(terminal["timestamp"]) < created,
                f"Refusing a halted or newly authored terminal: {key}")
        affected.append(key)
    report = {"schema_version": "diaggen-native-repair-stage-terminals-v1", "valid": True,
              "revision": active, "base_revision": base_id, "route": route,
              "inherited_terminal_keys": affected, "state_before_sha256": before_sha,
              "base_snapshot_sha256": base_sha, "applied": False}
    if not apply or not affected:
        return report
    require(digest(state_path) == before_sha, "State changed after inspection")
    sys.path.insert(0, str(NATIVE_ROOT))
    from hag4r.agentic import runtime_state
    require(Path(runtime_state.__file__).resolve() == NATIVE_ROOT.resolve() / "hag4r/agentic/runtime_state.py",
            "Recovery must use this checkout's existing native implementation")
    runtime_state.reset_active_revision_stage_runtime_terminals(run)
    after = json.loads(state_path.read_text())
    expected_runtime = deepcopy(runtime)
    for key in affected:
        expected_runtime[key].pop("terminal", None)
        expected_runtime[key].pop("diagnostic_response_summary", None)
    require(after.get("stage_runtime", {}) == expected_runtime, "Unexpected runtime recovery mutation")
    for key in ("stages", "completed_global_stage_sequence", "active_revision", "revisions", "route_state",
                "diagnostics", "diagnostic_runtime_attachments", "diagnostic_runtime_sessions"):
        require(after.get(key) == state.get(key), f"Recovery changed unrelated state: {key}")
    require(digest(base_path) == base_sha, "Immutable base snapshot changed")
    report.update(applied=True, state_after_sha256=digest(state_path))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.run_root, apply=args.apply), sort_keys=True))
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

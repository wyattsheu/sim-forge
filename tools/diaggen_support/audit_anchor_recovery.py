#!/usr/bin/env python3
"""Read-only CPU audit of anchor resets and native snapshot eligibility.

This does not initialize a run, attach to diagnostics, or change a terminal.
Run with the DiagGen mesh interpreter so native mesh/appearance imports work.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyze_anchor_history(state: dict) -> dict:
    diagnostics = state.get("diagnostics", {})
    compiled = diagnostics.get("compiled_anchor_targets", [])
    by_id = {item["compile_id"]: item for item in compiled}
    reset_ids = set()
    resets = []
    for index, current in enumerate(compiled):
        if current.get("edit") is not None:
            continue
        previous = next((item for item in reversed(compiled[:index])
                         if item.get("anchor_id") == current.get("anchor_id")), None)
        if previous is None or previous.get("edit") is None:
            continue
        if current.get("mesh_frame_box_m") != previous.get("base_box_m"):
            continue
        reset_ids.add(current["compile_id"])
        resets.append({
            "anchor_id": current["anchor_id"],
            "discarded_edited_compile_id": previous["compile_id"],
            "reset_compile_id": current["compile_id"],
            "reset_to_original_base": True,
        })
    trials = []
    for trial in diagnostics.get("setup_trials", []):
        compile_id = trial.get("anchor_compile_id")
        if compile_id not in by_id:
            raise ValueError(f"setup trial refers to missing compile: {compile_id}")
        trials.append({
            "trial_id": trial["trial_id"],
            "compile_id": compile_id,
            "consumed_reset_compile": compile_id in reset_ids,
            "anchor_semantic_match": trial.get("reflection", {}).get("anchor_semantic_match"),
            "final_status": trial.get("final_status"),
        })
    terminal = diagnostics.get("terminal", {})
    return {
        "run_id": state.get("run_id"),
        "business_outcome": terminal.get("business_outcome", {}).get("status"),
        "reset_count": len(resets),
        "resets": resets,
        "setup_trials": trials,
    }


def audit_snapshot(native_repo: Path, snapshot: Path) -> dict:
    # These are the exact read-only preflights used before the supported public
    # initializer reserves a new run root. No seed function is called here.
    from hag4r.agentic.runtime_state import _load_validated_diagnostics_revision_snapshot
    from hag4r.tools.post_mesh_texture import load_appearance_rebake_evidence
    state_path = snapshot / "state.json"
    before = sha256(state_path)
    root, state, preflight = _load_validated_diagnostics_revision_snapshot(
        diagnostics_revision_snapshot_dir=snapshot,
        repo_root=native_repo,
        allow_post_mesh_repair_snapshot=False,
    )
    appearance = state.get("paths", {}).get("omnipart_appearance_manifest_path")
    if not appearance:
        raise FileNotFoundError("missing paths.omnipart_appearance_manifest_path")
    load_appearance_rebake_evidence(Path(appearance))
    after = sha256(state_path)
    if before != after:
        raise RuntimeError("read-only snapshot audit unexpectedly changed source state")
    return {
        "status": "pass",
        "snapshot_root": str(root),
        "source_state_sha256": before,
        "source_state_unchanged": True,
        "pre_diagnostic_stages_complete": True,
        "canonical_tet_inputs_present": True,
        "appearance_rebake_evidence_valid": True,
        "path_preflight_schema": preflight.get("schema_version"),
        "supported_initializer": "python -m hag4r.agentic.run_diaggen_pipeline",
        "required_flags": ["--diagnostics_revision_snapshot_dir", "--diagnostics-reroute-and-export",
                           "--require-new-run-root", "--run_id"],
        "limitation": "Eligibility only; no new diagnostics or final export executed.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-repo", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    native_repo = args.native_repo.resolve()
    sys.path.insert(0, str(native_repo))
    report = {"schema_version": "diaggen-anchor-recovery-audit-v1", "runs": []}
    success = True
    for snapshot in args.snapshot:
        snapshot = snapshot.resolve()
        try:
            state = json.loads((snapshot / "state.json").read_text())
            top_path = snapshot.parent.parent / "state.json"
            top_sha_before = sha256(top_path)
            item = analyze_anchor_history(state)
            item["snapshot_eligibility"] = audit_snapshot(native_repo, snapshot)
            item["original_run_state_unchanged"] = top_sha_before == sha256(top_path)
            if not item["original_run_state_unchanged"]:
                raise RuntimeError("source top-level state changed during audit")
        except Exception as exc:
            success = False
            item = {"snapshot": str(snapshot), "status": "fail", "error": str(exc)}
        report["runs"].append(item)
    report["status"] = "pass" if success else "fail"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())

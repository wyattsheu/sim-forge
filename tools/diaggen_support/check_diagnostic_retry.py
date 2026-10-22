"""Read-only native admission checks; never attach or persist diagnostic state."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys


def validate_retry_state(state, *, diaggen_root):
    sys.path.insert(0, str(Path(diaggen_root).resolve()))
    from hag4r.agentic.diagnostic_mcp_server import DiagnosticMcpRuntime
    from hag4r.agentic.runtime_tools.diagnostics import (
        archive_and_reset_diagnostic_execution_attempt, require_v2_session_state,
    )
    candidate = copy.deepcopy(state)
    attachments = candidate.get("diagnostic_runtime_attachments", [])
    if not isinstance(attachments, list) or not attachments or not isinstance(attachments[-1], dict):
        raise ValueError("Diagnostic successor needs its durable terminal owner")
    recovery = DiagnosticMcpRuntime._terminal_transport_recovery_metadata(
        candidate, str(attachments[-1].get("attachment_id", "")),
    )
    if recovery is None:
        raise ValueError("Diagnostic successor has no typed server-owned transport recovery provenance")
    archive_and_reset_diagnostic_execution_attempt(candidate, recovery=recovery)
    if require_v2_session_state(candidate, allow_fresh_unplanned=True) is not None:
        raise ValueError("Diagnostic successor unexpectedly retained an active plan")
    return {"valid": True, "kind": "diagnostic_successor", "fresh_unplanned": True,
            "recovery_cause": recovery["cause"],
            "archived_grounding_measurement_count": len(state.get("diagnostics", {}).get("part_grounding_context_measurements", []))}


def validate_snapshot(snapshot_dir, *, diaggen_root):
    root = Path(diaggen_root).resolve()
    snapshot = Path(snapshot_dir).resolve()
    sys.path.insert(0, str(root))
    from hag4r.agentic.runtime_state import _preflight_diagnostics_snapshot_before_run_root_reservation
    _preflight_diagnostics_snapshot_before_run_root_reservation(
        diagnostics_revision_snapshot_dir=snapshot, repo_root=root,
        diagnostics_stage_only=False,
    )
    return {"valid": True, "kind": "diagnostics_snapshot", "snapshot_dir": str(snapshot),
            "snapshot_state_sha256": hashlib.sha256((snapshot / "state.json").read_bytes()).hexdigest(),
            "appearance_preflight": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diaggen-root", type=Path, required=True)
    selected = parser.add_mutually_exclusive_group(required=True)
    selected.add_argument("--state-json", type=Path)
    selected.add_argument("--snapshot-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.state_json:
            report = validate_retry_state(json.loads(args.state_json.read_text()), diaggen_root=args.diaggen_root)
        else:
            report = validate_snapshot(args.snapshot_dir, diaggen_root=args.diaggen_root)
        print(json.dumps(report, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"valid": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Reproduce a retry's material-snapshot collision in a temporary workspace.

No MCP calls, GPU work, native source edits, or production state writes. The
optional candidate evaluation is only a registration-boundary experiment, not
an episode/diagnostic acceptance test or a deployed runtime patch.
"""
import argparse
import copy
import hashlib
import inspect
import json
from pathlib import Path
import shutil
import sys
import tempfile

WORKSPACE = Path(__file__).resolve().parents[3]
NATIVE = WORKSPACE / "tools/diaggen"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reproduce(state_path):
    sys.path.insert(0, str(NATIVE))
    from hag4r.agentic.runtime_tools import diagnostics as native
    state_path = state_path.resolve()
    state_hash = digest(state_path)
    state = json.loads(state_path.read_text())
    original_workspace = Path(state["paths"]["diagnostic_workspace_dir"])
    revision = state["active_revision"]
    diagnostics = state["diagnostics"]
    if not native._validate_diagnostic_attempt_archives(
        diagnostics.get("diagnostic_attempt_archives", []), diagnostics.get("active_diagnostic_attempt_id")
    ) or not diagnostics.get("active_diagnostic_attempt_id"):
        raise ValueError("Expected an authenticated recovery's archived successor state")
    if diagnostics.get("source_semantic_material_artifact_registrations"):
        raise ValueError("Expected missing registration in the successor")
    existing = original_workspace / "material_audit_authoritative" / revision
    collision = existing / ("cleaned_source_image" + Path(state["paths"]["cleaned_image_path"]).suffix)
    if not collision.is_file():
        raise ValueError("Expected the exact cleaned-image collision")
    originals = {path: digest(path) for path in existing.iterdir() if path.is_file()}
    grounding = original_workspace / "part_grounding_context.json"
    originals[grounding] = digest(grounding)
    source = inspect.getsource(native.initialize_source_semantic_material_artifact_registration)
    old = 'workspace_artifact_dir = runtime_paths["workspace_dir"] / "material_audit_authoritative" / revision_id'
    new = old + '\n            attempt_id = diagnostics.get("active_diagnostic_attempt_id")\n            if attempt_id is not None:\n                if not _validate_diagnostic_attempt_archives(diagnostics.get("diagnostic_attempt_archives", []), attempt_id):\n                    raise GenesisVlmSchemaError("invalid diagnostic attempt namespace")\n                workspace_artifact_dir = workspace_artifact_dir / attempt_id'
    if source.count(old) != 1:
        raise ValueError("Native source no longer matches this isolated experiment")
    namespace = dict(native.__dict__)
    exec(compile(source.replace(old, new), "<isolated-material-registration-candidate>", "exec"), namespace)
    candidate = namespace["initialize_source_semantic_material_artifact_registration"]
    with tempfile.TemporaryDirectory(prefix="diaggen-audit-collision-") as temporary:
        temporary_workspace = Path(temporary) / "sim_diagnostics"
        target = temporary_workspace / "material_audit_authoritative" / revision
        shutil.copytree(existing, target)
        shutil.copy2(grounding, temporary_workspace / grounding.name)
        isolated = copy.deepcopy(state)
        isolated["paths"]["diagnostic_workspace_dir"] = str(temporary_workspace)
        paths = {"workspace_dir": temporary_workspace,
                 "part_grounding_context": temporary_workspace / grounding.name}
        error = None
        try:
            native.initialize_source_semantic_material_artifact_registration(copy.deepcopy(isolated), runtime_paths=paths)
        except native.GenesisVlmSchemaError as exc:
            if str(exc) != "material audit registration snapshot path already exists: cleaned_source_image":
                raise
            error = str(exc)
        if error is None:
            raise AssertionError("Baseline no longer reproduces the diagnosed collision")
        trial = copy.deepcopy(isolated)
        registration = candidate(trial, runtime_paths=paths)
        if not registration["complete"] or len(registration["artifacts"]) != 5:
            raise AssertionError("Candidate did not register all five authoritative artifacts")
        for artifact in registration["artifacts"]:
            if digest(temporary_workspace / artifact["workspace_path"]) != artifact["source_sha256"]:
                raise AssertionError("Candidate snapshot differs from source")
        if candidate(trial, runtime_paths=paths) != registration:
            raise AssertionError("Repeated registration changed its immutable record")
        for original, before_hash in originals.items():
            relative = original.relative_to(original_workspace)
            if digest(temporary_workspace / relative) != before_hash:
                raise AssertionError("Candidate overwrote prior evidence")
    if digest(state_path) != state_hash or any(digest(path) != before for path, before in originals.items()):
        raise AssertionError("Production evidence changed while observed; rerun from stable copies")
    return {"run_id": state["run_id"], "state_sha256": state_hash,
            "baseline_error": error, "candidate_registration_artifact_count": 5,
            "candidate_source_hashes_match": True, "previous_evidence_preserved": True,
            "production_sources_and_state_modified": False, "candidate_deployed": False,
            "scope": "temporary registration boundary only; full define_episode, simulation and acceptance untested"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-json", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(reproduce(args.state_json), indent=2))

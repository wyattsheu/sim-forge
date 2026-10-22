#!/usr/bin/env python3
"""Verify an existing strict-accepted DiagGen export; optionally settle its ledger.

This is a deterministic parent bookkeeping tool. It never runs generation,
simulations, diagnostic lifecycle calls, or a Python pipeline orchestrator.
Use the native hag4r_mesh Python, which supplies the native mesh validators.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


SCHEMA = "diaggen-completed-export-validation-v1"
STAGES = (
    "image_cleanup", "sam3_omnipart_2d_segmentation", "omnipart_generate_parts",
    "hag4r_gpt_staged_material_inference", "hag4r_assign_params_to_prims",
    "hag4r_combined_to_monolithic", "genesis_live_diagnostic_loop",
    "hag4r_post_mesh_texture", "hag4r_final_export_bundle",
)
PHYSICAL = {
    "final_mesh.mesh": "monolithic_mesh_path",
    "heterogeneous_params.npz": "monolithic_params_path",
    "inferred_params.json": "inferred_params_path",
    "volume_topology.json": "volume_topology_path",
    "metric_mesh_scaling.json": "metric_mesh_scaling_path",
}


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"Expected JSON object: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def regular_path(value: Any, *, within: Path) -> Path:
    require(isinstance(value, str) and bool(value.strip()), "Required artifact path is missing")
    path = Path(value)
    require(path.is_absolute(), f"Artifact path must be absolute: {path}")
    require(path.is_relative_to(within), f"Artifact path escapes its declared root: {path}")
    require(".." not in path.parts, f"Artifact path traverses its root: {path}")
    relative = path.relative_to(within)
    current = within
    for part in relative.parts:
        current = current / part
        require(not current.is_symlink(), f"Artifact path contains a symlink: {current}")
    require(path.is_file(), f"Required artifact is not a regular file: {path}")
    return path


def check_record(record: Any, expected: Path, *, within: Path) -> str:
    require(isinstance(record, dict), f"Missing artifact record: {expected}")
    path = regular_path(record.get("path"), within=within)
    require(path == expected, f"Artifact record path mismatch: {expected}")
    require(type(record.get("size_bytes")) is int and record["size_bytes"] == path.stat().st_size,
            f"Artifact size mismatch: {path}")
    digest = sha256(path)
    require(record.get("sha256") == digest, f"Artifact SHA256 mismatch: {path}")
    return digest


def _native_checks(root: Path, export: Path) -> dict[str, Any]:
    """Read-only native physical, exact appearance/binding, and tet checks."""
    sys.path.insert(0, str(root))
    import numpy as np
    from hag4r.tools.final_export import (
        build_final_export_request, _validate_canonical_final_export_contract,
    )
    from hag4r.tools.metric_mesh_scaling import read_medit_tet_mesh
    from hag4r.tools.post_mesh_texture import validate_post_mesh_texture_bundle
    from hag4r.tools.volumetric_meshing import validate_tet_mesh

    request = build_final_export_request(
        run_id=export.name, mesh_path=export / "final_mesh.mesh",
        heterogeneous_params_path=export / "heterogeneous_params.npz",
        inferred_params_path=export / "inferred_params.json",
        volume_topology_path=export / "volume_topology.json",
        metric_mesh_scaling_path=export / "metric_mesh_scaling.json",
        appearance_bundle_dir=export / "appearance", output_dir=export,
    )
    physical = _validate_canonical_final_export_contract(request)
    visual = validate_post_mesh_texture_bundle(export / "appearance", validate_glb=True, repo_root=root)
    mesh = read_medit_tet_mesh(export / "final_mesh.mesh")
    with np.load(export / "heterogeneous_params.npz", allow_pickle=False) as arrays:
        labels = np.asarray(arrays["tet_part_labels"])
        expected = np.asarray(arrays["part_indices"])
        require(expected.ndim == 1 and len(expected) > 0, "Expected material part indices are missing")
        require(np.issubdtype(expected.dtype, np.integer), "Material part indices must be integers")
        require(np.issubdtype(labels.dtype, np.integer), "Tet material labels must be integers")
        require(len(set(expected.tolist())) == len(expected) and bool(np.all(expected >= 0)),
                "Material part indices must be unique and nonnegative")
        count = len(mesh.tets)
        moduli = np.asarray(arrays["tet_E_nu"])
        density = np.asarray(arrays["tet_density"])
        require(moduli.shape == (count, 2) and density.shape == (count,),
                "Tet material parameter dimensions do not match mesh")
        require(bool(np.all(np.isfinite(moduli))) and bool(np.all(np.isfinite(density))),
                "Tet material parameters are nonfinite")
        require(bool(np.all(moduli[:, 0] > 0)) and bool(np.all(density > 0)),
                "Tet stiffness and density must be positive")
        require(bool(np.all((moduli[:, 1] > -1) & (moduli[:, 1] < 0.5))),
                "Tet Poisson ratios are outside the physical interval")
        tet = validate_tet_mesh(points=mesh.vertices, tets=mesh.tets, tet_part_labels=labels,
                                expected_part_indices=expected.tolist(), material_coverage="exact")
    require(tet.get("valid") is True and tet.get("material_label_coverage_valid") is True,
            "Native tet validation did not establish full material coverage")
    return {
        "physical_contract": physical,
        "appearance_schema": visual["schema_version"],
        "tet_count": tet["tet_count"], "point_count": tet["point_count"],
        "material_labels": tet["present_material_labels"],
        "face_connected_components": tet["face_connected_component_count"],
        "native_tet_valid": True, "native_appearance_valid": True,
    }


def validate_completed_export(run_root: Path, *, diaggen_root: Path | None = None) -> dict[str, Any]:
    root = (diaggen_root or Path(__file__).resolve().parents[1] / "diaggen").resolve()
    run = Path(run_root).expanduser().resolve()
    require(run.parent == root / "outputs/agentic_asset_refinement", "Run must use the native run-root layout")
    state_path = regular_path(str(run / "state.json"), within=root)
    state_digest = sha256(state_path)
    state = read_object(state_path)
    require(state.get("schema_version") == "2026-07-skill-suite-runtime-state-v2", "Unsupported native state schema")
    require(state.get("run_root") == str(run), "State run_root mismatch")
    export_mode = state.get("run_mode") == "full_image" or (
        state.get("run_mode") == "post_mesh_processing_diagnostics"
        and state.get("diagnostics_reroute_and_export") is True
        and state.get("diagnostics_stage_only") is False
    )
    require(state.get("runtime_kind") == "codex_skill" and export_mode,
            "Only native full-image or reroute-and-export snapshot skill runs can be settled")
    require(state.get("status") in {"running", "success"}, "Run status is not eligible for successful completion")
    require(state.get("planned_global_stage_sequence") == list(STAGES), "Planned stage sequence mismatch")
    require(state.get("completed_global_stage_sequence") == list(STAGES), "Completed stage sequence is incomplete or unordered")
    for name in STAGES:
        stage = state.get("stages", {}).get(name, {})
        require(stage.get("ok") is True and stage.get("status") in {"success", "reused"} and not stage.get("error"),
                f"Required native stage is not successful: {name}")
    terminal = state.get("stage_runtime", {}).get("final_export", {}).get("terminal", {})
    require(terminal.get("tool_name") == "submit_final_export_stage" and
            terminal.get("status") in {"pending_validation", "success"} and not terminal.get("error"),
            "Final export has no successful native submission")
    revision = state.get("active_revision")
    require(isinstance(revision, str) and bool(revision), "Active revision is missing")
    require(state.get("accepted_revision") == revision and state.get("exported_revision") == revision,
            "Active, accepted, and exported revisions differ")
    metadata = state.get("revisions", {}).get(revision, {})
    require(metadata.get("status") == "accepted", "Active revision is not accepted")
    revision_root = run / "revisions" / revision
    require(metadata.get("revision_root") == str(revision_root), "Revision root mismatch")

    diagnostics = state.get("diagnostics", {})
    require(diagnostics.get("enabled") is True, "Genesis diagnostics were not enabled")
    diagnostic = diagnostics.get("terminal", {})
    require(diagnostic.get("status") == "success" and diagnostic.get("validated") is True,
            "Genesis terminal is not validated success")
    recommendation = diagnostic.get("recommendation", {})
    require(recommendation.get("recommendation") == "accept" and recommendation.get("ready") is True
            and recommendation.get("route") == "accept" and bool(str(recommendation.get("reason", "")).strip()),
            "Genesis recommendation is not strict accept")
    business = diagnostic.get("business_outcome", {})
    require(business.get("status") == "recommendation_valid" and business.get("recommendation") == recommendation,
            "Genesis durable business recommendation mismatch")
    operational = diagnostic.get("operational_outcome", {})
    require(operational.get("status") == "complete" and operational.get("cleanup_status") == "complete"
            and operational.get("retryable") is False and not operational.get("error")
            and not operational.get("failure_kind"), "Genesis operational completion is incomplete")
    for component in ("media", "reports"):
        require(operational.get("artifact_status", {}).get(component, {}).get("status") == "complete",
                f"Genesis {component} completion is incomplete")
    decision = state.get("route_state", {}).get("orchestrator_diagnostic_decision", {})
    require(decision.get("status") == "success" and decision.get("diagnostic_verdict") == "accept"
            and decision.get("child_recommendation") == "accept" and decision.get("source_revision") == revision
            and decision.get("transition_action") == "post_mesh_texture"
            and bool(str(decision.get("diagnostic_verdict_reason", "")).strip())
            and not decision.get("failure_kind") and not decision.get("halt_reason"),
            "Parent diagnostic accept decision mismatch")

    paths = state.get("paths", {})
    tag = state.get("output_tag")
    require(tag == run.name, "Output tag differs from run id")
    export = root / "outputs/run_pipeline" / tag
    manifest_path = export / "final_export_manifest.json"
    require(paths.get("final_export_dir") == str(export)
            and paths.get("final_export_manifest_path") == str(manifest_path)
            and state.get("final_export", {}).get("dir") == str(export), "Declared export layout mismatch")
    regular_path(str(manifest_path), within=root)
    manifest = read_object(manifest_path)
    manifest_digest = sha256(manifest_path)
    require(manifest.get("run_id") == tag and manifest.get("accepted_revision") == revision
            and manifest.get("export_revision") == revision, "Manifest revision or run id mismatch")
    inventory = {path.relative_to(export).as_posix() for path in export.rglob("*") if path.is_file()}
    require(not any(path.is_symlink() for path in export.rglob("*")), "Export contains symlinks")
    declared = manifest.get("canonical_files")
    require(isinstance(declared, list) and all(isinstance(name, str) for name in declared)
            and len(declared) == len(set(declared)) and set(declared) == inventory,
            "Manifest inventory does not match actual export files")
    require({path.name for path in export.iterdir()} == set(PHYSICAL) | {"final_export_manifest.json", "appearance"},
            "Export root contains noncanonical entries")
    exported_records = manifest.get("exported_artifacts", {})
    require(isinstance(exported_records, dict) and set(exported_records) == inventory - {"final_export_manifest.json"},
            "Exported artifact records do not match inventory")
    artifact_hashes = {}
    for name, record in exported_records.items():
        artifact_hashes[name] = check_record(record, export / name, within=export)
    sources = manifest.get("source_artifacts", {})
    for name, key in PHYSICAL.items():
        source = regular_path(paths.get(key), within=revision_root)
        require(check_record(sources.get(name), source, within=revision_root) == artifact_hashes[name],
                f"Export differs from source artifact: {name}")
    require(manifest.get("asset_refinement_source_dir") == str(revision_root)
            and manifest.get("source_directories", {}).get("asset_refinement") == str(revision_root)
            and manifest.get("source_directories", {}).get("sim_diagnostics") == str(revision_root / "sim_diagnostics"),
            "Manifest source-directory provenance mismatch")
    ownership = regular_path(sources.get("diagnostic_runtime_ownership"), within=revision_root / "sim_diagnostics")
    require(ownership.name == "runtime_ownership.json", "Diagnostic ownership provenance mismatch")
    auxiliary = manifest.get("auxiliary_source_artifacts", {})
    params_dir = regular_path(paths.get("monolithic_params_path"), within=revision_root).parent
    expected_auxiliary = {
        "cleaned_image.png": paths.get("cleaned_image_path"),
        "image_cleanup.json": paths.get("cleanup_report_path"),
        "heterogeneous_youngs_modulus.png": str(params_dir / f"{tag}_target_E.png"),
        "heterogeneous_density.png": str(params_dir / f"{tag}_target_density.png"),
        "heterogeneous_part_ids.png": str(params_dir / f"{tag}_target_part.png"),
        "source_part_ids.png": str(params_dir / f"{tag}_source_part.png"),
    }
    require(isinstance(auxiliary, dict) and set(auxiliary) == set(expected_auxiliary),
            "Required cleanup and material-render provenance records are incomplete")
    for name, record in auxiliary.items():
        require(isinstance(record, dict), "Malformed auxiliary provenance")
        source = regular_path(expected_auxiliary[name], within=revision_root)
        check_record(record, source, within=revision_root)
    source_visual = Path(str(paths.get("post_mesh_texture_dir", "")))
    require(source_visual.is_relative_to(revision_root), "Source appearance escapes active revision")
    for name in inventory:
        if name.startswith("appearance/"):
            source = regular_path(str(source_visual / name.removeprefix("appearance/")), within=revision_root)
            require(sha256(source) == artifact_hashes[name], f"Appearance differs from active revision: {name}")
    native = _native_checks(root, export)
    require(sha256(state_path) == state_digest, "Runtime state changed during validation; retry after the worker exits")
    require(sha256(manifest_path) == manifest_digest, "Export manifest changed during validation")
    return {
        "schema_version": SCHEMA, "valid": True, "run_id": tag, "run_root": str(run),
        "diaggen_root": str(root), "export_dir": str(export), "accepted_revision": revision,
        "state_sha256": state_digest, "manifest_sha256": manifest_digest,
        "artifact_count": len(inventory), "artifact_sha256": artifact_hashes,
        "all_native_stages_successful": True, "strict_genesis_accept": True,
        "native_validation": native,
    }


def settle_completed_export(run_root: Path, *, diaggen_root: Path | None = None) -> dict[str, Any]:
    report = validate_completed_export(run_root, diaggen_root=diaggen_root)
    root, run = Path(report["diaggen_root"]), Path(report["run_root"])
    sys.path.insert(0, str(root))
    from hag4r.agentic.runtime_state import append_history, load_state, update_state
    current = load_state(run)
    if current.get("status") == "success":
        return {**report, "settled": False, "already_successful": True}
    require(sha256(run / "state.json") == report["state_sha256"], "State changed before settlement")
    audit = {**report, "validated_at": datetime.now(timezone.utc).isoformat(),
             "authority": "parent_deterministic_export_validation"}
    update_state(run, status="success", completion_validation=audit)
    append_history(run, "parent_final_validation", "Verified existing accepted export without regeneration.",
                   event="pipeline_completion_validated", detail=audit)
    return {**report, "settled": True, "already_successful": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--settle", action="store_true", help="Record parent completion after successful verification")
    args = parser.parse_args()
    try:
        operation = settle_completed_export if args.settle else validate_completed_export
        print(json.dumps(operation(args.run_root), indent=2, sort_keys=True))
    except Exception as error:
        print(json.dumps({"schema_version": SCHEMA, "valid": False,
                          "error": f"{type(error).__name__}: {error}"}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

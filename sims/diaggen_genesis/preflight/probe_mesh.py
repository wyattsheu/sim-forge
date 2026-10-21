#!/usr/bin/env python3
"""CPU infrastructure fixtures for DiagGen's native deterministic mesh tools.

This does not orchestrate generation, make LLM calls, or write pipeline ledgers.
All inputs are explicitly synthetic boxes, never a substitute for a real asset.
Use hag4r_mesh's Python. An optional private DISPLAY enables software-only views.
"""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import traceback
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[3]
NATIVE = WORKSPACE / "tools" / "diaggen"
sys.path.insert(0, str(NATIVE))


@contextlib.contextmanager
def native_log(path: Path):
    """Capture native C++ output too, keeping stdout a single JSON document."""
    sys.stdout.flush()
    sys.stderr.flush()
    saved = os.dup(1), os.dup(2)
    try:
        with path.open("a", encoding="utf-8") as handle:
            os.dup2(handle.fileno(), 1)
            os.dup2(handle.fileno(), 2)
            yield
            sys.stdout.flush()
            sys.stderr.flush()
    finally:
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        os.close(saved[0])
        os.close(saved[1])


class Probe:
    def __init__(self, output: Path):
        self.output = output
        self.checks: list[dict[str, Any]] = []
        self.ctx: dict[str, Any] = {}

    def check(self, name, function, requires=()):
        started = time.monotonic()
        missing = [key for key in requires if key not in self.ctx]
        if missing:
            self.checks.append({"name": name, "status": "skip", "detail": "Prerequisite failed: " + ", ".join(missing), "elapsed_seconds": 0.0})
            return
        try:
            details = function() or {}
            self.checks.append({"name": name, "status": "pass", "detail": details, "elapsed_seconds": round(time.monotonic() - started, 3)})
        except Exception as error:
            traceback.print_exc()
            self.checks.append({"name": name, "status": "fail", "detail": f"{type(error).__name__}: {error}", "elapsed_seconds": round(time.monotonic() - started, 3)})

    def dependencies(self):
        dependencies = {"numpy": "numpy", "scipy": "scipy", "trimesh": "trimesh", "libigl": "igl", "pyvista": "pyvista", "vtk": "vtk", "pymeshlab": "pymeshlab", "pytetwild": "pytetwild", "manifold3d": "manifold3d", "meshio": "meshio"}
        versions, errors = {}, []
        for distribution, module in dependencies.items():
            try:
                importlib.import_module(module)
                versions[distribution] = importlib.metadata.version(distribution)
            except Exception as error:
                errors.append(f"{distribution}: {type(error).__name__}: {error}")
        self.ctx["versions"] = versions
        if errors:
            raise RuntimeError("; ".join(errors))
        import numpy as np
        import trimesh
        from hag4r.tools import volumetric_meshing as vm
        self.ctx.update(np=np, trimesh=trimesh, vm=vm)
        return versions

    def fixture_materials(self):
        np, vm, trimesh = (self.ctx[x] for x in ("np", "vm", "trimesh"))
        source = self.output / "fixture_source"
        source.mkdir()
        colors = np.asarray([[230, 45, 45], [45, 80, 230]], dtype=np.float64)
        predictions = []
        for index in range(2):
            box = trimesh.creation.box(extents=(1.0, 0.7, 0.6))
            box.apply_translation((0.6 * index, 0, 0))
            box.export(source / f"part{index}.glb")
            predictions.append({"part_index": index, "part_color_rgb": colors[index].tolist(), "volume_fill_mode": "solid_fill", "density_kg_m3": 900.0 + 100 * index, "youngs_modulus_pa": 100_000.0 * (index + 1), "poisson_ratio": 0.3, "friction_coefficient": 0.4})
        labels = source / "part_labels.npz"
        np.savez(labels, part_colors=colors)
        materials = source / "inferred_params.json"
        vm._write_json(materials, {"fixture_only": True, "predictions": predictions})
        from scripts.assign_params_to_prims import load_part_properties
        arrays = load_part_properties(materials, colors)
        params = self.output / "fixture_partwise_params.npz"
        np.savez(params, part_indices=arrays[0], part_E_nu=arrays[1], part_density=arrays[2], part_colors=colors, part_volume_fill_mode_codes=arrays[3], part_volume_fill_mode_names=arrays[4])
        specs = vm.load_color_locked_material_predictions(materials, labels)
        fidelities = [{"part_index": item.part_index, "part_color_rgb": list(item.part_color_rgb), "mesh_fidelity": "low", "fidelity_rationale": "Synthetic dependency fixture: simple overlapping box."} for item in specs]
        plan = vm.build_mesh_processing_plan(part_fidelities=fidelities, indexed_parts=specs, target_max_dimension_m=0.2, estimate_rationale="Synthetic fixture with known maximum dimension of 0.2 m.")
        specs = vm.load_mesh_fidelity_plan(plan, specs)
        request = vm.PerPartVolumetricMeshingRequest(input_mesh_dir=source, part_labels_path=labels, inferred_params_path=materials, partwise_params_path=params, mesh_processing_plan=plan, output_mesh_path=self.output / "fixture_final.mesh", heterogeneous_params_path=self.output / "fixture_heterogeneous_params.npz", metric_mesh_scaling_path=self.output / "fixture_metric_mesh_scaling.json", volume_topology_path=self.output / "fixture_volume_topology.json", repo_root=NATIVE)
        bad_materials = source / "fixture_bad_color.json"
        bad = json.loads(materials.read_text())
        bad["predictions"][0]["part_color_rgb"] = [0, 0, 0]
        vm._write_json(bad_materials, bad)
        try:
            load_part_properties(bad_materials, colors)
        except ValueError as error:
            assert "mismatch" in str(error)
        else:
            raise AssertionError("Known incorrect material color was accepted")
        self.ctx.update(request=request, specs=specs, source=source)
        return {"parts": 2, "material_negative_control": "color mismatch rejected", "fixture_only": True}

    def scaling(self):
        np, vm = self.ctx["np"], self.ctx["vm"]
        paths, meshes, scaling = vm._load_scaled_part_meshes(self.ctx["request"])
        measured = float(np.ptp(np.concatenate([mesh.vertices for mesh in meshes]), axis=0).max())
        assert np.isclose(measured, 0.2, rtol=0, atol=1e-8), measured
        self.ctx.update(paths=paths, meshes=meshes, scaling=scaling)
        return {"measured_max_dimension_m": measured, "scale_factor": scaling["scale_factor"], "glb_files_read": len(paths)}

    def occupancies(self):
        vm = self.ctx["vm"]
        parts = [vm._build_part_occupancy(spec=spec, source_mesh_path=path, mesh=mesh) for spec, path, mesh in zip(self.ctx["specs"], self.ctx["paths"], self.ctx["meshes"], strict=True)]
        hollow_spec = dataclasses.replace(self.ctx["specs"][0], volume_fill_mode="hollow_wall")
        hollow = vm._build_part_occupancy(spec=hollow_spec, source_mesh_path=self.ctx["paths"][0], mesh=self.ctx["meshes"][0])
        assert len(hollow.occupied_centers) < len(parts[0].occupied_centers)
        self.ctx.update(parts=parts, hollow=hollow)
        return {"solid_occupied_voxels": [len(part.occupied_centers) for part in parts], "hollow_occupied_voxels": len(hollow.occupied_centers), "production_voxels_longest_axis": parts[0].fidelity_config.longest_axis_voxels}

    def extract_surfaces(self):
        vm = self.ctx["vm"]
        import hag4r.mesh as mesh_tools
        if mesh_tools.ml is None:
            raise RuntimeError("Native pymeshlab import failed; refusing an unnoticed fallback in preflight")
        surfaces = [vm._extract_surface_for_part(part) for part in self.ctx["parts"]]
        hollow = vm._extract_surface_for_part(self.ctx["hollow"])
        for surface in [*surfaces, hollow]:
            report = vm.surface_validation_report(surface)
            assert report["valid"], report
        self.ctx["surfaces"] = surfaces
        return {"backend": "pymeshlab", "solid_faces": [len(surface.faces) for surface in surfaces], "hollow_faces": len(hollow.faces), "all_watertight": True}

    def boolean(self):
        vm = self.ctx["vm"]
        combined, report = vm.combine_part_surfaces(self.ctx["surfaces"], strategy="manifold_union")
        assert report["output"]["valid"]
        combined.export(self.output / "fixture_union.glb")
        self.ctx.update(combined=combined, boolean_report=report)
        return {"strategy": report["strategy"], "output": report["output"]}

    def tetrahedralize(self):
        vm = self.ctx["vm"]
        result = vm._tetrahedralize_once(self.ctx["combined"])
        points, tets = vm._structural_tet_arrays(result)
        report = vm.validate_tet_mesh(points=points, tets=tets)
        self.ctx.update(points=points, tets=tets, tet_report=report)
        return {"route": result["route"], "point_count": len(points), "tet_count": len(tets), "face_connected_component_count": report["face_connected_component_count"]}

    def ownership(self):
        np, vm = self.ctx["np"], self.ctx["vm"]
        labels, counts = vm.assign_tet_part_labels(points=self.ctx["points"], tets=self.ctx["tets"], parts=self.ctx["parts"])
        vm.validate_tet_mesh(points=self.ctx["points"], tets=self.ctx["tets"], tet_part_labels=labels, expected_part_indices=[0, 1])
        params = self.ctx["request"].heterogeneous_params_path
        arrays = vm._write_partwise_final_npz(params, self.ctx["specs"], labels)
        vm._validate_material_arrays(arrays, tet_count=len(labels))
        for part in self.ctx["parts"]:
            part.tet_count = int(np.count_nonzero(labels == part.spec.part_index))
        with np.load(params, allow_pickle=False) as reloaded:
            assert np.array_equal(reloaded["tet_part_labels"], labels)
            for index in range(2):
                mask = reloaded["tet_part_labels"] == index
                assert mask.any()
                assert np.all(reloaded["tet_density"][mask] == self.ctx["specs"][index].density_kg_m3)
                assert np.all(reloaded["tet_E_nu"][mask, 0] == self.ctx["specs"][index].youngs_modulus_pa)
        self.ctx.update(tet_labels=labels, arrays=arrays)
        return {"material_label_tet_counts": {str(i): int(np.count_nonzero(labels == i)) for i in range(2)}, **counts}

    def serialization(self):
        np, vm = self.ctx["np"], self.ctx["vm"]
        from hag4r.mesh import write_medit_mesh
        from hag4r.tools.metric_mesh_scaling import read_medit_tet_mesh, scale_medit_tet_mesh, tetra_volume_m3
        path = self.ctx["request"].output_mesh_path
        write_medit_mesh(path, self.ctx["points"], self.ctx["tets"])
        reloaded = read_medit_tet_mesh(path)
        assert np.array_equal(reloaded.vertices, self.ctx["points"])
        assert np.array_equal(reloaded.tets, self.ctx["tets"])
        vm.validate_tet_mesh(points=reloaded.vertices, tets=reloaded.tets, tet_part_labels=self.ctx["tet_labels"], expected_part_indices=[0, 1])
        scaled_path = self.output / "fixture_scaled_twice.mesh"
        scale_medit_tet_mesh(path, scaled_path, 2.0)
        scaled = read_medit_tet_mesh(scaled_path)
        ratio = float(tetra_volume_m3(scaled.vertices, scaled.tets).sum() / tetra_volume_m3(reloaded.vertices, reloaded.tets).sum())
        assert np.isclose(ratio, 8.0)
        write_medit_mesh(self.ctx["source"] / "mesh_combined.mesh", reloaded.vertices, reloaded.tets)
        np.savez(self.ctx["request"].part_labels_path, part_colors=np.asarray([spec.part_color_rgb for spec in self.ctx["specs"]]), tet_part_labels=self.ctx["tet_labels"])
        self.ctx["serialized"] = True
        return {"exact_coordinates_and_connectivity": True, "volume_ratio_after_2x_linear_scale": ratio}

    def negative_tets(self):
        np, vm = self.ctx["np"], self.ctx["vm"]
        bad = self.ctx["tets"].copy()
        bad[0, 1] = bad[0, 0]
        try:
            vm.validate_tet_mesh(points=self.ctx["points"], tets=bad)
        except vm.TetMeshValidationError:
            pass
        else:
            raise AssertionError("Repeated-vertex tetrahedron accepted")
        try:
            vm.validate_tet_mesh(points=self.ctx["points"], tets=self.ctx["tets"], tet_part_labels=np.zeros(len(self.ctx["tets"]), dtype=np.int64), expected_part_indices=[0, 1])
        except vm.TetMeshValidationError:
            pass
        else:
            raise AssertionError("Missing material label accepted")
        return "Repeated-vertex tetrahedra and incomplete material coverage both rejected"

    def canonical_contract(self):
        vm = self.ctx["vm"]
        from hag4r.tools.final_export import build_final_export_request, _validate_canonical_final_export_contract, write_final_export_bundle
        request = self.ctx["request"]
        topology = {"fixture_only": True, "schema_version": vm.VOLUME_TOPOLOGY_SCHEMA_VERSION, "volume_topology": vm.derive_volume_topology([part.spec.volume_fill_mode for part in self.ctx["parts"]]), "tet_count": len(self.ctx["tets"]), "parts": [vm._part_topology_payload(part=part, repo_root=NATIVE) for part in self.ctx["parts"]]}
        vm._write_json(request.volume_topology_path, topology)
        vm._write_json(request.metric_mesh_scaling_path, {"fixture_only": True, **self.ctx["scaling"]})
        export_request = build_final_export_request(run_id="preflight_synthetic_fixture", mesh_path=request.output_mesh_path, heterogeneous_params_path=request.heterogeneous_params_path, inferred_params_path=request.inferred_params_path, volume_topology_path=request.volume_topology_path, metric_mesh_scaling_path=request.metric_mesh_scaling_path, output_dir=self.output / "fixture_export", appearance_bundle_dir=self.output / "INTENTIONALLY_MISSING_APPEARANCE")
        report = _validate_canonical_final_export_contract(export_request)
        assert report["params"]["tet_count"] == len(self.ctx["tets"])
        try:
            write_final_export_bundle(export_request, repo_root=NATIVE)
        except NotADirectoryError:
            pass
        else:
            raise AssertionError("Final export accepted missing appearance bundle")
        assert not export_request.output_dir.exists(), "Negative export check wrote an incomplete bundle"
        return {"physical_contract": "valid", "missing_appearance_negative_control": "rejected before export writes", "full_bundle_export": "requires real validated appearance; not claimed by this mesh fixture"}

    def renders(self):
        if not os.environ.get("DISPLAY"):
            self.checks.append({"name": "native_four_material_pngs", "status": "skip", "detail": "No private DISPLAY supplied. Rerun with Xvfb DISPLAY and LIBGL_ALWAYS_SOFTWARE=1.", "elapsed_seconds": 0.0})
            return
        def render():
            if os.environ.get("LIBGL_ALWAYS_SOFTWARE") != "1":
                raise RuntimeError("CPU fixture requires LIBGL_ALWAYS_SOFTWARE=1 for rendering")
            vm = self.ctx["vm"]
            paths = vm._render_mesh_processing_pngs(request=self.ctx["request"], points=self.ctx["points"], tets=self.ctx["tets"], arrays=self.ctx["arrays"])
            from PIL import Image
            report = {}
            for name, path in paths.items():
                with Image.open(path) as image:
                    image.verify()
                report[name] = {"path": str(path), "size_bytes": path.stat().st_size}
            return report
        self.check("native_four_material_pngs", render, ("serialized", "arrays"))

    def run(self):
        self.check("mesh_runtime_dependencies", self.dependencies)
        self.check("color_locked_material_fixture_and_negative_control", self.fixture_materials, ("vm",))
        self.check("native_glb_load_and_metric_scaling", self.scaling, ("request",))
        self.check("native_solid_and_hollow_voxelization", self.occupancies, ("meshes",))
        self.check("native_marching_cubes_and_meshlab_simplification", self.extract_surfaces, ("parts",))
        self.check("native_manifold_boolean_union", self.boolean, ("surfaces",))
        self.check("native_pytetwild_and_hard_tet_validation", self.tetrahedralize, ("combined",))
        self.check("native_tet_owner_material_assignment_and_npz", self.ownership, ("tets", "parts"))
        self.check("native_medit_serialization_and_scale_volume", self.serialization, ("tet_labels",))
        self.check("native_invalid_tets_and_material_negative_controls", self.negative_tets, ("tets",))
        self.check("native_canonical_physical_export_contract", self.canonical_contract, ("serialized", "arrays"))
        self.renders()
        counts = {status: sum(check["status"] == status for check in self.checks) for status in ("pass", "fail", "skip")}
        return {"schema_version": "diaggen-preflight-mesh-v1", "scope": "CPU synthetic infrastructure fixtures; no production state or generation", "status": "fail" if counts["fail"] else ("partial" if counts["skip"] else "pass"), "overallstatus": "fail" if counts["fail"] else ("partial" if counts["skip"] else "pass"), "counts": counts, "checks": self.checks, "versions": self.ctx.get("versions", {}), "output_dir": str(self.output), "log": str(self.output / "native.log")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    output = args.output_dir.expanduser().resolve()
    if not output.is_relative_to((NATIVE / "outputs" / "preflight").resolve()):
        parser.error("--output-dir must be under tools/diaggen/outputs/preflight/")
    if output.exists() and any(output.iterdir()):
        parser.error("--output-dir must be new or empty; stale fixture artifacts are not reused")
    output.mkdir(parents=True, exist_ok=True)
    # TetWild also writes a fixed-name debug STL in cwd; isolate that side effect.
    os.chdir(output)
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    started = time.monotonic()
    with native_log(output / "native.log"):
        report = Probe(output).run()
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    (output / "report.json").write_text(text, encoding="utf-8")
    print(text, end="")
    return int(report["status"] == "fail")


if __name__ == "__main__":
    raise SystemExit(main())

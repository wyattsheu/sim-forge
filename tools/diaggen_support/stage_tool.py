#!/usr/bin/env python3
"""Call exactly one existing, non-diagnostic DiagGen stage tool.

Run this with tools/diaggen/.conda/hag4r/bin/python. These are local Python
tools, not stage MCP endpoints. The Codex stage child still supplies decisions,
validates the result, and explicitly submits or halts its stage. This command
does not select, repeat, submit, or advance stages. Genesis diagnostics must
continue through its authenticated MCP lifecycle.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import importlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys
import traceback
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[2]
DIAGGEN_ROOT = WORKSPACE / "tools" / "diaggen"
GUARD_PATH = WORKSPACE / "tools" / "wait_diaggen_gpu_memory.py"
STAGE_MODULE = "hag4r.agentic.runtime_tools.stage_tools"
TERMINAL_MODULE = "hag4r.agentic.runtime_tools.stage_terminal"

# Explicit review boundary: never discover additional callable exports or expose
# diagnostics, pipeline transitions, leases, sessions, finalizers, or state edits.
STAGE_TOOLS = (
    "register_image_cleanup_stage",
    "run_sam3_omnipart_2d_segmentation_stage",
    "run_omnipart_generate_parts_stage",
    "load_material_part_labels_stage",
    "build_material_indexed_parts_stage",
    "run_material_geometry_analysis_stage",
    "decide_material_fill_mode_stage",
    "run_material_semantics_inference_stage",
    "validate_repair_material_predictions_stage",
    "write_inferred_material_params_stage",
    "run_assign_params_to_prims_stage",
    "select_mesh_processing_fidelities_stage",
    "run_combined_to_monolithic_stage",
    "resolve_disconnected_tet_components_stage",
    "run_post_mesh_texture_stage",
    "run_final_export_bundle_stage",
)
TERMINAL_TOOLS = (
    "submit_image_cleanup_stage",
    "halt_image_cleanup_stage",
    "submit_segmentation_stage",
    "halt_segmentation_stage",
    "submit_omnipart_stage",
    "halt_omnipart_stage",
    "submit_material_inference_stage",
    "halt_material_inference_stage",
    "submit_mesh_processing_stage",
    "halt_mesh_processing_stage",
    "submit_post_mesh_texture_stage",
    "halt_post_mesh_texture_stage",
    "submit_final_export_stage",
    "halt_final_export_stage",
)
TOOL_MODULES = {
    **dict.fromkeys(STAGE_TOOLS, STAGE_MODULE),
    **dict.fromkeys(TERMINAL_TOOLS, TERMINAL_MODULE),
}
OMNIPART_TOOL = "run_omnipart_generate_parts_stage"


def import_native_module(name: str):
    """Import from this workspace's checkout; reject already-loaded substitutes."""
    native_path = str(DIAGGEN_ROOT)
    if not DIAGGEN_ROOT.is_dir():
        raise FileNotFoundError(f"Native DiagGen checkout is missing: {DIAGGEN_ROOT}")
    if native_path not in sys.path:
        sys.path.insert(0, native_path)
    module = importlib.import_module(name)
    expected = DIAGGEN_ROOT.joinpath(*name.split(".")).with_suffix(".py").resolve()
    actual = getattr(module, "__file__", None)
    if actual is None or Path(actual).resolve() != expected:
        raise ImportError(f"Native module must come from {expected}; got {actual!r}")
    return module


def resolve_tool(name: str):
    module_name = TOOL_MODULES.get(name)
    if module_name is None:
        raise ValueError(f"Tool is not allowlisted: {name!r}; use --list")
    module = import_native_module(module_name)
    function = getattr(module, name, None)
    if not callable(function):
        raise ImportError(f"Native tool is unavailable: {module_name}.{name}")
    return function


def list_tools() -> dict[str, Any]:
    """Actually import and inspect all allowed functions, without invoking any."""
    return {
        "status": "success",
        "tools": list(TOOL_MODULES),
        "signatures": {name: str(inspect.signature(resolve_tool(name)))
                       for name in TOOL_MODULES},
        "diagnostics": "Use the authenticated Genesis diagnostic MCP; excluded here.",
    }


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON number is not allowed: {value}")


def read_arguments(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"),
                         object_pairs_hook=_unique_object,
                         parse_constant=_reject_constant)
    if not isinstance(payload, dict):
        raise ValueError("--input-json must contain one JSON object of keyword arguments")
    return payload


def load_guard_module():
    """Load the one deterministic guard by its workspace-derived absolute path."""
    if not GUARD_PATH.is_file():
        raise FileNotFoundError(f"GPU memory guard is missing: {GUARD_PATH}")
    spec = importlib.util.spec_from_file_location("diaggen_stage_tool_gpu_guard", GUARD_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load GPU memory guard: {GUARD_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_omnipart_memory(arguments, minimum_free_mib=None, *, environment=None):
    """Wait on the exact persisted GPU before one requested OmniPart tool call."""
    environment = os.environ if environment is None else environment
    guard = load_guard_module()
    gpu_uuid = environment.get("CUDA_VISIBLE_DEVICES")
    guard.validate_gpu_uuid(gpu_uuid)
    if minimum_free_mib is None:
        configured = environment.get("DIAGGEN_JOB_MINIMUM_FREE_MIB")
        if not isinstance(configured, str) or not configured.isascii() or not configured.isdecimal():
            raise ValueError("OmniPart requires DIAGGEN_JOB_MINIMUM_FREE_MIB or --minimum-free-mib")
        minimum_free_mib = int(configured)
    guard.validate_minimum(minimum_free_mib)
    run_root = arguments.get("run_root")
    if not isinstance(run_root, str) or not run_root.strip():
        raise ValueError("OmniPart run_root must be a nonempty string")
    runtime = import_native_module("hag4r.agentic.runtime_state")
    state = runtime.load_state(str(Path(run_root).expanduser().resolve()))
    if not state:
        raise ValueError("OmniPart requires an existing initialized runtime state")
    bound_gpu = runtime.worker_cuda_visible_devices(state)
    guard.validate_gpu_uuid(bound_gpu)
    if bound_gpu != gpu_uuid:
        raise ValueError("CUDA_VISIBLE_DEVICES differs from the persisted worker GPU binding")

    # Keep stdout reserved for the requested native tool's JSON result. Guard
    # observations remain visible in stderr while it waits on shared memory.
    def emit(record):
        print(json.dumps(record, sort_keys=True, allow_nan=False), file=sys.stderr, flush=True)

    guard_rc = guard.wait_for_memory(gpu_uuid, minimum_free_mib, emit=emit)
    if type(guard_rc) is not int or guard_rc != 0:
        raise RuntimeError(f"GPU memory guard did not succeed (exit={guard_rc!r}); tool was not called")


def invoke_tool(name, arguments, minimum_free_mib=None, *, environment=None):
    """Validate a single native call; never submit, retry, or choose another tool."""
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a JSON object")
    function = resolve_tool(name)
    inspect.signature(function).bind(**arguments)
    if name == OMNIPART_TOOL:
        require_omnipart_memory(arguments, minimum_free_mib, environment=environment)
    elif minimum_free_mib is not None:
        raise ValueError("--minimum-free-mib is only valid for the OmniPart generation tool")
    return function(**arguments)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", nargs="?", help="One exact non-diagnostic tool name from --list")
    parser.add_argument("--list", action="store_true", help="Import and list the actual allowed tools; invoke none")
    parser.add_argument("--input-json", type=Path, help="JSON object containing the native function's keyword arguments")
    parser.add_argument("--minimum-free-mib", type=int,
                        help="OmniPart guard threshold; overrides DIAGGEN_JOB_MINIMUM_FREE_MIB; no default")
    args = parser.parse_args(argv)
    try:
        if args.list:
            if args.tool is not None or args.input_json is not None or args.minimum_free_mib is not None:
                raise ValueError("Use --list by itself")
            with redirect_stdout(sys.stderr):
                result = list_tools()
        else:
            if args.tool is None or args.input_json is None:
                raise ValueError("Provide TOOL --input-json PATH, or use --list")
            arguments = read_arguments(args.input_json)
            with redirect_stdout(sys.stderr):
                native_result = invoke_tool(args.tool, arguments, args.minimum_free_mib)
            result = {"tool": args.tool, "result": native_result}
        encoded = json.dumps(result, sort_keys=True, allow_nan=False)
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"tool": args.tool, "status": "error",
                          "error": {"type": type(error).__name__, "message": str(error)}},
                         sort_keys=True, allow_nan=False), flush=True)
        return 1
    print(encoded, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

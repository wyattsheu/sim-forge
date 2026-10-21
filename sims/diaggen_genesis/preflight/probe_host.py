#!/usr/bin/env python3
"""CPU-only host, input, SAM3 and orchestration dependency preflight."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "sims/diaggen_genesis"
NATIVE = ROOT / "tools/diaggen"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.expanduser().resolve()
    permitted = (NATIVE / "outputs/preflight").resolve()
    if not output.is_relative_to(permitted) or output == permitted or (output.exists() and any(output.iterdir())):
        parser.error("--output-dir must be a fresh child of tools/diaggen/outputs/preflight")
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": "diaggen-host-preflight-v1", "checks": [], "cpu_only": True,
              "limitations": ["No new LLM/image-generation/API requests; authentication evidence is historical.",
                              "CPU checkpoint inspection does not measure SAM3 GPU peak memory."]}
    environment = os.environ.copy()
    environment.update({"CUDA_VISIBLE_DEVICES": "", "PYTHONNOUSERSITE": "1", "PYTHONPATH": str(NATIVE),
                        "CUDA_HOME": "/usr/local/cuda-12.8", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    environment["PATH"] = ":".join(["/usr/local/cuda-12.8/bin", str(Path.home() / ".local/bin"),
                                     str(Path.home() / "miniforge3/bin"), environment.get("PATH", "")])

    def record(name, function, optional=False):
        try:
            detail = function()
            value = {"name": name, "status": "pass", "detail": detail}
        except Exception as error:
            value = {"name": name, "status": "skip" if optional else "fail", "detail": f"{type(error).__name__}: {error}"}
        report["checks"].append(value)
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"{value['status']}: {name}", file=sys.stderr, flush=True)

    def command(argv, timeout=120):
        completed = subprocess.run([str(value) for value in argv], cwd=NATIVE, env=environment,
                                   capture_output=True, text=True, timeout=timeout)
        if completed.returncode:
            raise RuntimeError(f"exit={completed.returncode}: {completed.stderr[-1800:]} {completed.stdout[-800:]}")
        return completed.stdout

    def inspect_inputs():
        from PIL import Image
        plan = json.loads((BASE / "batch_plan.json").read_text())
        jobs = plan["jobs"]
        gallery = BASE / "inputs/demo_gallery"
        actual = {path.resolve() for path in gallery.iterdir() if path.suffix.lower() in {".png", ".jpg", ".jpeg"}}
        expected = {(BASE / job["input"]).resolve() for job in jobs}
        if len(jobs) != 9 or len(expected) != 9 or actual != expected:
            raise ValueError("Nine distinct queued inputs must exactly match gallery image files")
        validated = []
        for job in jobs:
            path = (BASE / job["input"]).resolve()
            if not path.is_relative_to(gallery.resolve()):
                raise ValueError("Input path escapes gallery")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with Image.open(path) as image:
                dimensions = image.size
                image.verify()
            with Image.open(path) as image:
                image.load()
            if digest != job["input_sha256"] or dimensions != (job["width"], job["height"]):
                raise ValueError(f"Input differs from batch plan: {job['id']}")
            validated.append({"id": job["id"], "sha256": digest, "dimensions": dimensions})
        return validated

    record("nine_input_decode_hash_dimensions", inspect_inputs)

    def filesystem():
        free = shutil.disk_usage(NATIVE / "outputs").free
        if free < 10 * 1024**3:
            raise RuntimeError(f"Native outputs has less than the 10 GiB minimum preflight guard: {free} bytes free")
        path = output / "write_read_probe.bin"
        payload = os.urandom(4096)
        with path.open("wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != payload:
            raise ValueError("Output storage write/read mismatch")
        path.unlink()
        return {"free_bytes": free, "write_read_bytes": len(payload), "free_space_guard_gib": 10,
                "guard_basis": "Sanity guard only; not a measured full-batch disk requirement"}
    record("native_output_space_write_read", filesystem)
    environments = {name: NATIVE / ".conda" / name / "bin/python" for name in ("hag4r", "hag4r_mesh", "hag4r_segmentation", "omnipart")}
    environments["genesis"] = NATIVE / "third_party/genesis-world/.conda/genesis_world-main/bin/python"
    for name, python in environments.items():
        record("python_" + name, lambda python=python: {"path": str(python), "version": command([python, "--version"]).strip()})
    modules = ["yaml", "mcp.server.fastmcp", "hag4r.agentic.run_diaggen_pipeline", "hag4r.agentic.diagnostic_mcp_server"]
    modules += ["hag4r.tools." + path.stem for path in (NATIVE / "hag4r/tools").glob("*.py") if path.stem != "__init__"]
    imports = "import importlib,json; names=" + repr(modules) + "; result=[]\nfor name in names:\n m=importlib.import_module(name); result.append({'module':name,'file':getattr(m,'__file__',None)})\nprint(json.dumps(result))"
    record("hag4r_all_stage_runtime_imports", lambda: json.loads(command([environments["hag4r"], "-B", "-c", imports])))
    sam_imports = "import json,torch,PIL; from sam3.model_builder import build_sam3_image_model; from sam3.model.sam3_image_processor import Sam3Processor; print(json.dumps({'sam3_model_builder':True,'sam3_image_processor':True,'torch':torch.__version__,'pillow':PIL.__version__,'cuda_initialized':torch.cuda.is_initialized()})); assert not torch.cuda.is_initialized()"
    record("sam3_cpu_runtime_imports", lambda: json.loads(command([environments["hag4r_segmentation"], "-B", "-c", sam_imports])))
    checkpoint = Path.home() / ".cache/huggingface/hub/models--facebook--sam3/snapshots/3c879f39826c281e95690f02c7821c4de09afae7/sam3.pt"
    weight_code = "import json,sys,torch; p=sys.argv[1]; d=torch.load(p,map_location='cpu',weights_only=True,mmap=True); assert isinstance(d,dict) and d; w=d.get('model',d); assert isinstance(w,dict) and w; print(json.dumps({'mmap':True,'map_location':'cpu','top_keys':list(d)[:5],'entry_count':len(w),'sample_keys':list(w)[:5],'cuda_initialized':torch.cuda.is_initialized()})); assert not torch.cuda.is_initialized()"
    record("sam3_checkpoint_cpu_mmap", lambda: json.loads(command([environments["hag4r_segmentation"], "-B", "-c", weight_code, checkpoint], timeout=180)))
    record("sam3_exr_actual_roundtrip", lambda: json.loads(command([environments["hag4r_segmentation"], ROOT / "tools/check_diaggen_exr.py"])))
    commands = {"conda": ["--version"], "codex": ["--version"], "git": ["--version"], "tmux": ["-V"],
                "ffmpeg": ["-version"], "ffprobe": ["-version"], "nvcc": ["--version"], "c++": ["--version"]}
    for binary, flags in commands.items():
        def version(binary=binary, flags=flags):
            path = shutil.which(binary, path=environment["PATH"])
            if not path:
                raise FileNotFoundError(binary)
            return {"path": path, "version": command([path, *flags], timeout=30).strip().splitlines()[:5]}
        record("command_" + binary.replace("+", "p"), version)
    xvfb = NATIVE / ".local/xvfb/usr/bin/Xvfb"
    record("private_xvfb_executable", lambda: str(xvfb) if xvfb.is_file() and os.access(xvfb, os.X_OK)
           else (_ for _ in ()).throw(FileNotFoundError(xvfb)))
    record("optional_cmake", lambda: shutil.which("cmake", path=environment["PATH"])
           or (_ for _ in ()).throw(FileNotFoundError("cmake not needed by current installed runtime")), optional=True)

    def historical():
        queue = BASE / "queue"
        events = [json.loads(line) for line in (queue / "model_preflight_events.jsonl").read_text().splitlines()]
        if not any(item.get("type") == "turn.completed" for item in events):
            raise ValueError("No completed historical model preflight")
        settings = json.loads((queue / "settings.json").read_text())
        if settings.get("model") != "gpt-6-luna" or settings.get("model_reasoning_effort") != "max":
            raise ValueError("Current requested model differs from recorded orchestration configuration")
        cleanup = []
        for state_path in (NATIVE / "outputs/agentic_asset_refinement").glob("*/state.json"):
            state = json.loads(state_path.read_text())
            stage = state.get("stages", {}).get("image_cleanup", {})
            if stage.get("status") != "success":
                continue
            attempts = stage.get("outputs", {}).get("result", {}).get("metrics", {}).get("payload", {}).get("attempts", [])
            evidence = [attempt.get("imagegen_invocation_evidence", {}) for attempt in attempts]
            image_artifacts = [item["path"] for item in stage.get("artifacts", {}).get("expected", []) if item.get("role") == "cleaned_source_image"]
            if any(item.get("kind") == "codex_builtin_imagegen" for item in evidence) and any(Path(path).is_file() for path in image_artifacts):
                cleanup.append({"run_id": state["run_id"], "state_path": str(state_path), "finished_at": stage.get("finished_at"), "imagegen_calls": len(evidence)})
        if not cleanup:
            raise ValueError("No completed cleanup with built-in imagegen invocation evidence and actual image artifact")
        return {"evidence_kind": "historical", "model": settings["model"], "reasoning_effort": settings["model_reasoning_effort"],
                "successful_cleanup_runs": cleanup, "fresh_api_access_retested": False,
                "preflight_events": str(queue / "model_preflight_events.jsonl"),
                "subagent_and_imagegen_availability_record": str(queue / "model_preflight_result.txt")}
    record("historical_codex_model_imagegen_subagent_evidence", historical)
    report["overall_status"] = "fail" if any(item["status"] == "fail" for item in report["checks"]) else "pass"
    report["checked_at_unix"] = time.time()
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 1 if report["overall_status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Bind a fully passing preflight to its exact local inputs and runtime.

This CPU-only gate never imports simulation libraries or contacts a service.
It detects changes after testing; it does not replace the actual full probes.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


SCHEMA = "diaggen-runtime-preflight-certificate-v1"
BASE = Path("sims/diaggen_genesis")
NATIVE = Path("tools/diaggen")
ENVIRONMENTS = {
    **{name: NATIVE / ".conda" / name for name in
       ("hag4r", "hag4r_mesh", "hag4r_segmentation", "omnipart")},
    "genesis": NATIVE / "third_party/genesis-world/.conda/genesis_world-main",
}
REQUIRED_SOURCES = [
    BASE / "batch_plan.json", BASE / "queue/run_one.sh",
    BASE / "preflight/readiness.py",
    *[BASE / "preflight" / f"probe_{name}.py" for name in ("host", "mesh", "genesis", "omnipart")],
    BASE / "preflight/summarize.py", BASE / "queue/batch_control.py",
    *[BASE / "queue" / name for name in
      ("monitor.py", "run_monitor.sh", "install_monitor.sh")],
    *[BASE / "queue/systemd" / ("diaggen-genesis-monitor." + name + ".in")
      for name in ("service", "timer")],
    *[Path("tools") / name for name in
      ("check_diaggen_exr.py", "check_diaggen_display.py", "wait_diaggen_gpu_memory.py")],
    NATIVE / "scripts/generate_simulation_mp4.sh",
    NATIVE / "hag4r/tools/volumetric_meshing.py",
    NATIVE / ".agents/skills/run-diaggen-pipeline/SKILL.md",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_record(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"Required file is absent: {path}")
    return {"resolved_path": str(path.resolve()), "sha256": sha256(path)}


def executable_record(path: Path) -> dict:
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"Required executable is absent: {path}")
    stat = path.stat()
    return {"path": str(path), "resolved_path": str(path.resolve()),
            "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def environment_inventory(python: Path) -> dict:
    # Metadata only: torch, CUDA, OpenGL and simulation packages are not imported.
    code = ("import importlib.metadata as m,json,sys; "
            "print(json.dumps({'python_path':sys.path,'distributions':"
            "sorted((d.metadata['Name'].lower().replace('_','-'), d.version) "
            "for d in m.distributions())},sort_keys=True))")
    result = subprocess.run([str(python), "-I", "-c", code], check=True,
                            capture_output=True, text=True, timeout=15)
    inventory = json.loads(result.stdout)
    if not inventory.get("distributions") or not inventory.get("python_path"):
        raise ValueError(f"Empty package inventory: {python}")
    encoded = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
    return {"python": executable_record(python),
            "inventory_sha256": hashlib.sha256(encoded).hexdigest(),
            "distribution_count": len(inventory["distributions"]),
            "python_path": inventory["python_path"]}


def binary_inventory(workspace: Path) -> dict:
    binaries = {
        "xvfb": workspace / NATIVE / ".local/xvfb/usr/bin/Xvfb",
        "nvcc": Path("/usr/local/cuda-12.8/bin/nvcc"),
        "ninja": workspace / ENVIRONMENTS["omnipart"] / "bin/ninja",
    }
    for name, command in (("cxx", os.environ.get("CXX", "c++")),
                          ("ffmpeg", "ffmpeg"), ("ffprobe", "ffprobe")):
        resolved = shutil.which(command)
        if not resolved:
            raise ValueError(f"Required executable not on PATH: {command}")
        binaries[name] = Path(resolved)
    return {name: executable_record(path) for name, path in sorted(binaries.items())}


def native_tracked_sources(workspace: Path) -> list[Path]:
    result = subprocess.run(["git", "-C", str(workspace / NATIVE), "ls-files", "-z"],
                            check=True, capture_output=True, timeout=15)
    extensions = {".py", ".sh", ".yaml", ".yml", ".json", ".cu", ".cuh",
                  ".cpp", ".h", ".hpp", ".glsl", ".vert", ".frag"}
    paths = [NATIVE / path for path in result.stdout.decode().split("\0")
             if path and "__pycache__" not in path and Path(path).suffix in extensions]
    if not paths:
        raise ValueError("Native tracked source inventory is empty")
    return paths


def fingerprint(workspace: Path) -> dict:
    sources = set(REQUIRED_SOURCES)
    sources.update(native_tracked_sources(workspace))
    sources.update(path.relative_to(workspace) for path in
                   (workspace / BASE / "preflight").glob("probe_*.py"))
    support = workspace / "tools/diaggen_support"
    helpers = [path for path in support.rglob("*")
               if path.is_file() and path.suffix in {".py", ".sh", ".patch", ".json", ".js", ".md"}]
    if not helpers:
        raise ValueError("DiagGen support sources are missing")
    sources.update(path.relative_to(workspace) for path in helpers)
    sources.update(path.relative_to(workspace) for path in
                   (workspace / NATIVE / ".agents/skills/run-diaggen-pipeline").rglob("SKILL.md"))
    plan = json.loads((workspace / BASE / "batch_plan.json").read_text())
    jobs = plan.get("jobs")
    if not isinstance(jobs, list) or len(jobs) != 9 or len({job["id"] for job in jobs}) != 9:
        raise ValueError("Expected exactly nine distinct planned inputs")
    inputs = {}
    input_root = (workspace / BASE / "inputs").resolve()
    for job in jobs:
        path = (workspace / BASE / job["input"]).resolve()
        if not path.is_relative_to(input_root) or path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            raise ValueError(f"Invalid input location: {job['id']}")
        record = file_record(path)
        if record["sha256"] != job.get("input_sha256"):
            raise ValueError(f"Planned input hash mismatch: {job['id']}")
        inputs[job["id"]] = record
    with ThreadPoolExecutor(max_workers=5) as pool:
        inventories = list(pool.map(environment_inventory,
                                   [workspace / prefix / "bin/python" for prefix in ENVIRONMENTS.values()]))
    return {"sources": {str(path): file_record(workspace / path) for path in sorted(sources)},
            "inputs": inputs, "environments": dict(zip(ENVIRONMENTS, inventories)),
            "binaries": binary_inventory(workspace)}


def passing_report(path: Path) -> dict:
    report = json.loads(path.read_text())
    if not isinstance(report, dict):
        raise ValueError("Full preflight report must be an object")
    checks = report.get("checks")
    if (str(report.get("overall_status", "")).lower() != "pass"
            or not isinstance(checks, list) or not checks
            or any(not isinstance(check, dict) or str(check.get("status", "")).lower() != "pass"
                   for check in checks)):
        raise ValueError("Full preflight report is incomplete or contains non-passing checks")
    return {"path": str(path.resolve()), "sha256": sha256(path), "checks_passed": len(checks)}


def certify(workspace: Path, report: Path, certificate: Path) -> dict:
    evidence = passing_report(report)
    runtime = fingerprint(workspace)
    # Refuse a report modified during the snapshot operation.
    if evidence != passing_report(report):
        raise ValueError("Preflight report changed while certifying")
    payload = {"schema_version": SCHEMA, "overall_status": "pass",
               "certified_at": datetime.now(timezone.utc).isoformat(),
               "workspace": str(workspace), "report": evidence, "fingerprint": runtime}
    certificate.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".preflight-", dir=certificate.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, certificate)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"status": "pass", "checks_passed": evidence["checks_passed"]}


def verify(workspace: Path, certificate: Path) -> dict:
    payload = json.loads(certificate.read_text())
    if (not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA or payload.get("overall_status") != "pass"
            or payload.get("workspace") != str(workspace)):
        raise ValueError("Invalid certificate schema, status or workspace")
    if payload.get("report") != passing_report(Path(payload["report"]["path"])):
        raise ValueError("Certified preflight report changed")
    if payload.get("fingerprint") != fingerprint(workspace):
        raise ValueError("Runtime changed since full preflight; run the probes again")
    return {"status": "pass", "checks_passed": payload["report"]["checks_passed"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("certify", "verify"))
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--report", type=Path)
    parser.add_argument("--certificate", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        workspace = args.workspace.resolve()
        if args.command == "certify":
            if args.report is None:
                raise ValueError("certify requires --report")
            result = certify(workspace, args.report.resolve(), args.certificate.resolve())
        else:
            result = verify(workspace, args.certificate.resolve())
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

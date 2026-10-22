#!/usr/bin/env python3
"""Compare tiny OmniPart Native sparse convolution with explicit implicit GEMM.

This is a dependency/backend probe, not full OmniPart inference or a reproduction
of the large-tensor int32 assertion. Run with the isolated OmniPart Python.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback

WORKSPACE = Path(__file__).resolve().parents[3]
DIAGGEN = WORKSPACE / "tools/diaggen"
OMNIPART = DIAGGEN / "third_party/OmniPart"
LOCK = WORKSPACE / "sims/diaggen_genesis/queue/preflight_gpu.lock"
MINIMUM_FREE_MIB = 8192


def query_gpu(gpu_uuid):
    if not re.fullmatch(r"GPU-[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}", gpu_uuid):
        raise ValueError("one complete GPU UUID is required")
    result = subprocess.run([
        "nvidia-smi", "-i", gpu_uuid,
        "--query-gpu=uuid,memory.free,name", "--format=csv,noheader,nounits",
    ], check=True, capture_output=True, text=True, timeout=15)
    rows = [line.split(",", 2) for line in result.stdout.strip().splitlines()]
    if len(rows) != 1 or len(rows[0]) != 3 or rows[0][0].strip() != gpu_uuid:
        raise ValueError("ambiguous GPU identity")
    return {"uuid": gpu_uuid, "free_mib": int(rows[0][1]), "name": rows[0][2].strip()}


def execute(gpu_uuid):
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu_uuid
    os.environ["SPCONV_ALGO"] = "native"
    os.environ["SPARSE_BACKEND"] = "spconv"
    os.environ["PYTHONNOUSERSITE"] = "1"
    sys.path.insert(0, str(OMNIPART))
    import torch
    import spconv
    import spconv.pytorch as sparse
    from modules.part_synthesis.modules.sparse import SparseTensor
    from modules.part_synthesis.modules.sparse.conv import SPCONV_ALGO, SparseConv3d

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise ValueError("expected exactly one visible CUDA device")
    properties = torch.cuda.get_device_properties(0)
    actual_uuid = str(getattr(properties, "uuid", ""))
    if actual_uuid.removeprefix("GPU-") != gpu_uuid.removeprefix("GPU-"):
        raise ValueError(f"CUDA device UUID mismatch: {actual_uuid}")
    if SPCONV_ALGO != "native":
        raise ValueError("OmniPart did not load the requested Native backend")

    torch.manual_seed(7201)
    coords = torch.tensor([[0, x, y, z] for x in range(2)
                           for y in range(2) for z in range(2)],
                          dtype=torch.int32, device="cuda")
    native = SparseConv3d(8, 8, 3, bias=False).cuda().eval()
    implicit = sparse.SubMConv3d(8, 8, 3, bias=False,
                                algo=sparse.ConvAlgo.MaskImplicitGemm).cuda().eval()
    if native.conv.algo != sparse.ConvAlgo.Native:
        raise ValueError("OmniPart wrapper did not instantiate ConvAlgo.Native")
    if native.conv.weight.shape != implicit.weight.shape:
        raise ValueError("backend weight layouts differ; explicit conversion is required")
    with torch.no_grad():
        native.conv.weight.fill_(1)
        ones = torch.ones((8, 8), dtype=torch.float32, device="cuda")
        answer = native(SparseTensor(ones, coords)).feats
        analytic_error = float((answer - 64).abs().max().item())
        if answer.shape != (8, 8) or not torch.isfinite(answer).all() or analytic_error > 1e-4:
            raise ValueError(f"Native analytical output mismatch: {analytic_error}")

        # Same full-precision input and weights; no quantization or model edits.
        features = torch.randn((8, 8), dtype=torch.float32, device="cuda")
        native.conv.weight.copy_(torch.randn_like(native.conv.weight) * .1)
        implicit.weight.copy_(native.conv.weight)
        a = native(SparseTensor(features, coords))
        b = implicit(sparse.SparseConvTensor(features, coords, [2, 2, 2], 1))
        if not torch.equal(a.coords, b.indices):
            raise ValueError("backend output coordinate order differs")
        parity_error = float((a.feats - b.features).abs().max().item())
        torch.testing.assert_close(a.feats, b.features, atol=1e-4, rtol=1e-4)
        if not torch.isfinite(a.feats).all():
            raise ValueError("non-finite Native random output")
    torch.cuda.synchronize()
    return {
        "torch": torch.__version__, "spconv": spconv.__version__,
        "gpu_uuid": actual_uuid, "gpu_name": properties.name,
        "backend": SPCONV_ALGO, "native_conv_algo": str(native.conv.algo),
        "baseline_conv_algo": str(implicit.algo), "dtype": "float32",
        "active_voxels": 8, "input_channels": 8, "output_channels": 8,
        "analytic_expected_each_output": 64,
        "analytic_max_absolute_error": analytic_error,
        "backend_parity_max_absolute_error": parity_error,
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        "model_instances_loaded": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu-uuid", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    allowed = (DIAGGEN / "outputs/preflight").resolve()
    output = args.output_dir.resolve()
    if not output.is_relative_to(allowed) or output == allowed:
        parser.error("--output-dir must be a fresh child of tools/diaggen/outputs/preflight")
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "schema_version": "diaggen-spconv-backend-probe-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "failed", "minimum_free_mib": MINIMUM_FREE_MIB,
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "limitations": ["tiny dependency/backend probe only",
                        "does not reproduce or prove resolution of the large-tensor int32 assertion",
                        "does not load model checkpoints or measure production peak VRAM"],
    }
    try:
        with LOCK.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            report["gpu_before"] = query_gpu(args.gpu_uuid)
            if report["gpu_before"]["free_mib"] < MINIMUM_FREE_MIB:
                raise RuntimeError("insufficient free GPU memory; no CUDA probe started")
            with redirect_stdout(sys.stderr):
                report["result"] = execute(args.gpu_uuid)
            report["status"] = "success"
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        traceback.print_exc(file=sys.stderr)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())

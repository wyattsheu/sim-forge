#!/usr/bin/env python3
"""Functional dependency probes; never starts model inference or edits run state.

Run in .conda/omnipart. CUDA checks require an explicitly selected GPU UUID
with at least 8192 MiB free immediately before each check. The caller serializes
this script with the shared preflight_gpu.lock when another probe uses CUDA.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback
import zipfile


WORKSPACE = Path(__file__).resolve().parents[3]
DIAGGEN = WORKSPACE / "tools/diaggen"
OMNIPART = DIAGGEN / "third_party/OmniPart"
MINIMUM_FREE_MIB = 8192


class Skipped(RuntimeError):
    pass


def query_gpu(gpu_uuid: str) -> dict:
    if not re.fullmatch(r"GPU-[0-9A-Fa-f-]+", gpu_uuid):
        raise ValueError("--gpu-uuid must be one exact NVIDIA GPU UUID")
    result = subprocess.run(
        ["nvidia-smi", "-i", gpu_uuid,
         "--query-gpu=uuid,memory.free,name", "--format=csv,noheader,nounits"],
        check=True, capture_output=True, text=True, timeout=15,
    )
    rows = [line.split(",", 2) for line in result.stdout.strip().splitlines()]
    if len(rows) != 1 or len(rows[0]) != 3 or rows[0][0].strip() != gpu_uuid:
        raise ValueError("nvidia-smi returned an ambiguous GPU identity")
    return {"uuid": gpu_uuid, "free_mib": int(rows[0][1]), "name": rows[0][2].strip()}


def run(output_dir: Path, gpu_uuid: str | None) -> dict:
    output_dir = output_dir.resolve()
    allowed_root = (DIAGGEN / "outputs/preflight").resolve()
    if not output_dir.is_relative_to(allowed_root) or output_dir == allowed_root:
        raise ValueError("output directory must be a unique child of tools/diaggen/outputs/preflight")
    output_dir.mkdir(parents=True, exist_ok=False)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["PYTHONNOUSERSITE"] = "1"
    cuda_home = os.environ.get("CUDA_HOME", "/usr/local/cuda-12.8")
    os.environ["CUDA_HOME"] = cuda_home
    os.environ["PATH"] = os.pathsep.join(
        [str(Path(sys.prefix) / "bin"), str(Path(cuda_home) / "bin"), os.environ.get("PATH", "")]
    )
    # Native JIT probes get a new output-only cache; no shared extensions changed.
    os.environ["TORCH_EXTENSIONS_DIR"] = str(output_dir / "torch_extensions")
    os.environ.setdefault("TORCH_CUDA_ARCH_LIST", "12.0")
    os.environ.setdefault("MAX_JOBS", "2")
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu_uuid or ""
    sys.path[:0] = [str(DIAGGEN), str(OMNIPART)]
    os.chdir(OMNIPART)
    checks: list[dict] = []
    scratch: dict = {}

    def check(name, operation, *, gpu=False):
        started = time.monotonic()
        entry = {"name": name, "status": "pass"}
        captured = io.StringIO()
        try:
            if gpu:
                if not gpu_uuid:
                    raise Skipped("No --gpu-uuid supplied; CUDA execution was not attempted")
                gpu_state = query_gpu(gpu_uuid)
                entry["gpu_before"] = gpu_state
                if gpu_state["free_mib"] < MINIMUM_FREE_MIB:
                    raise Skipped(f"Only {gpu_state['free_mib']} MiB free; tiny probes require {MINIMUM_FREE_MIB} MiB")
            with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                detail = operation()
            entry["detail"] = detail
        except Skipped as exc:
            entry.update(status="skip", detail=str(exc))
        except Exception as exc:
            entry.update(status="fail", detail=f"{type(exc).__name__}: {exc}")
            (output_dir / f"{name}.traceback.txt").write_text(traceback.format_exc())
        if captured.getvalue():
            (output_dir / f"{name}.log").write_text(captured.getvalue())
        entry["elapsed_seconds"] = round(time.monotonic() - started, 3)
        checks.append(entry)
        print(json.dumps(entry), flush=True)
        return entry["status"] == "pass"

    def dependency_imports():
        names = ["torch", "torchvision", "flash_attn", "spconv.pytorch", "cumm",
                 "nvdiffrast.torch", "diff_gaussian_rasterization", "xatlas",
                 "torch_scatter", "cv2", "trimesh", "scipy.ndimage", "pyvista",
                 "pymeshfix", "mesh2sdf", "rembg", "onnxruntime", "transformers",
                 "diffusers", "utils3d", "safetensors", "imageio_ffmpeg", "ninja"]
        result, failures = {}, []
        for name in names:
            try:
                module = importlib.import_module(name)
                # utils3d lazily imports any requested attribute; asking it for
                # absent __version__ would itself create a false import failure.
                result[name] = vars(module).get("__version__", "imported")
            except Exception as exc:
                failures.append(f"{name}: {type(exc).__name__}: {exc}")
        (output_dir / "import_versions.json").write_text(json.dumps(result, indent=2))
        if failures:
            raise RuntimeError("; ".join(failures))
        return result

    check("dependency_imports", dependency_imports)

    def native_modules():
        modules = ["modules.part_synthesis.pipelines", "modules.bbox_gen.models.autogressive_bbox_gen",
                   "modules.hag4r_step16_inputs", "modules.part_synthesis.process_utils",
                   "hag4r.tools.post_mesh_texture"]
        for name in modules:
            importlib.import_module(name)
        return {"modules": modules, "model_instances_created": 0}

    check("native_stage_imports", native_modules)

    def offline_weights():
        from huggingface_hub import hf_hub_download
        from safetensors import safe_open
        import torch
        records = []
        config = json.loads(Path(hf_hub_download("omnipart/OmniPart", "pipeline.json", local_files_only=True)).read_text())
        for key, relative in config["args"]["models"].items():
            model_cfg = Path(hf_hub_download("omnipart/OmniPart", relative + ".json", local_files_only=True))
            model_path = Path(hf_hub_download("omnipart/OmniPart", relative + ".safetensors", local_files_only=True))
            parsed = json.loads(model_cfg.read_text())
            with safe_open(model_path, framework="pt", device="cpu") as handle:
                tensor_count = len(handle.keys())
            if not tensor_count or not parsed.get("name"):
                raise ValueError(f"empty model configuration/checkpoint: {key}")
            records.append({"name": key, "bytes": model_path.stat().st_size, "tensor_count": tensor_count})
        dino_cfg = json.loads(Path(hf_hub_download("facebook/dinov2-with-registers-large", "config.json", local_files_only=True)).read_text())
        dino_weights = Path(hf_hub_download("facebook/dinov2-with-registers-large", "model.safetensors", local_files_only=True))
        with safe_open(dino_weights, framework="pt", device="cpu") as handle:
            dino_tensor_count = len(handle.keys())
        if dino_cfg.get("model_type") != "dinov2_with_registers" or not dino_tensor_count:
            raise ValueError("invalid offline DINOv2 HF config/checkpoint")
        records.append({"name": "dinov2_hf", "bytes": dino_weights.stat().st_size, "tensor_count": dino_tensor_count})
        # Check ZIP structure only: loading the full multi-GB pickle is unnecessary here.
        paths = [OMNIPART / "ckpt/partfield_encoder.ckpt", OMNIPART / "ckpt/bbox_gen.ckpt",
                 Path(torch.hub.get_dir()) / "checkpoints/dinov2_vitl14_reg4_pretrain.pth"]
        for path in paths:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                if not any(name.endswith("data.pkl") for name in names) or not any("/data/" in name for name in names):
                    raise ValueError(f"checkpoint ZIP lacks tensors/pickle: {path.name}")
            records.append({"name": path.name, "bytes": path.stat().st_size, "zip_entries": len(names)})
        hub_repo = Path(torch.hub.get_dir()) / "facebookresearch_dinov2_main"
        for relative in ["hubconf.py", "dinov2/hub/backbones.py"]:
            if not (hub_repo / relative).is_file():
                raise FileNotFoundError(f"offline torch hub source missing {relative}")
        return {"weights": records, "network_used": False, "large_models_loaded": False}

    check("offline_weight_inventory", offline_weights)

    def toolchain():
        import imageio_ffmpeg
        commands = {
            "nvcc": [str(Path(cuda_home) / "bin/nvcc"), "--version"],
            "cxx": [shutil.which(os.environ.get("CXX", "c++")) or "c++", "--version"],
            "ninja": [shutil.which("ninja") or "ninja", "--version"],
            "ffmpeg": [imageio_ffmpeg.get_ffmpeg_exe(), "-version"],
        }
        result = {}
        for name, command in commands.items():
            proc = subprocess.run(command, check=True, capture_output=True, text=True, timeout=20)
            result[name] = {"executable": command[0], "version": (proc.stdout or proc.stderr).splitlines()[0]}
        return result

    check("external_toolchain", toolchain)

    def tiny_video_roundtrip():
        import imageio.v2 as imageio
        import numpy as np
        path = output_dir / "codec_probe.mp4"
        frames = [np.full((32, 32, 3), value, dtype=np.uint8) for value in [16, 80, 160, 240]]
        imageio.mimwrite(path, frames, fps=4, codec="libx264", macro_block_size=None)
        decoded = imageio.mimread(path, memtest="4MB")
        means = [float(frame.mean()) for frame in decoded]
        if len(decoded) != 4 or not all(b > a for a, b in zip(means, means[1:])):
            raise ValueError(f"video round trip corrupted: {means}")
        return {"frames": len(decoded), "means": means, "bytes": path.stat().st_size}

    check("ffmpeg_encode_decode", tiny_video_roundtrip)

    def exact_texture_binding():
        import numpy as np
        from PIL import Image
        from hag4r.tools import post_mesh_texture as texture
        points = np.asarray([[0, 0, 0], [.1, 0, 0], [0, .1, 0], [0, 0, .1]], dtype=np.float64)
        tets = np.asarray([[0, 1, 2, 3]], dtype=np.int64)
        labels = np.asarray([0], dtype=np.int64)
        inputs = texture.ExactBindingInputs(points, tets, labels, 1)
        boundary = texture.extract_exact_tet_boundary(physics_vertices_m=points, tets=tets, tet_part_labels=labels, declared_part_count=1)
        binding = texture.unwrap_exact_tet_boundary(boundary=boundary, physics_vertices_m=points, tets=tets, tet_part_labels=labels, declared_part_count=1)
        albedo = output_dir / "albedo.png"
        Image.new("RGB", (texture.ATLAS_RESOLUTION, texture.ATLAS_RESOLUTION), (40, 150, 210)).save(albedo)
        glb_result = texture._write_visual_mesh_glb(output_path=output_dir / "visual_mesh.glb", albedo_path=albedo, binding=binding, binding_inputs=inputs)
        scratch["binding"] = binding
        return {"physical_vertices": len(points), "tets": len(tets), "xatlas_visual_vertices": len(binding.visual_uv), "glb_roundtrip": glb_result}

    check("xatlas_exact_binding_and_glb", exact_texture_binding)

    def existing_usb_fixture():
        import trimesh
        from modules.part_synthesis.appearance_evidence import _validate_manifest_and_bundle
        fixture = DIAGGEN / "outputs/agentic_asset_refinement/genesis_first_20261021_exr_retry1/revisions/revision_0000/omnipart/genesis_first_20261021_exr_retry1"
        if not fixture.is_dir():
            raise Skipped("Recorded USB intermediate fixture is absent; synthetic binding test remains independent")
        mesh = trimesh.load(fixture / "mesh_combined_textured.glb", force="scene", process=False)
        if not mesh.geometry:
            raise ValueError("USB GLB has no geometry")
        validation = _validate_manifest_and_bundle(fixture / "appearance")
        if validation.get("valid") is not True:
            raise ValueError(f"USB appearance fixture is invalid: {validation}")
        return {"geometry_count": len(mesh.geometry), "appearance_validation": validation, "fixture_written": False}

    check("existing_usb_glb_and_appearance", existing_usb_fixture)

    def cuda_identity():
        import torch
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError("Expected exactly one explicit visible CUDA GPU")
        props = torch.cuda.get_device_properties(0)
        device_uuid = str(getattr(props, "uuid", ""))
        if device_uuid and device_uuid.removeprefix("GPU-") != gpu_uuid.removeprefix("GPU-"):
            raise ValueError(f"CUDA device UUID mismatch: {device_uuid}")
        result = (torch.ones(16, device="cuda") * 3).sum().item()
        if result != 48:
            raise ValueError("CUDA arithmetic produced an incorrect result")
        return {"name": props.name, "uuid": device_uuid, "capability": list(torch.cuda.get_device_capability(0)), "torch": torch.__version__}

    check("cuda_identity_arithmetic", cuda_identity, gpu=True)

    def attention():
        import torch
        from modules.part_synthesis.modules.attention import scaled_dot_product_attention
        torch.manual_seed(7)
        qkv = torch.randn((1, 16, 3, 2, 32), dtype=torch.float16, device="cuda")
        actual = scaled_dot_product_attention(qkv)
        q, k, v = (qkv[:, :, index].transpose(1, 2).float() for index in range(3))
        reference = torch.nn.functional.scaled_dot_product_attention(q, k, v).transpose(1, 2)
        error = float((actual.float() - reference).abs().max().item())
        if not torch.isfinite(actual).all() or error > .01:
            raise ValueError(f"attention mismatch max_abs_error={error}")
        return {"shape": list(actual.shape), "max_abs_error_vs_float32_sdpa": error}

    check("native_flash_attention_kernel", attention, gpu=True)

    def sparse_conv():
        import torch
        import spconv.pytorch as spconv
        coords = torch.tensor([[0, x, y, z] for x in range(2) for y in range(2) for z in range(2)], dtype=torch.int32, device="cuda")
        features = torch.ones((8, 8), dtype=torch.float32, device="cuda")
        tensor = spconv.SparseConvTensor(features, coords, spatial_shape=[4, 4, 4], batch_size=1)
        conv = spconv.SubMConv3d(8, 8, 3, padding=1, bias=False).cuda().eval()
        with torch.no_grad():
            conv.weight.fill_(1)
            result = conv(tensor).features
        error = float((result - 64).abs().max().item())
        if result.shape != (8, 8) or error > 1e-4:
            raise ValueError(f"spconv output mismatch: shape={tuple(result.shape)} error={error}")
        return {"active_voxels": 8, "channels": 8, "expected_each_output": 64, "max_abs_error": error}

    check("spconv_actual_convolution", sparse_conv, gpu=True)

    def scatter_kernel():
        import torch
        from torch_scatter import scatter_add
        actual = scatter_add(torch.tensor([1., 2., 3.], device="cuda"), torch.tensor([0, 1, 0], device="cuda"))
        if actual.tolist() != [4., 2.]:
            raise ValueError(f"scatter output mismatch: {actual.tolist()}")
        return {"output": actual.tolist()}

    check("torch_scatter_cuda", scatter_kernel, gpu=True)

    def texture_raster():
        import torch
        import numpy as np
        import nvdiffrast.torch as dr
        from hag4r.tools import post_mesh_texture as texture
        binding = scratch.get("binding")
        if binding is None:
            raise RuntimeError("CPU exact binding test failed; cannot rasterize its output")
        vertices = binding.visual_rest_vertices_m
        triangles = vertices[binding.visual_faces]
        normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        normals /= np.linalg.norm(normals, axis=1, keepdims=True)
        context = dr.RasterizeCudaContext(device="cuda")
        raster = texture._rasterize_uv_target(binding, vertices, normals, raster_context=context, device=torch.device("cuda"), raster_resolution=64)
        occupied = int((raster.chart_face_id >= 0).sum().item())
        if occupied <= 0 or not torch.isfinite(raster.target_points_internal).all():
            raise ValueError("native UV raster contains no valid geometry")
        sampled = texture._sample_texture(torch.full((2, 2, 3), .25, device="cuda"), torch.tensor([[.5, .5]], device="cuda"), filter_mode="linear")
        if not torch.allclose(sampled, torch.full_like(sampled, .25)):
            raise ValueError("native nvdiffrast texture sample mismatch")
        return {"raster_resolution": 64, "occupied_texels": occupied, "sampled_rgb": sampled.tolist(), "jit_cache": str(output_dir / "torch_extensions")}

    check("native_texture_uv_raster_and_sample", texture_raster, gpu=True)

    def gaussian_render():
        import torch
        import numpy as np
        from PIL import Image
        from modules.part_synthesis.representations.gaussian.gaussian_model import Gaussian
        from modules.part_synthesis.renderers.gaussian_render import GaussianRenderer
        gaussian = Gaussian(aabb=[-.5, -.5, -.5, 1., 1., 1.], sh_degree=0, mininum_kernel_size=0., scaling_bias=.01, opacity_bias=.1, scaling_activation="exp", device="cuda")
        gaussian.from_xyz(torch.tensor([[0., 0., 1.]], device="cuda"))
        gaussian.from_scaling(torch.full((1, 3), .12, device="cuda"))
        gaussian.from_rotation(torch.tensor([[1., 0., 0., 0.]], device="cuda"))
        gaussian.from_opacity(torch.full((1, 1), .95, device="cuda"))
        gaussian.from_features(torch.zeros((1, 1, 3), device="cuda"))
        renderer = GaussianRenderer({"resolution": 32, "near": .1, "far": 10., "ssaa": 1, "bg_color": (0, 0, 0)})
        intrinsics = torch.tensor([[1., 0., .5], [0., 1., .5], [0., 0., 1.]], device="cuda")
        frame = renderer.render(gaussian, torch.eye(4, device="cuda"), intrinsics)["color"]
        if not torch.isfinite(frame).all() or not (frame > 0).any():
            raise ValueError("native gaussian CUDA rasterizer produced an empty/non-finite frame")
        image = np.clip(frame.detach().cpu().numpy().transpose(1, 2, 0) * 255, 0, 255).astype(np.uint8)
        Image.fromarray(image).save(output_dir / "gaussian_probe.png")
        return {"resolution": [32, 32], "gaussians": 1, "maximum_pixel": float(frame.max().item())}

    check("native_gaussian_rasterizer", gaussian_render, gpu=True)
    counts = {status: sum(entry["status"] == status for entry in checks) for status in ["pass", "fail", "skip"]}
    report = {
        "schema_version": "diaggen-omnipart-preflight-v1",
        "status": "fail" if counts["fail"] else "partial" if counts["skip"] else "pass",
        "python": sys.executable, "checks": checks, "counts": counts,
        "limits": ["No full OmniPart/SAM3 inference, no model quality or full-run VRAM claim.",
                   "Checkpoint validation reads safetensors headers and pickle ZIP inventories; not every model tensor was read.",
                   "Texture GPU check uses native 64x64 UV raster/sample and synthetic tetrahedron; not the full 1024x1024 rebake."]
    }
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--gpu-uuid")
    args = parser.parse_args()
    report = run(args.output_dir, args.gpu_uuid)
    print(json.dumps(report, indent=2))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())

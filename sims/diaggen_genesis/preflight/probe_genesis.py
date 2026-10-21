#!/usr/bin/env python3
"""Isolated Genesis dependency/live FEM/render/video smoke, never a pipeline run.

Run with the bundled Genesis interpreter. Hardware work is opt-in via an exact
GPU UUID; callers serialize hardware probes with queue/preflight_gpu.lock.
Exit 0 means every requested check passed, 1 is failure, 2 includes a deferred
hardware check. Each invocation requires a fresh directory beneath native
DiagGen outputs/preflight. No diagnostic ownership or production state is used.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import traceback


WORKSPACE = Path(__file__).resolve().parents[3]
DIAGGEN = WORKSPACE / "tools/diaggen"
GENESIS = DIAGGEN / "third_party/genesis-world"
MINIMUM_FREE_MIB = 8192


def check_gpu(uuid: str) -> dict:
    completed = subprocess.run(
        ["nvidia-smi", "--query-gpu=uuid,memory.free", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True, timeout=15,
    )
    matches = []
    for line in completed.stdout.splitlines():
        values = [item.strip() for item in line.split(",")]
        if len(values) == 2 and values[0] == uuid:
            matches.append({"uuid": uuid, "free_mib": int(values[1])})
    if len(matches) != 1:
        raise ValueError("exact GPU UUID was not found once in nvidia-smi")
    return matches[0]


def validate_geometry(value: dict) -> None:
    import numpy as np
    if value.get("vertex_count") != 5 or value.get("element_count") != 2:
        raise ValueError(f"fixture vertex/tet counts differ: {value}")
    if value.get("representation") != "volumetric":
        raise ValueError("fixture is not volumetric FEM")
    bounds = np.asarray([value["bbox_min"], value["bbox_max"]], dtype=float)
    if bounds.shape != (2, 3) or not np.isfinite(bounds).all():
        raise ValueError("live readback has missing/nonfinite bounds")
    if not (bounds[1] > bounds[0]).all():
        raise ValueError("live readback bounds collapsed")


def png_records(value):
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and value["path"].endswith(".png"):
            yield value
        for child in value.values():
            yield from png_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from png_records(child)


def validate_render(value: dict, output_dir: Path) -> list[Path]:
    import numpy as np
    from PIL import Image
    records = {record["path"]: record for record in png_records(value)}
    if not records:
        raise ValueError("live renderer returned no PNG artifact records")
    paths = []
    nonuniform = False
    for raw_path, record in records.items():
        path = Path(raw_path).resolve()
        if not path.is_relative_to(output_dir) or not path.is_file():
            raise ValueError("renderer artifact missing or outside isolated output")
        if record.get("byte_size") is not None and record["byte_size"] != path.stat().st_size:
            raise ValueError("renderer byte-size evidence differs")
        if record.get("sha256") and record["sha256"] != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError("renderer SHA-256 differs")
        with Image.open(path) as image:
            image.load()
            rgb = np.asarray(image.convert("RGB"))
            if image.width < 64 or image.height < 64:
                raise ValueError("rendered image is unexpectedly small")
            nonuniform = nonuniform or bool(np.any(rgb != rgb[0, 0]))
        paths.append(path)
    if not nonuniform:
        raise ValueError("all renderer artifacts are uniform blank images")
    return paths


def fixture(output: Path) -> Path:
    import igl
    import numpy as np
    mesh = output / "two_tets.mesh"
    materials = output / "heterogeneous_params.npz"
    palette = output / "part_palette.npz"
    vertices = np.array([[0., 0., 0.], [.1, 0., 0.], [0., .1, 0.], [0., 0., .1], [0., 0., -.1]])
    tets = np.array([[0, 1, 2, 3], [0, 2, 1, 4]], dtype=np.int64)
    igl.writeMESH(str(mesh), vertices, tets, np.empty((0, 3), dtype=np.int64))
    np.savez(materials, tet_E_nu=np.array([[1e5, .3], [2e5, .35]]),
             tet_density=np.array([1000., 1200.]), tet_part_labels=np.array([0, 1], dtype=np.int32))
    np.savez(palette, part_colors=np.array([[30, 220, 80], [220, 110, 30]], dtype=np.uint8))
    scene = {
        "backend": "cuda",
        "sim_options": {"dt": .001, "substeps": 2},
        "fem_options": {"use_implicit_solver": True, "enable_qualification_safety_extrema": True},
        "entities": [{"name": "body", "morph": {"type": "tet_mesh", "file": str(mesh)},
                      "material": {"type": "elastic", "heterogeneous": {"file": str(materials)}},
                      "part_segmentation": {"primitive_labels_file": str(materials),
                                            "primitive_labels_key": "tet_part_labels",
                                            "palette_file": str(palette), "palette_key": "part_colors",
                                            "parts": [{"part_id": 0, "part_name": "green", "part_color_rgb": [30, 220, 80]},
                                                      {"part_id": 1, "part_name": "orange", "part_color_rgb": [220, 110, 30]}],
                                            "context_palette": {"background": [0, 0, 0], "fixture": [41, 110, 255], "probe": [255, 89, 41]}}}],
    }
    config = output / "scene.json"
    config.write_text(json.dumps(scene, indent=2) + "\n")
    return config


def close_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--gpu-uuid")
    parser.add_argument("--timeout-seconds", type=int, default=360)
    args = parser.parse_args(argv)
    output = args.output_dir.expanduser().resolve()
    permitted = (DIAGGEN / "outputs/preflight").resolve()
    if not output.is_relative_to(permitted) or output == permitted:
        parser.error("output directory must be a fresh child of tools/diaggen/outputs/preflight")
    if output.exists() and any(output.iterdir()):
        parser.error("output directory must be empty to exclude stale artifacts")
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": "diaggen-genesis-preflight-v1", "checks": [],
              "runtime": {"python": sys.executable, "genesis_root": str(GENESIS),
                          "gpu_uuid": args.gpu_uuid, "minimum_free_mib": MINIMUM_FREE_MIB},
              "artifacts": [], "limitations": ["Synthetic two-tet fixture; does not prove full generated-asset stability or peak VRAM.",
                                                 "Does not attach to any production diagnostic run or lease."]}

    def record(name, status, detail):
        report["checks"].append({"name": name, "status": status, "detail": detail})
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"{status}: {name}", file=sys.stderr, flush=True)

    def run_check(name, fn):
        try:
            result = fn()
            record(name, "PASS", result)
            return result
        except Exception as error:
            record(name, "FAIL", f"{type(error).__name__}: {error}")
            (output / f"{name}.traceback.txt").write_text(traceback.format_exc())
            return None

    # Import the bundled fork by explicit path, without modifying any installation.
    sys.path.insert(0, str(GENESIS))
    os.environ["PYTHONNOUSERSITE"] = "1"
    os.environ["GS_CACHE_FILE_PATH"] = str(output / ".cache/genesis")
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
    required_imports = ["genesis", "genesis.live.server", "genesis.live.visual_telemetry",
                        "genesis.ext.pyrender", "genesis.utils.heterogeneous_materials",
                        "igl", "numpy", "scipy", "torch", "pyglet", "OpenGL", "imageio", "imageio_ffmpeg"]
    for name in required_imports:
        run_check("import_" + name.replace(".", "_"),
                  lambda name=name: {"module": name, "file": getattr(importlib.import_module(name), "__file__", None)})
    encoder = DIAGGEN / "scripts/generate_simulation_mp4.sh"
    run_check("native_diagnostic_mp4_script", lambda: str(encoder) if encoder.is_file() and os.access(encoder, os.X_OK)
              else (_ for _ in ()).throw(FileNotFoundError(f"required executable is absent: {encoder}")))
    for binary in ("ffmpeg", "ffprobe"):
        run_check("binary_" + binary, lambda binary=binary: shutil.which(binary)
                  or (_ for _ in ()).throw(FileNotFoundError(binary)))
    if not args.gpu_uuid:
        record("cuda_live_fem_render_video", "SKIP", "No exact --gpu-uuid supplied; hardware work was not requested.")
    elif any(item["status"] == "FAIL" and item["name"].startswith("import_") for item in report["checks"]):
        record("cuda_live_fem_render_video", "SKIP", "Required imports failed.")
    else:
        gpu = run_check("gpu_memory_gate", lambda: check_gpu(args.gpu_uuid))
        if gpu is None or gpu["free_mib"] < MINIMUM_FREE_MIB:
            record("cuda_live_fem_render_video", "SKIP", {"reason": "Need >=8192 MiB free immediately before tiny fixture launch.", "gpu": gpu})
        else:
            env = os.environ.copy()
            env.update({"CUDA_VISIBLE_DEVICES": args.gpu_uuid, "PYTHONPATH": str(GENESIS),
                        "LIBGL_ALWAYS_SOFTWARE": "1", "GALLIUM_DRIVER": "llvmpipe", "__GLX_VENDOR_LIBRARY_NAME": "mesa"})
            server = display = None
            sock = None
            logs = []
            try:
                xvfb = DIAGGEN / ".local/xvfb/usr/bin/Xvfb"
                if not xvfb.is_file() or not os.access(xvfb, os.X_OK):
                    raise FileNotFoundError(f"private Xvfb is missing: {xvfb}")
                display_number = output / "xdisplay.number"
                with display_number.open("w") as descriptor, (output / "xvfb.log").open("w") as logfile:
                    display = subprocess.Popen([str(xvfb), "-displayfd", str(descriptor.fileno()), "-screen", "0", "1024x768x24", "-nolisten", "tcp"],
                                               stdout=logfile, stderr=subprocess.STDOUT, pass_fds=(descriptor.fileno(),))
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and display.poll() is None and not display_number.read_text().strip():
                    time.sleep(.1)
                number = display_number.read_text().strip()
                if not number.isdigit() or display.poll() is not None:
                    raise RuntimeError("private Xvfb did not allocate a live display")
                env["DISPLAY"] = ":" + number
                record("private_xvfb", "PASS", {"display": env["DISPLAY"], "owned_pid": display.pid})
                # Recheck after display startup; a prior query is not a reservation.
                gpu = check_gpu(args.gpu_uuid)
                if gpu["free_mib"] < MINIMUM_FREE_MIB:
                    record("cuda_live_fem_render_video", "SKIP", {"reason": "GPU free memory dropped before launch", "gpu": gpu})
                else:
                    config = fixture(output)
                    ready_path = output / "ready.json"
                    for stream in ("stdout", "stderr"):
                        logs.append((output / f"genesis_live_{stream}.log").open("w"))
                    server = subprocess.Popen([sys.executable, "-B", "-m", "genesis.live.server", "--host", "127.0.0.1", "--port", "0",
                                               "--scene-config", str(config), "--ready-file", str(ready_path), "--output-dir", str(output / "live"), "--start-paused"],
                                              cwd=GENESIS, env=env, stdout=logs[0], stderr=logs[1])
                    deadline = time.monotonic() + args.timeout_seconds
                    while not ready_path.is_file() and time.monotonic() < deadline and server.poll() is None:
                        time.sleep(.2)
                    if not ready_path.is_file():
                        raise RuntimeError(f"native server did not become ready (exit={server.poll()}); inspect genesis_live_stderr.log")
                    ready = json.loads(ready_path.read_text())
                    if ready.get("server_pid") != server.pid or ready.get("protocol") != "genesis-live-v1":
                        raise ValueError("ready evidence does not belong to the launched fixture")
                    sock = socket.create_connection((ready["host"], ready["port"]), timeout=120)
                    from genesis.live.protocol import send_json, recv_json

                    def rpc(method, params=None, *, expect_error=False):
                        send_json(sock, {"request_id": method, "method": method, "params": params or {}})
                        response = recv_json(sock)
                        if expect_error:
                            if response.get("status") != "error":
                                raise ValueError("negative control unexpectedly succeeded")
                            return response
                        if response.get("status") != "ok":
                            raise RuntimeError(json.dumps(response))
                        return response["data"]

                    handshake = rpc("session.handshake")
                    import genesis as gs
                    if handshake.get("status", {}).get("backend") != str(gs.cuda):
                        raise ValueError(f"CUDA requested but runtime reports {handshake}")
                    record("live_ready_handshake", "PASS", {"protocol": handshake["protocol"], "capabilities": handshake["capabilities"], "backend": handshake["status"]["backend"], "port": ready["port"]})
                    negative = rpc("preflight.unknown_method", expect_error=True)
                    if negative.get("error", {}).get("code") != "unknown_method":
                        raise ValueError("negative RPC did not return typed unknown_method")
                    record("negative_rpc_rejected", "PASS", negative["error"])
                    before = rpc("geometry.context.get", {"entity": "body"})
                    validate_geometry(before)
                    observed = rpc("observation.fused")
                    if observed["material"].get("heterogeneous") is not True:
                        raise ValueError("runtime did not load heterogeneous material")
                    record("heterogeneous_fem_readback", "PASS", observed)
                    resumed = rpc("sim.resume", {"steps": 10})
                    after = rpc("geometry.context.get", {"entity": "body"})
                    validate_geometry(after)
                    if resumed["status"].get("current_step") != 10:
                        raise ValueError("runtime did not advance ten steps")
                    import numpy as np
                    displacement = float(np.linalg.norm(np.asarray(after["bbox_min"]) - before["bbox_min"]))
                    if displacement <= 1e-8:
                        raise ValueError("fixture did not move under gravity")
                    record("cuda_fem_step_finite_motion", "PASS", {"completed_steps": 10, "bbox_min_displacement_m": displacement, "geometry_after": after})
                    rendered = rpc("visual.capture", {"diagnostic_visual": {"mode": "part_shaded_triptych"}})
                    (output / "render_response.json").write_text(json.dumps(rendered, indent=2) + "\n")
                    images = validate_render(rendered, output)
                    record("native_part_shaded_triptych", "PASS", {"png_count": len(images), "paths": [str(path) for path in images]})
                    report["artifacts"].extend(str(path) for path in images)
                    # Capture two real physics states, then invoke the exact
                    # diagnostic encoder entrypoint and verify decoded output.
                    rpc("sim.resume", {"steps": 10})
                    second_render = rpc("visual.capture", {"diagnostic_visual": {"mode": "part_shaded_triptych"}})
                    (output / "render_response_second.json").write_text(json.dumps(second_render, indent=2) + "\n")
                    second_images = validate_render(second_render, output)
                    sequence = output / "captured_sequence"
                    sequence.mkdir()
                    for index, candidates in enumerate((images, second_images)):
                        source = next(path for path in candidates if path.parent.name == "png_part_shaded_triptych")
                        shutil.copy2(source, sequence / f"frame_{index:06d}.png")
                    video_scene = output / "video_scene.json"
                    video_scene.write_text(json.dumps({"timestep": .001, "output_png": str(sequence),
                                                       "render_png": {"capture_every_n_steps": 10}}) + "\n")
                    video_root = output / "encoded_video"
                    encoder_env = env | {"HAG4R_MP4_OUTPUT_ROOT": str(video_root),
                                         "HAG4R_PYTHON_BIN": sys.executable, "HAG4R_LEGACY_SIM_ROOT": "/"}
                    encoded = subprocess.run([str(encoder), str(video_scene), "10"],
                                             cwd=DIAGGEN, env=encoder_env, capture_output=True, text=True, timeout=120)
                    (output / "native_encoder.stdout.log").write_text(encoded.stdout)
                    (output / "native_encoder.stderr.log").write_text(encoded.stderr)
                    if encoded.returncode != 0:
                        raise RuntimeError("native diagnostic encoder failed: " + encoded.stderr[-1500:])
                    video = video_root / output.name / "video_scene.mp4"
                    decoded = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], capture_output=True, text=True, timeout=60)
                    if decoded.returncode != 0 or not video.is_file() or video.stat().st_size == 0:
                        raise ValueError("created MP4 did not decode: " + decoded.stderr[-1500:])
                    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height,nb_read_frames", "-of", "json", str(video)],
                                           capture_output=True, text=True, check=True, timeout=30)
                    stream = json.loads(probe.stdout)["streams"][0]
                    if int(stream["nb_read_frames"]) < 2:
                        raise ValueError("MP4 has fewer than two decoded frames")
                    record("mp4_encode_decode", "PASS", stream | {"encoder_script": str(encoder), "source": "two actual live captures"})
                    report["artifacts"].append(str(video))
                    rpc("session.close")
                    sock.close()
                    sock = None
                    server.wait(timeout=30)
                    if server.returncode != 0:
                        raise RuntimeError(f"owned server exited with {server.returncode}")
                    record("live_server_clean_close", "PASS", {"returncode": server.returncode})
            except Exception as error:
                record("cuda_live_fem_render_video", "FAIL", f"{type(error).__name__}: {error}")
                (output / "live.traceback.txt").write_text(traceback.format_exc())
            finally:
                if sock is not None:
                    sock.close()
                close_process(server)
                close_process(display)
                for stream in logs:
                    stream.close()
    statuses = {item["status"] for item in report["checks"]}
    report["overall_status"] = "FAIL" if "FAIL" in statuses else "SKIP" if "SKIP" in statuses else "PASS"
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return {"PASS": 0, "FAIL": 1, "SKIP": 2}[report["overall_status"]]


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Encode actual captured PNGs using the native diagnostic video path contract."""
import argparse
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image


def encode(scene_path, time_multiplier, *, environment=None):
    environment = os.environ if environment is None else environment
    scene_path = Path(scene_path).expanduser().resolve()
    scene = json.loads(scene_path.read_text())
    if not isinstance(scene, dict):
        raise ValueError("Scene must be a JSON object")
    timestep = scene.get("timestep")
    if isinstance(timestep, bool) or not isinstance(timestep, (int, float)) or not math.isfinite(timestep) or timestep <= 0:
        raise ValueError("A positive finite scene timestep is required")
    if not math.isfinite(time_multiplier) or time_multiplier <= 0:
        raise ValueError("Time multiplier must be positive and finite")
    render = scene.get("render_png", {})
    if not isinstance(render, dict):
        raise ValueError("render_png must be an object")
    stride = render.get("capture_every_n_steps", 1)
    if type(stride) is not int or stride <= 0:
        raise ValueError("capture_every_n_steps must be a positive integer")
    source = scene.get("output_png")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Scene output_png is required")
    frames = Path(source).expanduser()
    if not frames.is_absolute():
        legacy_root = environment.get("HAG4R_LEGACY_SIM_ROOT")
        if not legacy_root:
            raise ValueError("Relative output_png requires HAG4R_LEGACY_SIM_ROOT")
        frames = Path(legacy_root).expanduser() / frames
    frames = frames.resolve()
    paths = sorted(frames.glob("frame_*.png"))
    if not paths or any(path.name != f"frame_{index:06d}.png" for index, path in enumerate(paths)):
        raise ValueError("Captured frames must be contiguous from frame_000000.png")
    dimensions = None
    for path in paths:
        with Image.open(path) as image:
            if dimensions is None:
                dimensions = image.size
            if image.size != dimensions:
                raise ValueError("Captured frame dimensions differ")
            image.verify()
    output_root = environment.get("HAG4R_MP4_OUTPUT_ROOT")
    if not isinstance(output_root, str) or not output_root.strip():
        raise ValueError("HAG4R_MP4_OUTPUT_ROOT is required")
    output = Path(output_root).expanduser().resolve() / scene_path.parent.name / (scene_path.stem + ".mp4")
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise FileNotFoundError("Both ffmpeg and ffprobe are required")
    fps = Fraction(1) / (Fraction(str(timestep)) * stride * Fraction(str(time_multiplier)))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".mp4", delete=False) as stream:
            temporary = Path(stream.name)
        subprocess.run([
            ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-framerate", str(fps), "-start_number", "0", "-i", str(frames / "frame_%06d.png"),
            "-frames:v", str(len(paths)), "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-threads", "2",
            "-movflags", "+faststart", str(temporary),
        ], check=True, capture_output=True, text=True, timeout=600)
        probe = subprocess.run([
            ffprobe, "-v", "error", "-select_streams", "v:0", "-count_frames",
            "-show_entries", "stream=codec_name,width,height,nb_read_frames,avg_frame_rate",
            "-of", "json", str(temporary),
        ], check=True, capture_output=True, text=True, timeout=60)
        streams = json.loads(probe.stdout).get("streams", [])
        if len(streams) != 1 or streams[0].get("codec_name") != "h264":
            raise ValueError("Encoded video has no valid H.264 stream")
        video = streams[0]
        if int(video.get("nb_read_frames", -1)) != len(paths) or Fraction(video["avg_frame_rate"]) != fps:
            raise ValueError("Encoded frame count or frame rate differs from captured evidence")
        if temporary.stat().st_size <= 0:
            raise ValueError("Encoded video is empty")
        temporary.replace(output)
        return {"status": "success", "path": str(output), "frame_count": len(paths),
                "fps": float(fps), "width": video["width"], "height": video["height"],
                "source": "captured_png_sequence"}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scene_path", type=Path)
    parser.add_argument("time_multiplier", type=float)
    args = parser.parse_args()
    print(json.dumps(encode(args.scene_path, args.time_multiplier)))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Render an existing exported GLB with a camera that fits its full bounds.

Presentation only: read the asset, use a private software X display, and write
the additional preview outside the asset directory. Never modify native output.
Run with the installed OmniPart Python for its PyVista software renderer.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asset, output = args.asset_dir.resolve(), args.output.resolve()
    if output.is_relative_to(asset) or output.exists():
        raise ValueError("Use a new preview path outside the immutable asset directory")
    root = Path(__file__).resolve().parents[3]
    glb, albedo = asset / "appearance/visual_mesh.glb", asset / "appearance/albedo.png"
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    before = {str(path): digest(path) for path in (glb, albedo)}
    output.parent.mkdir(parents=True, exist_ok=True)
    read_fd, write_fd = os.pipe()
    server = subprocess.Popen([
        str(root / "tools/diaggen/.local/xvfb/usr/bin/Xvfb"),
        "-displayfd", str(write_fd), "-screen", "0", "1024x768x24", "-nolisten", "tcp",
    ], pass_fds=(write_fd,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.close(write_fd)
    try:
        if not select.select([read_fd], [], [], 10)[0]:
            raise RuntimeError("Private X display did not become ready")
        number = os.read(read_fd, 64).decode().strip()
        if not number.isdecimal():
            raise RuntimeError("Private X display returned an invalid selector")
        os.environ.update(DISPLAY=":" + number, CUDA_VISIBLE_DEVICES="",
                          LIBGL_ALWAYS_SOFTWARE="1", GALLIUM_DRIVER="llvmpipe",
                          __GLX_VENDOR_LIBRARY_NAME="mesa", PYVISTA_OFF_SCREEN="true",
                          VTK_DEFAULT_OPENGL_WINDOW="vtkXOpenGLRenderWindow")
        import numpy as np
        from PIL import Image
        import pyvista as pv
        import trimesh

        mesh = trimesh.load(glb, force="mesh", process=False)
        faces = np.column_stack((np.full(len(mesh.faces), 3), mesh.faces)).reshape(-1)
        surface = pv.PolyData(mesh.vertices, faces)
        surface.active_texture_coordinates = np.asarray(mesh.visual.uv)
        texture = pv.numpy_to_texture(np.asarray(Image.open(albedo).convert("RGB")))
        plotter = pv.Plotter(off_screen=True, window_size=(768, 768))
        try:
            plotter.disable_anti_aliasing()
            plotter.set_background((32 / 255,) * 3)
            plotter.add_mesh(surface, texture=texture, lighting=False)
            center = mesh.bounds.mean(axis=0)
            radius = float(np.linalg.norm(mesh.extents))
            direction = np.asarray([1., -1., 1.]) / np.sqrt(3.)
            plotter.camera_position = (center + radius * 3 * direction, center, (0, 1, 0))
            plotter.enable_parallel_projection()
            plotter.reset_camera()
            plotter.camera.zoom(0.9)
            plotter.render()
            pixels = plotter.screenshot(str(output))
            border = np.concatenate((pixels[0], pixels[-1], pixels[:, 0], pixels[:, -1]))
            if np.any(border[:, :3] != 32) or not np.any(pixels[:, :, :3] != 32):
                raise RuntimeError("Preview must show the asset with an empty image border")
            capabilities = plotter.ren_win.ReportCapabilities()
            renderer = next((line.split(":", 1)[1].strip() for line in capabilities.splitlines()
                             if line.startswith("OpenGL renderer string:")), "")
            if not any(name in renderer.lower() for name in ("llvmpipe", "softpipe", "swrast", "software")):
                raise RuntimeError("Expected the software renderer")
        finally:
            plotter.close()
        if before != {str(path): digest(path) for path in (glb, albedo)}:
            raise RuntimeError("Source asset changed while rendering")
        report = {"presentation_only": True, "source_asset_unchanged": True,
                  "source_glb_sha256": digest(glb), "source_albedo_sha256": digest(albedo),
                  "preview_sha256": digest(output), "vertices": len(mesh.vertices),
                  "faces": len(mesh.faces), "image_size": [768, 768],
                  "empty_image_border": True, "renderer": renderer}
        output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))
    finally:
        os.close(read_fd)
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    main()

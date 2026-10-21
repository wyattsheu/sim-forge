#!/usr/bin/env python3
"""CPU-only six-view PyVista display preflight, independent of pipeline state.

Run with the OmniPart Python after the caller starts a real private Xvfb and
sets DISPLAY. Images are temporary test geometry, never native asset outputs.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile


def check_display() -> dict:
    display = os.environ.get("DISPLAY", "").strip()
    if not display:
        raise RuntimeError("DISPLAY must identify an already running X server")

    # These controls belong only to this short-lived preflight process.
    # Do not export them to the complete DiagGen/Genesis worker.
    os.environ.update(
        CUDA_VISIBLE_DEVICES="",
        LIBGL_ALWAYS_SOFTWARE="1",
        GALLIUM_DRIVER="llvmpipe",
        __GLX_VENDOR_LIBRARY_NAME="mesa",
        VTK_DEFAULT_OPENGL_WINDOW="vtkXOpenGLRenderWindow",
        PYVISTA_OFF_SCREEN="true",
    )
    import numpy as np
    import pyvista as pv

    views = (
        ("front", (0, 0, 1), (0, 1, 0)),
        ("back", (0, 0, -1), (0, 1, 0)),
        ("left", (-1, 0, 0), (0, 1, 0)),
        ("right", (1, 0, 0), (0, 1, 0)),
        ("top", (0, 1, 0), (0, 0, -1)),
        ("bottom", (0, -1, 0), (0, 0, 1)),
    )
    colors = np.array(((141, 211, 199), (251, 128, 114)), dtype=np.uint8)
    plotter = pv.Plotter(off_screen=True, notebook=False, window_size=(512, 512))
    records = []
    renderer = {}
    try:
        plotter.disable_anti_aliasing()
        plotter.set_background("white")
        for index, center in enumerate(((-0.65, -0.25, 0), (0.65, 0.25, 0))):
            plotter.add_mesh(
                pv.Cube(center=center, x_length=0.9, y_length=0.9, z_length=0.9),
                color=tuple(colors[index].astype(float) / 255),
                lighting=False,
                show_edges=False,
                smooth_shading=False,
            )
        with tempfile.TemporaryDirectory(prefix="diaggen-display-probe-") as temp_dir:
            for name, direction, up in views:
                plotter.camera_position = (
                    tuple(6 * np.array(direction, dtype=float)),
                    (0, 0, 0),
                    up,
                )
                plotter.reset_camera_clipping_range()
                plotter.render()
                path = Path(temp_dir) / f"mesh_combined_part_labels_{name}.png"
                image = plotter.screenshot(str(path))
                if image.shape != (512, 512, 3):
                    raise RuntimeError(f"{name}: unexpected screenshot shape {image.shape}")
                colored = int(np.count_nonzero(np.any(image != 255, axis=2)))
                if colored < 100 or not path.is_file() or path.stat().st_size == 0:
                    raise RuntimeError(f"{name}: blank or missing screenshot")
                visible_colors = [
                    index for index, color in enumerate(colors)
                    if np.any(np.all(np.abs(image.astype(int) - color.astype(int)) <= 2, axis=2))
                ]
                if not visible_colors:
                    raise RuntimeError(f"{name}: test part colors were not rendered")
                records.append({
                    "view": name,
                    "width": 512,
                    "height": 512,
                    "nonwhite_pixels": colored,
                    "visible_test_parts": visible_colors,
                })
            capabilities = plotter.ren_win.ReportCapabilities()
            for line in capabilities.splitlines():
                for prefix, key in (
                    ("OpenGL vendor string:", "vendor"),
                    ("OpenGL renderer string:", "renderer"),
                    ("OpenGL version string:", "version"),
                ):
                    if line.startswith(prefix):
                        renderer[key] = line[len(prefix):].strip()
            renderer_name = renderer.get("renderer", "").lower()
            if not any(value in renderer_name for value in ("llvmpipe", "softpipe", "swrast", "software")):
                raise RuntimeError(f"CPU renderer not confirmed: {renderer}")
            if {i for record in records for i in record["visible_test_parts"]} != {0, 1}:
                raise RuntimeError("The six views did not show both test parts")
    finally:
        plotter.close()
    return {
        "ok": True,
        "kind": "cpu_display_preflight",
        "geometry": "two_test_cubes",
        "native_asset_stage_validated": False,
        "display": display,
        "pyvista_version": pv.__version__,
        "renderer": renderer,
        "views": records,
        "screenshots_retained": False,
    }


if __name__ == "__main__":
    try:
        result = check_display()
    except Exception as exc:
        print(json.dumps({"ok": False, "kind": "cpu_display_preflight", "error": str(exc)}))
        sys.exit(1)
    print(json.dumps(result, sort_keys=True))

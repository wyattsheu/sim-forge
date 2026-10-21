#!/usr/bin/env python3
"""CPU preflight for the actual float32 EXR mask serialization contract."""
import json
import os
from pathlib import Path
import tempfile

os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"

import cv2
import numpy as np


def main():
    labels = np.array([[0, 1, 2], [3, 5, 6]], dtype=np.float32)
    mask = np.repeat(labels[:, :, None], 3, axis=-1)
    with tempfile.TemporaryDirectory(prefix="diaggen-exr-") as directory:
        path = Path(directory) / "mask.exr"
        if not cv2.imwrite(str(path), mask):
            raise RuntimeError("Required EXR mask writer returned false")
        decoded = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if decoded is None or decoded.dtype != np.float32 or not np.array_equal(decoded, mask):
            raise RuntimeError("Required float32 EXR mask did not round-trip exactly")
    print(json.dumps({"exr_float32_roundtrip": True, "opencv_version": cv2.__version__}))


if __name__ == "__main__":
    main()

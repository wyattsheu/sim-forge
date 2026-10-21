#!/usr/bin/env python3
"""Wait for free memory on one already selected GPU; never reserve or launch work.

This deterministic guard only queries nvidia-smi. A successful observation does
not reserve memory, and another process can allocate memory immediately after it.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import re
import subprocess
import time


GPU_UUID = re.compile(r"GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z")
MAX_POLL_SECONDS = 15


def validate_gpu_uuid(value):
    if not isinstance(value, str) or not GPU_UUID.fullmatch(value):
        raise ValueError("Exactly one full GPU UUID is required")
    return value


def validate_minimum(value):
    if type(value) is not int or value <= 0:
        raise ValueError("minimum-free-mib must be a positive integer")
    return value


def validate_poll(value):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not 0 < value <= MAX_POLL_SECONDS):
        raise ValueError("poll-seconds must be greater than 0 and at most 15")
    return value


def query_gpu_csv(gpu_uuid):
    validate_gpu_uuid(gpu_uuid)
    return subprocess.run(
        ["nvidia-smi", "--id", gpu_uuid, "--query-gpu=uuid,memory.free",
         "--format=csv,noheader,nounits"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout


def parse_free_mib(value, gpu_uuid):
    validate_gpu_uuid(gpu_uuid)
    if not isinstance(value, str):
        raise ValueError("GPU probe response must be text")
    rows = list(csv.reader(io.StringIO(value), strict=True))
    if len(rows) != 1 or len(rows[0]) != 2:
        raise ValueError("GPU probe must return exactly one two-column record")
    returned_uuid, free_mib = (column.strip() for column in rows[0])
    if returned_uuid != gpu_uuid:
        raise ValueError("GPU probe returned a different UUID")
    if not re.fullmatch(r"[0-9]+", free_mib):
        raise ValueError("GPU free memory is unavailable or invalid")
    return int(free_mib)


def emit_json(record):
    print(json.dumps(record, sort_keys=True), flush=True)


def wait_for_memory(gpu_uuid, minimum_free_mib, poll_seconds=15,
                    *, query=None, sleep=None, emit=None):
    """Return zero only after the exact selected GPU reports enough free MiB."""
    validate_gpu_uuid(gpu_uuid)
    validate_minimum(minimum_free_mib)
    validate_poll(poll_seconds)
    query = query_gpu_csv if query is None else query
    sleep = time.sleep if sleep is None else sleep
    emit = emit_json if emit is None else emit
    base = {"event": "gpu_memory_guard", "gpu_uuid": gpu_uuid,
            "minimum_free_mib": minimum_free_mib, "memory_reserved": False}
    while True:
        try:
            free_mib = parse_free_mib(query(gpu_uuid), gpu_uuid)
        except (OSError, subprocess.SubprocessError, ValueError, csv.Error) as error:
            emit(dict(base, status="probe_failed", error=str(error)))
            return 1
        ready = free_mib >= minimum_free_mib
        emit(dict(base, status="ready" if ready else "waiting", free_mib=free_mib))
        if ready:
            return 0
        sleep(poll_seconds)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu-uuid", default=os.environ.get("CUDA_VISIBLE_DEVICES"),
                        help="One full GPU UUID; defaults to CUDA_VISIBLE_DEVICES")
    parser.add_argument("--minimum-free-mib", type=int, required=True)
    parser.add_argument("--poll-seconds", type=float, default=15)
    args = parser.parse_args(argv)
    try:
        validate_gpu_uuid(args.gpu_uuid)
        validate_minimum(args.minimum_free_mib)
        validate_poll(args.poll_seconds)
    except ValueError as error:
        parser.error(str(error))
    return wait_for_memory(args.gpu_uuid, args.minimum_free_mib, args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())

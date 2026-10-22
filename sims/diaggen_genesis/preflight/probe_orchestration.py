#!/usr/bin/env python3
"""Collect the real CPU orchestration regression suites in native hag4r Python.

This executes deterministic tests only, never a pipeline or hardware probe.
Every discovered test is required: skips, expected failures, and unexpected
successes are recorded separately and cannot produce a passing certificate.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import unittest


WORKSPACE = Path(__file__).resolve().parents[3]
BASE = WORKSPACE / "sims/diaggen_genesis"
NATIVE = WORKSPACE / "tools/diaggen"
PYTHON = NATIVE / ".conda/hag4r/bin/python"
SCHEMA = "diaggen-orchestration-preflight-v1"
GROUPS = (
    ("namespace_unittest_suite", BASE / "tests", "test_*.py"),
    ("preflight_negative_controls", BASE / "preflight", "test_preflight_*.py"),
)
OUTCOMES = ("pass", "fail", "error", "skip", "expected_fail", "unexpected_success")


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fresh_output(value):
    permitted = (NATIVE / "outputs/preflight").resolve()
    output = Path(value).expanduser().resolve()
    if output == permitted or not output.is_relative_to(permitted) or output.exists():
        raise ValueError("--output-dir must be a nonexistent child of tools/diaggen/outputs/preflight")
    return output


def inventory():
    tests = {path for _, directory, pattern in GROUPS for path in directory.glob(pattern)}
    sources = set()
    for directory, patterns in (
        (BASE / "queue", ("*.py", "*.sh")),
        (BASE / "preflight", ("*.py",)),
        (WORKSPACE / "tools/diaggen_support", ("*.py", "*.sh", "*.patch", "*.json", "*.js", "*.md")),
    ):
        for pattern in patterns:
            sources.update(directory.glob(pattern))
    for directory in (NATIVE / "hag4r", NATIVE / "scripts"):
        sources.update(directory.rglob("*.py"))
    sources.update(WORKSPACE / "tools" / name for name in (
        "check_diaggen_exr.py", "check_diaggen_display.py", "wait_diaggen_gpu_memory.py",
    ))
    sources.difference_update(tests)
    sources.add(WORKSPACE / 'diaggen')
    sources.update(BASE / 'queue' / name for name in ('repair_prompt.md', 'repair_result.schema.json'))
    sources.update((BASE / 'queue/systemd').glob('*.in'))

    def records(paths):
        return {str(path.relative_to(WORKSPACE)): {"sha256": file_hash(path), "size_bytes": path.stat().st_size}
                for path in sorted(paths)}

    result = {"sources": records(sources), "tests": records(tests)}
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    result["inventory_sha256"] = hashlib.sha256(encoded).hexdigest()
    return result


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executed_test_ids = []
        self.outcomes = []

    def startTest(self, test):
        self.executed_test_ids.append(test.id())
        super().startTest(test)

    def record(self, test, status, detail=None):
        item = {"test_id": test.id(), "status": status}
        if detail is not None:
            item["detail"] = detail
        self.outcomes.append(item)

    def addSuccess(self, test):
        super().addSuccess(test)
        self.record(test, "pass")

    def addFailure(self, test, error):
        super().addFailure(test, error)
        self.record(test, "fail", self._exc_info_to_string(error, test))

    def addError(self, test, error):
        super().addError(test, error)
        self.record(test, "error", self._exc_info_to_string(error, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.record(test, "skip", reason)

    def addExpectedFailure(self, test, error):
        super().addExpectedFailure(test, error)
        self.record(test, "expected_fail", self._exc_info_to_string(error, test))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.record(test, "unexpected_success")

    def addSubTest(self, test, subtest, error):
        super().addSubTest(test, subtest, error)
        if error is not None:
            status = "fail" if issubclass(error[0], test.failureException) else "error"
            self.record(subtest, status, self._exc_info_to_string(error, test))


@contextlib.contextmanager
def captured_log(path):
    """Capture test stdout/stderr, including native writes to process FDs."""
    sys.stdout.flush()
    sys.stderr.flush()
    saved = os.dup(1), os.dup(2)
    try:
        with path.open("w", encoding="utf-8", buffering=1) as log:
            os.dup2(log.fileno(), 1)
            os.dup2(log.fileno(), 2)
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                yield log
            log.flush()
    finally:
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        os.close(saved[0])
        os.close(saved[1])


def collect(output):
    if Path(sys.executable).resolve() != PYTHON.resolve():
        raise ValueError("Collection requires the local hag4r Python")
    if os.environ.get("PYTHONNOUSERSITE") != "1" or os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        raise ValueError("Collection requires isolated Python and disabled bytecode")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise ValueError("Collection requires CUDA_VISIBLE_DEVICES to be empty")
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {
        "schema_version": SCHEMA, "cpu_only": True, "overall_status": "fail",
        "started_at": datetime.now(timezone.utc).isoformat(), "python": str(PYTHON),
        "python_version": sys.version, "output_directory": str(output),
        "test_log": str(output / "test.log"), "groups": [], "checks": [],
        "required_test_policy": "Every discovered test must succeed; skips and expected failures are not passes.",
        "counts": {"run": 0, **{status: 0 for status in OUTCOMES}}, "test_ids": [],
    }
    with captured_log(output / "test.log") as log:
        try:
            before = inventory()
            report["source_inventory"] = before
            for name, directory, pattern in GROUPS:
                print(f"\nCollecting {name}: {directory} / {pattern}", file=log)
                loader = unittest.TestLoader()
                suite = loader.discover(str(directory), pattern=pattern)
                discovered_ids = [test.id() for test in flatten(suite)]
                result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=RecordedResult).run(suite)
                counts = {"run": result.testsRun, **{
                    status: sum(item["status"] == status for item in result.outcomes) for status in OUTCOMES}}
                passed = (bool(discovered_ids) and result.testsRun == len(discovered_ids)
                          and result.executed_test_ids == discovered_ids
                          and counts["pass"] == counts["run"]
                          and not any(counts[status] for status in OUTCOMES if status != "pass"))
                group = {"name": name, "directory": str(directory), "pattern": pattern,
                         "overall_status": "pass" if passed else "fail", "counts": counts,
                         "discovered_test_ids": discovered_ids, "test_ids": result.executed_test_ids,
                         "outcomes": result.outcomes, "discovery_errors": loader.errors}
                report["groups"].append(group)
                report["checks"].append({"name": name, "status": group["overall_status"], "detail": counts})
                report["test_ids"].extend(result.executed_test_ids)
                for key, value in counts.items():
                    report["counts"][key] += value
            after = inventory()
            unchanged = after == before
            report["source_inventory_unchanged"] = unchanged
            if not unchanged:
                report["source_inventory_after"] = after
            report["checks"].append({"name": "source_and_test_inventory_unchanged",
                                     "status": "pass" if unchanged else "fail"})
            report["overall_status"] = "pass" if all(item["status"] == "pass" for item in report["checks"]) else "fail"
        except BaseException as error:
            traceback.print_exc(file=log)
            report["collector_error"] = f"{type(error).__name__}: {error}"
            report["checks"].append({"name": "collector_completed", "status": "fail", "detail": report["collector_error"]})
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report["test_log_sha256"] = file_hash(output / "test.log")
    temporary = output / ".report.json.tmp"
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output / "report.json")
    print(json.dumps({"overall_status": report["overall_status"], "counts": report["counts"],
                      "report": str(output / "report.json"), "test_log": report["test_log"]}, sort_keys=True))
    return 0 if report["overall_status"] == "pass" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--collect-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        output = fresh_output(args.output_dir)
        if args.collect_worker:
            return collect(output)
        if not PYTHON.is_file():
            raise FileNotFoundError(f"Native hag4r Python is absent: {PYTHON}")
        environment = dict(os.environ, PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1",
                           CUDA_VISIBLE_DEVICES="", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        command = [str(PYTHON), str(Path(__file__).resolve()), "--output-dir", str(output), "--collect-worker"]
        return subprocess.run(command, cwd=WORKSPACE, env=environment, check=False).returncode
    except Exception as error:
        parser.error(f"{type(error).__name__}: {error}")


if __name__ == "__main__":
    raise SystemExit(main())

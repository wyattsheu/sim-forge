#!/usr/bin/env python3
"""Collect existing deterministic smoke reports; never execute pipeline stages."""
import argparse
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

WORKSPACE = Path(__file__).resolve().parents[3]


def summarize(audit_root, component_dirs):
    audit_root = Path(audit_root).resolve()
    audit_root.relative_to((WORKSPACE / "tools/diaggen/outputs/preflight").resolve())
    checks, optional, components = [], [], []
    for name, relative in component_dirs.items():
        path = audit_root / relative / "report.json"
        report = json.loads(path.read_text())
        source_checks = report.get("checks")
        if not isinstance(source_checks, list) or not source_checks:
            raise ValueError(f"No actual checks recorded for {name}")
        component_checks = []
        for check in source_checks:
            item = {"name": f"{name}/{check['name']}", "status": str(check["status"]).lower()}
            if item["status"] not in {"pass", "fail", "skip"}:
                raise ValueError("Unknown check status")
            if name == "host" and check["name"] == "optional_cmake":
                optional.append({**item, "reason": "Not required by the installed precompiled runtime or validated Ninja JIT"})
                continue
            checks.append(item)
            component_checks.append(item)
        components.append({"name": name, "report": str(path), "checks": component_checks})
    ready = bool(checks) and all(check["status"] == "pass" for check in checks)
    return {
        "schema_version": "diaggen-full-runtime-preflight-v1",
        "checked_at": datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
        "overall_status": "pass" if ready else "fail",
        "simulator": "Genesis", "checks": checks, "optional_checks": optional,
        "counts": {status: sum(check["status"] == status for check in checks) for status in ("pass", "fail", "skip")},
        "components": components,
        "scope": "Dependency and infrastructure smoke tests; synthetic fixtures are not generated production assets",
        "limitations": [
            "No complete nine-object generation or full-model peak VRAM measurement",
            "Texture kernels and exact binding tested; complete production texture rebake not claimed",
            "Final physical export contract and missing-appearance rejection tested; full appearance bundle export not claimed",
            "Model/imagegen access uses recorded successful executions; no new cloud image-generation call",
            "GPU availability is checked separately and does not reserve memory",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-root", type=Path, required=True)
    parser.add_argument("--mesh-dir", default="mesh_verified")
    parser.add_argument("--omnipart-dir", default="omnipart_verified")
    parser.add_argument("--genesis-dir", default="genesis_verified")
    args = parser.parse_args()
    result = summarize(args.audit_root, {"host": "host", "mesh": args.mesh_dir,
                                        "omnipart": args.omnipart_dir, "genesis": args.genesis_dir})
    output = args.audit_root / "summary.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"overall_status": result["overall_status"], "counts": result["counts"], "report": str(output)}))
    return 0 if result["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

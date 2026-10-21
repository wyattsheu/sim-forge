#!/usr/bin/env python3
"""Publish a small, allowlisted DiagGen progress view from an isolated worktree.

The pipeline owns its ledgers. This observer never changes them, starts GPU work,
or publishes raw ledgers, agent logs, ownership leases, or execution credentials.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from datetime import datetime
from zoneinfo import ZoneInfo


BRANCH = "diaggen-genesis-progress"
PROGRESS = Path("sims/diaggen_genesis/progress")
STAGES = (
    "image_cleanup", "sam3_omnipart_2d_segmentation", "omnipart_generate_parts",
    "hag4r_gpt_staged_material_inference", "hag4r_assign_params_to_prims",
    "hag4r_combined_to_monolithic", "genesis_live_diagnostic_loop",
    "hag4r_post_mesh_texture", "hag4r_final_export_bundle",
)
STAGE_LABELS = (
    "圖片清理", "SAM3 分割", "OmniPart 幾何生成", "材料推估", "材料參數配置",
    "體積網格處理", "Genesis 物理診斷", "貼圖生成", "最終匯出",
)
PHASE_LABELS = {
    "waiting_input": "等待輸入圖片", "waiting_gpu": "等待空閒 GPU",
    "running": "執行中", "success": "完成", "failed": "執行失敗",
    "blocked": "前置檢查未通過", "cancelled": "已取消", "stopped": "已停止",
    "unknown": "狀態未知",
}
STAGE_STATUSES = frozenset({
    "pending", "pending_retry", "retryable", "running", "success", "failed", "halted",
})
RUN_STATUSES = frozenset({"seeded", "running", "success", "failed"})
JOB_STATUSES = frozenset({"queued", "running", "success", "failed", "cancelled"})
PREVIEW_KEYS = (
    "cleaned_image_path", "processed_white_bg_png_path", "processed_rgba_path",
    "ordered_mask_vis_path", "segmentation_overlay_path", "albedo_path",
)
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_MEDIA_BYTES = 50 * 1024 * 1024
MAX_LEDGER_BYTES = 64 * 1024 * 1024
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
MODEL_NAMES = frozenset({"gpt-6-luna", "gpt-5.6-luna"})


def now():
    return datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")


def inside(path, parent):
    return path == parent or parent in path.parents


def read_object(path):
    if path.stat().st_size > MAX_LEDGER_BYTES:
        raise ValueError("ledger exceeds size limit")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("ledger must be a JSON object")
    return value


def enum(value, choices, fallback="unknown"):
    return value if isinstance(value, str) and value in choices else fallback


def identifier(value):
    return value if isinstance(value, str) and IDENTIFIER.fullmatch(value) else None


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def object_value(value):
    return value if isinstance(value, dict) else {}


def semantic_signature(snapshot):
    # Timestamps are observations, not progress. A heartbeat must not create a commit.
    def semantic(value):
        if isinstance(value, dict):
            return {key: semantic(item) for key, item in value.items()
                    if key not in {"updated_at", "created_at", "started_at", "finished_at", "signature"}}
        if isinstance(value, list):
            return [semantic(item) for item in value]
        return value
    return hashlib.sha256(json.dumps(semantic(snapshot), sort_keys=True,
                                     ensure_ascii=False).encode()).hexdigest()


def media_candidates(state):
    paths = object_value(state.get("paths"))
    for key in PREVIEW_KEYS:
        if isinstance(paths.get(key), str):
            yield key.removesuffix("_path"), paths[key], {".png", ".jpg", ".jpeg"}
    directory = paths.get("omnipart_output_dir")
    if isinstance(directory, str):
        for view in ("top", "bottom", "front", "back", "left", "right"):
            yield f"omnipart_{view}", str(Path(directory) / f"mesh_combined_part_labels_{view}.png"), {".png"}
    diagnostics = object_value(state.get("diagnostics"))
    episodes = diagnostics.get("episodes", [])
    if isinstance(episodes, list):
        # Bound both published files and work if a ledger grows unexpectedly large.
        for index, episode in enumerate(episodes[:100]):
            episode = object_value(episode)
            for key in ("video_path", "triptych_video_path"):
                if isinstance(episode.get(key), str):
                    yield f"episode_{index + 1:03d}_{key.removesuffix('_path')}", episode[key], {".mp4"}


def collect_media(state, run_root, outputs_root, *, name_prefix="", budget=None):
    budget = MAX_MEDIA_BYTES if budget is None else min(budget, MAX_MEDIA_BYTES)
    roots = [run_root.resolve()]
    final_export = object_value(state.get("paths")).get("final_export_dir")
    if isinstance(final_export, str) and Path(final_export).is_absolute():
        resolved = Path(final_export).resolve()
        if inside(resolved, outputs_root.resolve()) and resolved != outputs_root.resolve():
            roots.append(resolved)
    files, total = [], 0
    for label, raw_path, suffixes in media_candidates(state):
        try:
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                continue
            candidate = candidate.resolve(strict=True)
            if not any(inside(candidate, root) for root in roots):
                continue
            if not candidate.is_file() or candidate.suffix.lower() not in suffixes:
                continue
            size = candidate.stat().st_size
            if not 0 < size <= MAX_FILE_BYTES or total + size > budget:
                continue
            with candidate.open("rb") as stream:
                data = stream.read(MAX_FILE_BYTES + 1)
            if not data or len(data) > MAX_FILE_BYTES or total + len(data) > budget:
                continue
            suffix = candidate.suffix.lower()
            valid = (suffix == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n")) or (
                suffix in {".jpg", ".jpeg"} and data.startswith(b"\xff\xd8\xff")) or (
                suffix == ".mp4" and len(data) >= 12 and data[4:8] == b"ftyp")
            if not valid:
                continue
            name = f"media/{name_prefix}{label}{suffix}"
            files.append((name, data))
            total += len(data)
        except (OSError, RuntimeError, ValueError):
            continue
    return files


def build_run_snapshot(workspace, queued, *, media_prefix="", media_budget=None):
    run_id = identifier(queued.get("run_id"))
    if not run_id or run_id in {".", ".."}:
        raise ValueError("invalid queue run identifier")
    outputs = (workspace / "tools/diaggen/outputs").resolve()
    run_root = (outputs / "agentic_asset_refinement" / run_id).resolve()
    if not inside(run_root, outputs):
        raise ValueError("run root escapes outputs")
    ledger = run_root / "state.json"
    if ledger.exists() and not inside(ledger.resolve(), run_root):
        raise ValueError("runtime ledger escapes run root")
    state = read_object(ledger) if ledger.exists() else {}
    if state and state.get("run_id") != run_id:
        raise ValueError("queue and runtime run identifiers differ")
    phase = queued.get("phase")
    if phase == "confirming_gpu":
        phase = "waiting_gpu"
    phase = enum(phase, PHASE_LABELS)
    diagnostics = object_value(state.get("diagnostics"))
    terminal = object_value(diagnostics.get("terminal"))
    snapshot = {
        "schema_version": "diaggen-public-progress-v1",
        "pipeline": "DiagGen", "simulator": "Genesis", "run_id": run_id,
        "phase": phase, "pipeline_status": enum(state.get("status"), RUN_STATUSES, "not_initialized"),
        "generation_and_diagnostics_model": enum(queued.get("generation_and_diagnostics_model"), MODEL_NAMES),
        "reasoning_effort": enum(queued.get("reasoning_effort"), {"max"}),
        "active_revision": identifier(state.get("active_revision")),
        "created_at": timestamp(state.get("created_at")), "updated_at": now(),
        "diagnostics": {
            "enabled": diagnostics.get("enabled") if isinstance(diagnostics.get("enabled"), bool) else None,
            "episode_count": len(diagnostics["episodes"]) if isinstance(diagnostics.get("episodes"), list) else 0,
            "terminal_status": enum(terminal.get("status"), {"success", "failed", "retryable", "halted", "pending"}, "not_available"),
        },
        "stages": [],
    }
    stages = object_value(state.get("stages"))
    for name, label in zip(STAGES, STAGE_LABELS):
        stage = object_value(stages.get(name))
        ledger_status = enum(stage.get("status"), STAGE_STATUSES, "pending")
        started = timestamp(stage.get("started_at"))
        effective = "running" if ledger_status == "pending" and started and stage.get("ok") is not True else ledger_status
        snapshot["stages"].append({
            "name": name, "label": label, "status": effective, "ledger_status": ledger_status,
            "ok": stage.get("ok") is True, "started_at": started,
            "finished_at": timestamp(stage.get("finished_at")),
        })
    media = collect_media(state, run_root, outputs, name_prefix=media_prefix, budget=media_budget)
    snapshot["media"] = [{"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                         for name, data in media]
    snapshot["signature"] = semantic_signature(snapshot)
    return snapshot, media


def bounded_integer(value, lower, upper):
    return value if isinstance(value, int) and not isinstance(value, bool) and lower <= value <= upper else None


def build_batch_snapshot(workspace, queued, batch):
    if batch.get("schema_version") != "diaggen-batch-v1":
        raise ValueError("unsupported batch schema")
    jobs = batch.get("jobs")
    if not isinstance(jobs, list) or not 1 <= len(jobs) <= 100:
        raise ValueError("batch must contain between one and 100 jobs")
    source_policy = object_value(batch.get("policy"))
    policy = {
        "minimum_free_mib": bounded_integer(source_policy.get("minimum_free_mib"), 1, 1024 * 1024),
        "allow_compute_sharing": source_policy.get("allow_compute_sharing")
        if isinstance(source_policy.get("allow_compute_sharing"), bool) else None,
        "check_interval_seconds": bounded_integer(source_policy.get("check_interval_seconds"), 1, 86400),
        "max_parallel_jobs": bounded_integer(source_policy.get("max_parallel_jobs"), 1, 64),
    }
    phase = queued.get("phase")
    phase = "waiting_gpu" if phase == "confirming_gpu" else enum(phase, PHASE_LABELS)
    snapshot = {
        "schema_version": "diaggen-public-batch-progress-v1",
        "pipeline": "DiagGen", "simulator": "Genesis", "phase": phase,
        "generation_and_diagnostics_model": enum(queued.get("generation_and_diagnostics_model"), MODEL_NAMES),
        "reasoning_effort": enum(queued.get("reasoning_effort"), {"max"}),
        "updated_at": now(), "policy": policy,
        "counts": {status: 0 for status in ("queued", "running", "success", "failed", "cancelled", "unknown")},
        "jobs": [], "media": [],
    }
    queue = workspace / "sims/diaggen_genesis/queue"
    media, seen_ids, seen_run_ids, seen_prefixes = [], set(), set(), set()
    remaining = MAX_MEDIA_BYTES
    for job in jobs:
        job = object_value(job)
        job_id, run_id = identifier(job.get("id")), identifier(job.get("run_id"))
        if not job_id or job_id in {".", ".."} or not run_id or run_id in {".", ".."}:
            raise ValueError("invalid batch job identifier")
        prefix = re.sub(r"[^a-z0-9_]", "_", job_id.lower()) + "_"
        if job_id in seen_ids or run_id in seen_run_ids or prefix in seen_prefixes:
            raise ValueError("batch jobs require unique identifiers and media prefixes")
        seen_ids.add(job_id)
        seen_run_ids.add(run_id)
        seen_prefixes.add(prefix)
        status = enum(job.get("status"), JOB_STATUSES)
        snapshot["counts"][status] += 1
        status_path = queue / "jobs" / job_id / "status.json"
        if status_path.exists() and not inside(status_path.resolve(), queue.resolve()):
            raise ValueError("job status escapes queue")
        observed = read_object(status_path) if status_path.exists() else {}
        if observed.get("run_id") not in {None, run_id}:
            raise ValueError("batch and job status run identifiers differ")
        job_phase = observed.get("phase")
        if status in {"success", "failed", "cancelled"}:
            job_phase = status
        elif job_phase not in PHASE_LABELS and job_phase != "confirming_gpu":
            job_phase = "waiting_gpu" if status == "queued" else enum(status, PHASE_LABELS)
        job_queue = {
            "run_id": run_id, "phase": job_phase,
            "generation_and_diagnostics_model": observed.get("generation_and_diagnostics_model", queued.get("generation_and_diagnostics_model")),
            "reasoning_effort": observed.get("reasoning_effort", queued.get("reasoning_effort")),
        }
        progress, files = build_run_snapshot(workspace, job_queue, media_prefix=prefix, media_budget=remaining)
        remaining -= sum(len(data) for _, data in files)
        media.extend(files)
        progress.pop("signature", None)
        progress.update(id=job_id, status=status,
                        attempts=bounded_integer(job.get("attempts"), 0, 1000000))
        minimums = [value for value in (
            policy["minimum_free_mib"],
            bounded_integer(job.get("minimum_free_mib"), 1, 1024 * 1024),
        ) if value is not None]
        progress["minimum_free_mib"] = max(minimums) if minimums else None
        snapshot["jobs"].append(progress)
        snapshot["media"].extend(progress["media"])
    snapshot["counts"]["total"] = len(snapshot["jobs"])
    snapshot["signature"] = semantic_signature(snapshot)
    return snapshot, media


def build_snapshot(workspace):
    queue = workspace / "sims/diaggen_genesis/queue"
    queued = read_object(queue / "status.json")
    batch_path = queue / "batch.json"
    if batch_path.exists():
        if not inside(batch_path.resolve(), queue.resolve()):
            raise ValueError("batch ledger escapes queue")
        return build_batch_snapshot(workspace, queued, read_object(batch_path))
    return build_run_snapshot(workspace, queued)


def render_batch_readme(snapshot):
    policy, counts = snapshot["policy"], snapshot["counts"]
    lines = ["# DiagGen / Genesis 批次執行進度", "",
             f"狀態：**{PHASE_LABELS[snapshot['phase']]}**  ",
             f"模型：`{snapshot['generation_and_diagnostics_model']}`，reasoning `{snapshot['reasoning_effort']}`  ",
             f"更新：{snapshot['updated_at']}（Asia/Taipei）", "",
             f"共 {counts['total']} 件：等待 {counts['queued']}、執行中 {counts['running']}、完成 {counts['success']}、失敗 {counts['failed']}、取消 {counts['cancelled']}。", "",
             f"GPU 可用記憶體門檻：{policy['minimum_free_mib']} MiB；最多同時 {policy['max_parallel_jobs']} 件；排程每 {policy['check_interval_seconds']} 秒檢查。  ",
             f"允許與既有運算共用 GPU：{'是' if policy['allow_compute_sharing'] is True else '否' if policy['allow_compute_sharing'] is False else '未知'}。", "",
             "只在排程狀態、階段、revision 或預覽成果改變時更新。等待期間不重複提交。", "",
             "| 物件 | 排程狀態 | Runtime | Revision | 顯存門檻 | 已完成階段 |", "|---|---|---|---|---|---|"]
    for job in snapshot["jobs"]:
        completed = sum(stage["ok"] for stage in job["stages"])
        lines.append(f"| {job['id']} | {job['status']} | {job['pipeline_status']} | {job['active_revision'] or '尚未初始化'} | {job['minimum_free_mib']} MiB | {completed}/{len(STAGES)} |")
    for job in snapshot["jobs"]:
        lines += ["", f"## {job['id']}", "", f"Run：`{job['run_id']}`；{PHASE_LABELS[job['phase']]}。", "",
                  "| 階段 | 狀態 |", "|---|---|"]
        for stage in job["stages"]:
            lines.append(f"| {stage['label']} | {stage['status']} |")
        lines += ["", f"Genesis 診斷 episode 數：{job['diagnostics']['episode_count']}。", ""]
        for item in job["media"]:
            path = item["path"]
            lines += [f"[{Path(path).stem}]({path})" if path.endswith(".mp4") else f"![{Path(path).stem}]({path})", ""]
    lines += ["完整執行紀錄、GPU 識別資訊與失敗細節保留在伺服器。", ""]
    return "\n".join(lines)


def render_readme(snapshot):
    if "jobs" in snapshot:
        return render_batch_readme(snapshot)
    lines = ["# DiagGen / Genesis 執行進度", "",
             f"狀態：**{PHASE_LABELS[snapshot['phase']]}**", "",
             f"Run：`{snapshot['run_id']}`  ",
             f"模擬器：Genesis  ",
             f"模型：`{snapshot['generation_and_diagnostics_model']}`，reasoning `{snapshot['reasoning_effort']}`  ",
             f"Runtime：`{snapshot['pipeline_status']}`  ",
             f"Revision：`{snapshot['active_revision'] or '尚未初始化'}`  ",
             f"更新：{snapshot['updated_at']}（Asia/Taipei）", "",
             "只在排程狀態、階段、revision 或預覽成果改變時更新。等待期間不重複提交。", "",
             "| 階段 | 狀態 |", "|---|---|"]
    for stage in snapshot["stages"]:
        lines.append(f"| {stage['label']} | {stage['status']} |")
    lines += ["", f"Genesis 診斷 episode 數：{snapshot['diagnostics']['episode_count']}。",
              "", "失敗細節與完整執行紀錄保留在伺服器。", ""]
    for media in snapshot["media"]:
        path = media["path"]
        lines.append(f"[{Path(path).stem}]({path})" if path.endswith(".mp4") else f"![{Path(path).stem}]({path})")
        lines.append("")
    return "\n".join(lines)


def git(worktree, *arguments, check=True, input_text=None):
    # Every Git operation is explicitly bound to the isolated worktree.
    result = subprocess.run(["git", "-C", str(worktree), *arguments],
                            input=input_text, text=True, capture_output=True, timeout=60,
                            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if check and result.returncode:
        # Git errors may include credential-bearing remote URLs. Keep public/log errors generic.
        raise RuntimeError(f"git {arguments[0]} failed (exit {result.returncode})")
    return result


def allowed_output(path):
    return path in {str(PROGRESS / "README.md"), str(PROGRESS / "status.json")} or bool(
        re.fullmatch(re.escape(str(PROGRESS)) + r"/media/[a-z0-9_]+\.(png|jpg|jpeg|mp4)", path))


def validate_worktree(worktree):
    top = git(worktree, "rev-parse", "--show-toplevel").stdout.strip()
    if Path(top).resolve() != worktree.resolve():
        raise ValueError("publisher requires the dedicated worktree root")
    if git(worktree, "branch", "--show-current").stdout.strip() != BRANCH:
        raise ValueError("publisher requires its dedicated progress branch")
    staged = git(worktree, "diff", "--cached", "--name-only", "-z").stdout.split("\0")
    if any(path and not allowed_output(path) for path in staged):
        raise ValueError("unrelated staged files found in publishing worktree")


def write_snapshot(worktree, snapshot, media):
    destination = worktree / PROGRESS
    if not inside(destination.resolve(), worktree.resolve()):
        raise ValueError("progress directory escapes worktree")
    destination.mkdir(parents=True, exist_ok=True)
    media_dir = destination / "media"
    if media_dir.is_symlink():
        raise ValueError("media destination must not be a symlink")
    media_dir.mkdir(exist_ok=True)
    expected = {name for name, _ in media}
    changed = [str(PROGRESS / "README.md"), str(PROGRESS / "status.json")]
    for old in media_dir.iterdir():
        relative = old.relative_to(destination).as_posix()
        repo_path = str(PROGRESS / relative)
        if allowed_output(repo_path) and relative not in expected:
            old.unlink()
            changed.append(repo_path)
    contents = [("README.md", render_readme(snapshot).encode()),
                ("status.json", (json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode()), *media]
    for name, data in contents:
        target = destination / name
        if target.is_symlink():
            raise ValueError("output file must not be a symlink")
        descriptor, temporary_name = tempfile.mkstemp(prefix=".publisher-", dir=target.parent)
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        temporary.replace(target)
        changed.append(str(PROGRESS / name))
    return list(dict.fromkeys(changed))


def sync_once(workspace, worktree, dry_run=False):
    snapshot, media = build_snapshot(workspace)
    if not dry_run:
        validate_worktree(worktree)
    old_path = worktree / PROGRESS / "status.json"
    old = read_object(old_path) if old_path.exists() else {}
    changed = snapshot["signature"] != old.get("signature")
    if changed:
        write_snapshot(worktree, snapshot, media)
    if dry_run:
        return {"changed": changed, "pushed": False, "phase": snapshot["phase"]}
    # Reconcile exact managed paths on every invocation, including recovery after
    # a crash between writing, staging, and committing. Never stage arbitrary files.
    files = [str(PROGRESS / "README.md"), str(PROGRESS / "status.json")]
    files += [str(PROGRESS / item["path"]) for item in snapshot["media"]]
    tracked = git(worktree, "ls-files", "-z", "--", str(PROGRESS)).stdout.split("\0")
    files += [path for path in tracked if path and allowed_output(path)]
    files = [path for path in dict.fromkeys(files) if (worktree / path).exists() or path in tracked]
    if files:
        git(worktree, "add", "--", *files)
    staged = git(worktree, "diff", "--cached", "--name-only", "-z").stdout.split("\0")
    if any(path for path in staged):
        if any(path and not allowed_output(path) for path in staged):
            raise ValueError("refusing unrelated staged files")
        git(worktree, "commit", "--cleanup=verbatim", "--file=-", input_text="Update DiagGen Genesis progress\n")
    head = git(worktree, "rev-parse", "HEAD").stdout.strip()
    remote = git(worktree, "rev-parse", "--verify", f"refs/remotes/origin/{BRANCH}", check=False)
    pushed = remote.returncode != 0 or remote.stdout.strip() != head
    if pushed:
        latest_message = git(worktree, "log", "-1", "--format=%B").stdout
        if re.search(r"co-authored-by|coworker", latest_message, flags=re.I):
            raise ValueError("commit contains a forbidden attribution")
        # Always retry an outstanding local commit even if the snapshot is unchanged.
        git(worktree, "push", "origin", f"HEAD:refs/heads/{BRANCH}")
    return {"changed": changed, "pushed": pushed, "phase": snapshot["phase"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--once", action="store_true")
    modes.add_argument("--watch", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="write the sanitized snapshot without Git operations")
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--worktree", type=Path)
    parser.add_argument("--interval", type=float, default=60)
    arguments = parser.parse_args()
    workspace = arguments.workspace.resolve()
    queue = workspace / "sims/diaggen_genesis/queue"
    worktree = (arguments.worktree or queue / ".publish-worktree").resolve()
    logging.basicConfig(filename=queue / "publisher.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if arguments.interval < 1:
        parser.error("interval must be at least one second")
    with (queue / "publisher.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logging.info("publisher already running")
            return 1
        while True:
            try:
                result = sync_once(workspace, worktree, arguments.dry_run)
                if result["changed"] or result["pushed"]:
                    logging.info("sync phase=%s changed=%s pushed=%s", result["phase"], result["changed"], result["pushed"])
            except Exception as error:
                # Never copy raw exception strings or tracebacks containing source payloads/URLs.
                logging.error("sync failed: %s; retry on next interval", type(error).__name__)
                if arguments.once:
                    return 1
            if arguments.once:
                return 0
            time.sleep(arguments.interval)


if __name__ == "__main__":
    raise SystemExit(main())

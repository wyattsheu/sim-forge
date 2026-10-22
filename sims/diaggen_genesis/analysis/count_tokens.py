#!/usr/bin/env python3
"""Read-only Codex model-usage accounting for one DiagGen queue attempt.

Use structured per-response records: display token_count events can omit
compaction requests. Cached input and reasoning output are subsets, not extras.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import sys


FIELDS = (
    "input_tokens", "cached_input_tokens", "cache_write_input_tokens",
    "output_tokens", "reasoning_output_tokens", "total_tokens",
)


class AccountingError(ValueError):
    """An incomplete or inconsistent source cannot produce a valid total."""


def records(path: Path):
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    item = json.loads(line)
                    if not isinstance(item, dict):
                        raise AccountingError("A source record is not an object.")
                    yield item
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AccountingError("A required source is missing, unreadable, or incomplete.") from exc


def validate_usage(value):
    if not isinstance(value, dict):
        raise AccountingError("A required usage object is missing.")
    usage = {key: value.get(key) for key in FIELDS}
    if any(type(number) is not int or number < 0 for number in usage.values()):
        raise AccountingError("Usage fields must be present, nonnegative integers.")
    if usage["input_tokens"] + usage["output_tokens"] != usage["total_tokens"]:
        raise AccountingError("Input plus output does not match total tokens.")
    if usage["cached_input_tokens"] > usage["input_tokens"]:
        raise AccountingError("Cached input exceeds input tokens.")
    if usage["reasoning_output_tokens"] > usage["output_tokens"]:
        raise AccountingError("Reasoning output exceeds output tokens.")
    return usage


def thread_usage(path: Path, thread_id: str):
    unique = {}
    final_cumulative = None
    duplicate_count = 0
    for item in records(path):
        if item.get("type") != "token_usage_record":
            continue
        payload = item.get("payload", {})
        if not isinstance(payload, dict):
            raise AccountingError("A token record has an invalid payload.")
        if payload.get("thread_id") != thread_id:
            continue
        response_id = payload.get("response_id")
        if not isinstance(response_id, str) or not response_id:
            raise AccountingError("A token record has no response identifier.")
        usage = validate_usage(payload.get("usage"))
        final_cumulative = validate_usage(payload.get("thread_token_usage"))
        key = (thread_id, response_id)
        if key in unique:
            if unique[key] != usage:
                raise AccountingError("Duplicate response records disagree about usage.")
            duplicate_count += 1
        else:
            unique[key] = usage
    if not unique:
        raise AccountingError("A required thread has no structured usage records.")
    total = {field: sum(usage[field] for usage in unique.values()) for field in FIELDS}
    validate_usage(total)
    if total != final_cumulative:
        raise AccountingError("Per-response usage does not match final thread usage.")
    return total, len(unique), duplicate_count


def safe_label(value, fallback):
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:+-]{1,100}", value):
        return value
    return fallback


def collect(events: Path, database: Path):
    started = []
    parent_completed = False
    for item in records(events):
        if item.get("type") == "thread.started":
            started.append(item.get("thread_id"))
        elif item.get("type") == "turn.completed":
            parent_completed = True
    if len(started) != 1 or not isinstance(started[0], str) or not started[0]:
        raise AccountingError("The events source must contain exactly one thread.started.")
    parent = started[0]
    try:
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            connection.execute("PRAGMA query_only = ON")
            rows = connection.execute(
                """WITH RECURSIVE family(id) AS (
                       SELECT ?
                       UNION
                       SELECT edge.child_thread_id
                       FROM thread_spawn_edges AS edge JOIN family
                         ON edge.parent_thread_id = family.id
                   )
                   SELECT family.id, threads.rollout_path, threads.model,
                          threads.agent_path, threads.agent_role
                   FROM family LEFT JOIN threads ON threads.id = family.id""",
                (parent,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise AccountingError("The read-only session database could not be queried.") from exc
    threads = []
    total = dict.fromkeys(FIELDS, 0)
    for thread_id, rollout_path, model, agent_path, agent_role in rows:
        if not rollout_path:
            raise AccountingError("A required thread has no session metadata.")
        usage, requests, duplicates = thread_usage(Path(rollout_path), thread_id)
        is_parent = thread_id == parent
        role = "parent" if is_parent else safe_label(
            agent_path.rsplit("/", 1)[-1] if isinstance(agent_path, str) else agent_role,
            "stage_agent",
        )
        threads.append({
            "role": role,
            "is_parent": is_parent,
            "model": safe_label(model, "unknown"),
            "requests": requests,
            "identical_duplicate_records_ignored": duplicates,
            "usage": usage,
            "validated_against_final_thread_usage": True,
        })
        for field in FIELDS:
            total[field] += usage[field]
    threads.sort(key=lambda thread: (not thread["is_parent"], thread["role"]))
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "One queue attempt: parent and recursively spawned descendant model requests.",
        "excludes": [
            "Earlier attempts and retries outside this parent thread family",
            "Interactive debugging outside this parent thread family",
            "Separate image-generation tool charges",
            "Local GPU computation",
        ],
        "method": "Sum unique own-thread token_usage_record.usage by (thread_id, response_id), including compaction.",
        "subset_notes": [
            "cached_input_tokens is already included in input_tokens",
            "reasoning_output_tokens is already included in output_tokens",
        ],
        "parent_turn_completed_observed": parent_completed,
        "thread_count": len(threads),
        "request_count": sum(thread["requests"] for thread in threads),
        "usage": total,
        "uncached_input_tokens": total["input_tokens"] - total["cached_input_tokens"],
        "input_cache_hit_percent": (
            round(100 * total["cached_input_tokens"] / total["input_tokens"], 6)
            if total["input_tokens"] else 0.0
        ),
        "threads": threads,
        "billing_note": "Observed model usage, not a billing invoice or subscription-quota conversion.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--database", type=Path, default=Path.home() / ".codex/state_5.sqlite")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = collect(args.events, args.database)
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
    except (AccountingError, OSError) as exc:
        message = str(exc) if isinstance(exc, AccountingError) else "The requested output could not be written."
        print(json.dumps({"error": message}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

DiagGen / Genesis batch of nine inputs

Simulator: Genesis 1.2.0 (the fork bundled with DiagGen).
Genesis diagnostics are enabled.
Generation and diagnostics: GPT-6 Luna (gpt-6-luna), max reasoning.
All stage children inherit the same model and reasoning effort.
Paper generation/diagnostics: GPT-5.6 Luna, Max; the user allowed a newer version.
The paper's separate independent evaluation judges are GPT-5.6 Terra, Max.

Static inputs/policy: batch_plan.json
Nine PNG/JPG inputs are scheduled; README.txt and ATTRIBUTION.txt are excluded.
Eight inputs are input-photo crops from the official gallery video (not original
full-resolution photos); Capybara plush toy.jpg is user supplied.
See demo_image_sources.json for provenance. demo_inputs_preview.jpg contains
only the eight official crops. references/official_cleaned/ is not a queue input.

The watcher checks every 15 seconds. It permits compute sharing whenever a GPU
has at least 24576 MiB free. It does not require low utilization or no processes.
At most one of our jobs per physical GPU and two jobs total run simultaneously.
This is an aggressive experimental threshold, not a measured OmniPart peak.
Other users' processes are never interrupted. GPU memory can change after a
check; allocation failures are recorded honestly and do not block the next job.

Each job has isolated run ID, GPU UUID, Genesis cache and logs.
Results: sims/diaggen_genesis/runs/<run_id>/
  asset/       final physical asset, material parameters, appearance and manifest
  trace/       original state, revisions and available diagnostic evidence
  input.*      frozen input used for this run
  manifest.json records simulator=Genesis, input hash and working/archive mapping

Working files remain under tools/diaggen/outputs/ as required by DiagGen.
Archived ledgers retain their original absolute working paths.
Failed jobs can contain only partial artifacts; existence of a video alone does
not indicate that the run or physical validation succeeded.

Overall state: queue/status.json
Batch ledger: queue/batch.json
Supervisor log: queue/watcher.log
Per-job status/logs: queue/jobs/<job_id>/
  status.json, launcher.log, codex_events.jsonl, codex_stderr.log, last_message.txt

Observe from workspace root:
  cat sims/diaggen_genesis/queue/status.json
  tail -f sims/diaggen_genesis/queue/watcher.log
  tmux attach -t diaggen-genesis-wait
Detach from tmux with Ctrl-b then d.

Cancel queued jobs (checked within 15 seconds):
  touch sims/diaggen_genesis/queue/STOP
Already running jobs finish normally. No failed run is automatically retried or
overwritten. tmux survives closing the chat/SSH, but not a server reboot.

To hold new launches while retaining queued jobs, create queue/HOLD. Existing
jobs continue. After a verified dependency repair, explicit retries can be
requested while HOLD exists:
  <hag4r-python> queue/batch_control.py retry <job_id> <new_run_id> <reason_enum>
Only failed jobs with an exited launcher can retry. Old queue logs move into
queue/job_history/<job_id>/<old_run_id>/ and native runs/archives stay intact.
Remove HOLD only after verifying the repair. Each launcher checks actual
float32 EXR write/read before initializing an expensive native pipeline.

2026-10-21: fixed project-local SAM3 OpenCV from 5.0.0.93 (no OpenEXR) to
4.13.0.92, matching DiagGen requirements. The native save_mask_exr function
round-tripped the actual USB Hub 518x518 mask exactly. Four failed attempts
were explicitly requeued with _exr_retry1 run IDs; no success was fabricated.

GitHub progress: branch diaggen-genesis-progress, directory
  sims/diaggen_genesis/progress/
Publisher session: diaggen-github-progress

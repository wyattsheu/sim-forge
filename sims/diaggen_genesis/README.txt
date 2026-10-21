DiagGen / Genesis queued first run

Simulator: Genesis 1.2.0 (the fork bundled with DiagGen).
Genesis diagnostics are enabled. No Isaac Sim conversion is included.

Generation and diagnostics: GPT-6 Luna (gpt-6-luna), max reasoning.
All stage children inherit the same model and reasoning effort.
The paper's corresponding setting is GPT-5.6 Luna, Max reasoning.
The user explicitly allowed a newer model version; this difference is recorded.
The paper's independent evaluation judges use GPT-5.6 Terra at Max reasoning.
Those benchmark judges are separate from this first generation/diagnostics run.

Place exactly one complete-object PNG or JPG photo in:
  sims/diaggen_genesis/inputs/
Suggested filename: object.png
Avoid placing multiple photos here for this first run.

Demo inputs have now been prepared under inputs/demo_gallery/ (8 images).
The active first input is inputs/demo_gallery/usb_hub.png, selected by
queue/input_path.txt. They are input-photo crops from the official video,
not original full-resolution photos. See demo_image_sources.json for provenance
and demo_inputs_preview.jpg for the contact sheet. An additional author
AI-cleaned sloth reference is kept separately in references/official_cleaned/.

The watcher checks every 60 seconds. It waits for an input that Pillow can read,
then for the same GPU to have no compute processes and at least 65536 MiB free
on two consecutive checks. This conservative memory threshold is not a measured
OmniPart requirement. Other users' jobs are never interrupted.

Run ID: genesis_first_20261021
Results: sims/diaggen_genesis/runs/genesis_first_20261021/
  asset/       final mesh, material parameters, textures and export manifest
  trace/       original state, revision artifacts, diagnostic images/videos
  manifest.json records simulator=Genesis, input hash and working/archive mapping

Working files remain under tools/diaggen/outputs/ as required by DiagGen.
Archived ledgers retain their original absolute working paths.

Status: queue/status.json
GPU snapshot: queue/gpu_snapshot.json
Log: queue/watcher.log
Codex events: queue/codex_events.jsonl
Final agent report: queue/last_message.txt

Observe from the workspace root:
  cat sims/diaggen_genesis/queue/status.json
  tail -f sims/diaggen_genesis/queue/watcher.log
  tmux attach -t diaggen-genesis-wait
Detach from tmux with Ctrl-b then d.

Cancel while waiting (checked within 60 seconds):
  touch sims/diaggen_genesis/queue/STOP

This is a one-shot job. It does not retry a failed model run or overwrite a prior
run. The tmux session survives closing this chat or SSH, but not a server reboot.

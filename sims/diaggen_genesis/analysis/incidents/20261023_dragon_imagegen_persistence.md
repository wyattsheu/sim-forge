# 2026-10-23 Dragon image persistence incident

## Finding

Classification: `pipeline_runtime`.

The `dragon` job's `image_cleanup` child generated an image, then could not save
the PNG candidate. Its nested writer command failed during local bubblewrap
network-namespace setup (`RTM_NEWADDR: Operation not permitted`). Retrying the
same in-memory result put base64 data in process command arguments and failed
with `Argument list too long`. No candidate PNG was persisted. The native
`image_cleanup` stage recorded a halted runtime terminal while the top-level
run remained seeded.

The monitor and repair timers were active, and a recent monitor tick completed
successfully. This was not a scheduler interruption or a physical acceptance
failure. Same-run `Queue.resume` correctly rejected the halted stage terminal;
no native state or terminal was edited.

## Change

`tools/diaggen_support/save_imagegen_result.js` now streams the retained PNG
through a non-PTY stdin session in bounded base64 lines. The local writer
validates the native candidate path and PNG bytes, then links the verified file
atomically. If the exact local bubblewrap namespace error occurs, the helper
requests review for that same writer command once. Review rejection and other
errors stop the save; the helper does not retry by placing image bytes in the
command line or generate another image.

Regression coverage in `tests/test_imagegen_result.py` checks byte-identical
large-image persistence, the one-command escalation path, rejection without a
write, and no escalation for unrelated errors.

## Checks and requeue

- Full CPU orchestration collection: 443/443 passed, including the new
  regression and negative controls.
- Full runtime preflight: 74/74 passed and the readiness certificate verified.
  Host, mesh, Genesis, and OmniPart evidence was reused only after fingerprints
  confirmed native sources, inputs, environments, and binaries were unchanged.
- The original image hash, user hints, and six-run diagnostic budget were
  preserved. The old queue logs and native state remain in place and unchanged.
- Guarded `Queue.retry` admitted
  `genesis_dragon_20261023_saverfix174003`; it was queued pending repair-worker
  readiness completion. This is a new run, not a claim of generation completion
  or physical acceptance.

No native algorithm, diagnostic acceptance condition, model, precision,
resolution, or GPU assignment was changed.

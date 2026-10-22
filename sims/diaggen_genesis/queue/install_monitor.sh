#!/usr/bin/env bash
# Install only this user's two explicitly named DiagGen units; no sudo needed.
set -euo pipefail
QUEUE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$QUEUE_DIR/../../.." && pwd)"
python3 - "$QUEUE_DIR" "$WORKSPACE" <<'PY'
import os
from pathlib import Path
import sys
queue, workspace = map(Path, sys.argv[1:])
if any(c in str(workspace) for c in ('\n', '\r', '%', '"', '\\')):
    raise SystemExit('Unsupported path for systemd units')
target = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'systemd/user'
target.mkdir(parents=True, exist_ok=True)
for name in ('service', 'timer'):
    source = queue / 'systemd' / ('diaggen-genesis-monitor.' + name + '.in')
    content = source.read_text().replace('@WORKSPACE@', str(workspace)).replace('@QUEUE@', str(queue))
    destination = target / ('diaggen-genesis-monitor.' + name)
    if destination.is_symlink():
        raise SystemExit('Refusing symlink unit')
    if destination.exists() and not destination.read_text().startswith('# Managed by sim-forge DiagGen'):
        raise SystemExit('Refusing to overwrite an unrelated unit')
    temporary = destination.with_suffix(destination.suffix + '.tmp')
    temporary.write_text(content)
    temporary.replace(destination)
PY
systemctl --user daemon-reload
systemctl --user enable --now diaggen-genesis-monitor.timer
systemctl --user start diaggen-genesis-monitor.service
systemctl --user list-timers --all diaggen-genesis-monitor.timer

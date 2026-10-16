# pve-01 Resource Overview

Runs from your Mac, SSHes into pve-01, and renders a live memory/CPU table for
all LXCs and VMs. This README covers setup and CLI usage; the
[runbook](../../docs/runbooks/pve-status.md) covers operation, how it works and example output.

## Setup

```bash
cd tools/pve/
/opt/homebrew/bin/python3 -m venv .venv
source .venv/bin/activate
python --version   # should show 3.14.*
pip install -r requirements.txt
deactivate
cd ../..
```

Requires the `~/.ssh/homelab_id` key with access to `***@*.*.*.*`.

## Usage

```bash
source tools/pve/.venv/bin/activate
python tools/pve/status.py                    # render in terminal
python tools/pve/status.py --web-dir DIR    # write DIR/public/index.html (static-site export)
python tools/pve/status.py --publish          # push HTML to the monitoring-01 status page
deactivate
```

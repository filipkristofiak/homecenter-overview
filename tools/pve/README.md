# pve-01 Resource Overview

Runs from your Mac, SSHes into pve-01, and renders a live memory/CPU table for
all LXCs and VMs. See [docs/runbooks/pve-status.md](../../docs/runbooks/pve-status.md)
for how it works, example output, and the public status page setup.

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
python tools/pve/status.py --html out.html    # also export as HTML
python tools/pve/status.py --publish          # push HTML to the monitoring-01 status page
deactivate
```

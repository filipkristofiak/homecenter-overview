# pve-01 resource overview script

`tools/pve/status.py` — runs from your Mac, SSHes into pve-01, and renders
a live memory/CPU table for all LXCs and VMs.

---

## Setup

```bash
python3 -m venv tools/.venv
source tools/.venv/bin/activate
pip install rich
```

---

## Usage

```bash
source tools/.venv/bin/activate
python tools/pve/status.py
```

---

## Example output

```
                                               pve-01 · resource overview
╭───────┬────────────────────────┬─────┬──────────┬─────────┬─────────┬─────────┬──────────────────────────────┬────────╮
│    ID │ Name                   │     │ Status   │   Alloc │     RSS │   Cache │ Memory                       │    CPU │
├───────┼────────────────────────┼─────┼──────────┼─────────┼─────────┼─────────┼──────────────────────────────┼────────┤
│   100 │ truenas                │ VM  │ running  │  16383M │   5055M │    763M │ ██████░░░░░░░░░░░░░░   32%   │   0.0% │
│   200 │ nut-01                 │ LXC │ running  │    256M │     57M │    156M │ ████▒▒▒▒▒▒▒▒▒▒▒▒░░░░   22%   │   0.0% │
│   201 │ monitoring-01          │ LXC │ running  │   1024M │    241M │    722M │ ████▒▒▒▒▒▒▒▒▒▒▒▒▒▒░░   24%   │   0.0% │
│   202 │ plex-01                │ LXC │ running  │   2048M │    234M │   1267M │ ██▒▒▒▒▒▒▒▒▒▒▒▒░░░░░░   11%   │   0.0% │
│   203 │ homeautomation-01      │ VM  │ running  │   2048M │    848M │   1208M │ ████████▒▒▒▒▒▒▒▒▒▒▒▒   43%   │   0.0% │
│  9000 │ debian-12-cloudinit    │ VM  │ stopped  │   1024M │         │         │                              │   0.0% │
╰───────┴────────────────────────┴─────┴──────────┴─────────┴─────────┴─────────┴──────────────────────────────┴────────╯
  █ RSS   ▒ cache   ░ free
```

---

## How it works

- Fetches LXC and VM lists from `pvesh` on pve-01
- Runs `free -m` inside each running guest (`pct exec` for LXCs, `qm guest exec` for VMs)
- Memory bar shows RSS (green/yellow/red by % used), cache (blue), and free (dim)
- Guests where `free -m` fails (no guest agent, FreeBSD, stopped) show empty mem fields

Requires `~/.ssh/homelab_id` key with access to `***@*.*.*.*`.

---

## Notes

- TrueNAS uses all available RAM for ZFS ARC — its high RSS is expected, not a leak
- plex-01 shows low RSS at idle; memory only climbs during active local media playback
- monitoring-01's cache is Prometheus TSDB — expected to grow over time

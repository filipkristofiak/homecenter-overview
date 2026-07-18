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
python tools/pve/status.py             # render in terminal
python tools/pve/status.py --html out.html   # also export as HTML
python tools/pve/status.py --publish   # push HTML to the monitoring-01 status page
```

---

## Example output

```
                                                    pve-01 · resource overview
╭───────┬────────────────────────┬─────┬──────────┬─────────┬─────────┬─────────┬─────────┬──────────────────────────────┬────────╮
│    ID │ Name                   │     │ Status   │   Alloc │     RSS │   Cache │   Touch │ Memory                       │    CPU │
├───────┼────────────────────────┼─────┼──────────┼─────────┼─────────┼─────────┼─────────┼──────────────────────────────┼────────┤
│   100 │ truenas                │ VM  │ running  │  16383M │   4866M │    786M │  16460M │ █████░░░░░░░░░░░░░░░   30%   │   0.4% │
│   200 │ nut-01                 │ LXC │ running  │    256M │     72M │    154M │     84M │ █████▒▒▒▒▒▒▒▒▒▒▒▒░░░   28%   │   0.7% │
│   201 │ monitoring-01          │ LXC │ running  │   1024M │    295M │    635M │    326M │ █████▒▒▒▒▒▒▒▒▒▒▒▒░░░   29%   │   1.0% │
│   202 │ plex-01                │ LXC │ running  │   2048M │    123M │    318M │    137M │ █▒▒▒░░░░░░░░░░░░░░░░    6%   │   0.3% │
│   203 │ homeautomation-01      │ VM  │ running  │   2048M │    767M │    998M │   2074M │ ███████▒▒▒▒▒▒▒▒▒░░░░   37%   │   0.4% │
│   204 │ k3s-01                 │ VM  │ running  │  16384M │   1299M │   2543M │   4132M │ █▒▒▒░░░░░░░░░░░░░░░░    8%   │   1.0% │
│  9000 │ debian-12-cloudinit    │ VM  │ stopped  │   1024M │         │         │         │                              │   0.0% │
├───────┼────────────────────────┼─────┼──────────┼─────────┼─────────┼─────────┼─────────┼──────────────────────────────┼────────┤
│       │ guests total           │     │          │  39167M │   7422M │   5434M │  23213M │ ██▒░░░░░░░░░░░░░░░░░   12%   │   0.7% │
├───────┼────────────────────────┼─────┼──────────┼─────────┼─────────┼─────────┼─────────┼──────────────────────────────┼────────┤
│       │ pve-01 (host)          │     │          │  64069M │         │         │  25978M │ ████████░░░░░░░░░░░░   41%   │   0.8% │
╰───────┴────────────────────────┴─────┴──────────┴─────────┴─────────┴─────────┴─────────┴──────────────────────────────┴────────╯
  █ RSS   ▒ cache   ░ free   ·   Touch = host-resident (VMs: pages ever touched, only grows; LXC: cgroup usage)
  nvme0n1 *** · health OK · wear 0% · 38°C · spare 100% · 0 media errs · 1.0 TB / 160 TBW written
```

---

## How it works

- Fetches LXC and VM lists from `pvesh` on pve-01
- CPU and the **Touch** column come from `pvesh get /cluster/resources` — PVE 9
  stopped populating `cpu`/`maxcpu` in the per-node `lxc`/`qemu` endpoints (they
  read as hard zeros), so per-guest data is joined on vmid from the cluster view
- **Touch** is the *host-side* resident memory: for VMs the qemu process RSS —
  every guest page ever touched, which only grows (without ballooning nothing is
  handed back, so long-lived VMs converge to their full allocation); for LXCs
  the cgroup usage. `guests total` Touch vs the host row's Touch shows how much
  RAM the host itself consumes (~2.7 GB)
- **RSS/Cache** are the *in-guest* view: `free -m` inside each running guest
  (`pct exec` for LXCs, `qm guest exec` for VMs)
- Memory bar shows RSS (green/yellow/red by % used), cache (blue), and free (dim)
- If the in-guest query fails (QEMU agent down, FreeBSD), RSS falls back to the
  hypervisor view marked with `~` (no RSS/cache split) so the guest still counts
  toward `guests total` instead of silently dropping out
- NVMe footer reads `/var/lib/prometheus/node-exporter/nvme.prom` on the host (written
  every 5 min by the SMART collector, see
  [pve-01-nvme-health.md](pve-01-nvme-health.md)); health flag thresholds mirror the
  Prometheus alert rules, and the line warns in red if the file is >30 min stale

Requires `~/.ssh/homelab_id` key with access to `***@*.*.*.*`.

---

## Web status page

`--publish` exports the exact terminal rendering as HTML (rich `Console(record=True)`
+ `export_html` with an Ubuntu-terminal theme: aubergine background, Tango palette;
fixed 134-column width, rendered at 80% font size)
and scps it to `monitoring-01:/opt/monitoring/status/index.html`, where an
`nginx:alpine` container from the monitoring compose stack serves it on port 80
under `/status/` (`/` redirects there):

- **URL**: `http://*.*.*.*/status`
- The page auto-refreshes in the browser every 60 s, but its *content* only updates
  when `--publish` is run from the Mac — check the "as of" timestamp at the bottom.
- Uses the same `~/.ssh/homelab_id` key as everything else; no new trust edges.

### Follow-up: automate publishing

The page is only as fresh as the last manual run. To make it self-updating, run the
script on a schedule *on monitoring-01* (systemd timer, every 1–2 min). Deliberately
deferred because it requires a new trust edge — monitoring-01 would need an SSH key
authorized on `root@pve-01`. When doing it:

- use a dedicated key, restricted in `authorized_keys` (`from=`, ideally
  `command=` wrappers), not the general homelab key
- add SSH `ControlMaster` reuse — the script opens ~10 sequential SSH connections
  per run
- deploy the timer + key via the monitoring role so it stays in code

---

## Notes

- TrueNAS uses all available RAM for ZFS ARC — its Touch sits at its full 16 GB
  allocation permanently; expected, not a leak
- k3s-01's Touch creeps upward from ~4 GB toward its 16 GB allocation as
  workloads touch pages — plan host RAM against allocations, not guest RSS
- plex-01 shows low RSS at idle; memory only climbs during active local media playback
- monitoring-01's cache is Prometheus TSDB — expected to grow over time

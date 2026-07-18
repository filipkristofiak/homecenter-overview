#!/usr/bin/env python3
"""
Proxmox resource overview — runs from Mac, SSHes into pve-01.

Usage:
    python tools/pve/status.py                # render in terminal
    python tools/pve/status.py --html out.html
    python tools/pve/status.py --publish      # scp HTML to monitoring-01 status page
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich.terminal_theme import TerminalTheme
    from rich.text import Text
    from rich import box
except ImportError:
    print("Missing dependencies. Run: pip install rich")
    sys.exit(1)

PVE_HOST = "***@*.*.*.*" # user@host
SSH_KEY = str(Path.home() / ".ssh" / "homelab_id")

MONITORING_HOST = "***@*.*.*.*" # user@host
PUBLISH_DEST = "/opt/monitoring/status/index.html"
STATUS_URL = "http://*.*.*.*/status"

# written by the nvme-metrics timer on pve-01
NVME_PROM = "/var/lib/prometheus/node-exporter/nvme.prom"
NVME_STALE_MIN = 30
# rated endurance per model — only used for the "written / rated" figure
NVME_RATED_TBW = {"***": 160}  # keyed by model string as reported by the collector

# Ubuntu terminal look: aubergine background + Tango palette
UBUNTU_THEME = TerminalTheme(
    (48, 10, 36),      # background #300A24
    (238, 238, 236),   # foreground #EEEEEC
    [   # normal
        (46, 52, 54), (204, 0, 0), (78, 154, 6), (196, 160, 0),
        (52, 101, 164), (117, 80, 123), (6, 152, 154), (211, 215, 207),
    ],
    [   # bright
        (85, 87, 83), (239, 41, 41), (138, 226, 52), (252, 233, 79),
        (114, 159, 207), (173, 127, 168), (52, 226, 226), (238, 238, 236),
    ],
)

HTML_FORMAT = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="60">
<title>pve-01 · resource overview</title>
<style>
{stylesheet}
body {{
    color: {foreground};
    background-color: {background};
    padding: 24px;
}}
pre {{
    font-size: 80%;
}}
</style>
</head>
<body>
    <pre style="font-family:'Ubuntu Mono',Menlo,'DejaVu Sans Mono',consolas,'Courier New',monospace"><code style="font-family:inherit">{code}</code></pre>
</body>
</html>
"""


def ssh(cmd: str) -> str:
    result = subprocess.run(
        ["ssh", "-i", SSH_KEY, "-o", "BatchMode=yes", PVE_HOST, cmd],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def parse_free(output: str) -> tuple[int, int, int] | None:
    """Returns (rss_mb, cache_mb, total_mb) from `free -m` output."""
    for line in output.splitlines():
        if line.startswith("Mem:"):
            parts = line.split()
            return int(parts[2]), int(parts[5]), int(parts[1])
    return None


def inner_mem(vmid: int, kind: str) -> tuple[int, int, int] | None:
    """Returns (rss_mb, cache_mb, total_mb) queried from inside the guest."""
    try:
        if kind == "lxc":
            return parse_free(ssh(f"pct exec {vmid} -- free -m"))
        else:
            raw = json.loads(ssh(f"qm guest exec {vmid} -- free -m"))
            return parse_free(raw.get("out-data", ""))
    except Exception:
        return None


def mem_bar(rss: int, cache: int, total: int, width: int = 20) -> Text:
    if total == 0:
        return Text("░" * width, style="dim")
    rss_w = min(int(rss / total * width), width)
    cache_w = min(int(cache / total * width), width - rss_w)
    empty_w = width - rss_w - cache_w
    pct = rss / total * 100
    color = "green" if pct < 60 else "yellow" if pct < 85 else "red"
    t = Text()
    t.append("█" * rss_w, style=color)
    t.append("▒" * cache_w, style="blue")
    t.append("░" * empty_w, style="dim")
    t.append(f" {pct:4.0f}%", style="dim")
    return t


def nvme_health_lines() -> list[Text]:
    """One footer line per NVMe drive, from the SMART collector's textfile output.

    Thresholds mirror the Prometheus alert rules in
    ansible/roles/monitoring/templates/alerts.yml.j2 — this is a snapshot view,
    not a second opinion.
    """
    try:
        raw = ssh(f"stat -c %Y {NVME_PROM}; date +%s; cat {NVME_PROM}")
    except Exception as e:
        return [Text(f"  nvme health unavailable: {e}", style="dim")]

    mtime_s, now_s, *metric_lines = raw.splitlines()
    stale_min = (int(now_s) - int(mtime_s)) / 60

    drives: dict[str, dict] = {}
    for line in metric_lines:
        m = re.match(r'(\w+)\{(.*)\} (\S+)', line)
        if not m:
            continue
        name, labels_str, value = m.groups()
        labels = dict(re.findall(r'(\w+)="([^"]*)"', labels_str))
        d = drives.setdefault(labels.get("device", "?"), {"model": labels.get("model", "")})
        d[name] = float(value)

    lines = []
    for device, d in sorted(drives.items()):
        wear = d.get("nvme_percentage_used_percent", 0)
        temp = d.get("nvme_temperature_celsius", 0)
        spare = d.get("nvme_available_spare_percent", 0)
        spare_thresh = d.get("nvme_available_spare_threshold_percent", 0)
        media = d.get("nvme_media_errors_total", 0)
        crit = d.get("nvme_critical_warning", 0)
        written_tb = d.get("nvme_written_bytes_total", 0) / 1e12

        spare_low = spare <= spare_thresh + 5
        critical = crit > 0 or media > 0 or spare_low
        degraded = wear >= 80 or temp > 70

        t = Text("  ")
        t.append(f"{device} {d['model']}", style="dim")
        t.append(" · ", style="dim")
        if critical:
            t.append("health CRITICAL", style="bold red")
        elif degraded:
            t.append("health DEGRADED", style="yellow")
        else:
            t.append("health OK", style="green")
        t.append(" · ", style="dim")
        t.append(f"wear {wear:.0f}%", style="yellow" if wear >= 80 else "dim")
        t.append(" · ", style="dim")
        t.append(f"{temp:.0f}°C", style="yellow" if temp > 70 else "dim")
        t.append(" · ", style="dim")
        t.append(f"spare {spare:.0f}%", style="red" if spare_low else "dim")
        t.append(" · ", style="dim")
        t.append(f"{media:.0f} media errs", style="red" if media > 0 else "dim")
        t.append(" · ", style="dim")
        rated = NVME_RATED_TBW.get(d["model"])
        rated_str = f" / {rated} TBW" if rated else ""
        t.append(f"{written_tb:.1f} TB{rated_str} written", style="dim")
        if stale_min > NVME_STALE_MIN:
            t.append(f"  (stale {stale_min:.0f}m — check nvme-metrics.timer)", style="red")
        lines.append(t)

    return lines or [Text("  no nvme metrics in collector output", style="dim")]


def publish(html: str) -> None:
    """scp the rendered page to the monitoring-01 status directory."""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html)
        tmp_path = f.name
    try:
        result = subprocess.run(
            ["scp", "-q", "-i", SSH_KEY, "-o", "BatchMode=yes",
             tmp_path, f"{MONITORING_HOST}:{PUBLISH_DEST}"],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
    finally:
        os.unlink(tmp_path)


def main():
    parser = argparse.ArgumentParser(description="pve-01 resource overview")
    parser.add_argument("--html", metavar="PATH",
                        help="also write the rendered output as an HTML page")
    parser.add_argument("--publish", action="store_true",
                        help=f"push HTML to {MONITORING_HOST}:{PUBLISH_DEST} ({STATUS_URL})")
    args = parser.parse_args()

    exporting = bool(args.html or args.publish)
    # fixed width when exporting so the HTML doesn't depend on terminal size
    console = Console(record=exporting, width=134 if exporting else None)

    try:
        lxc_list = json.loads(ssh("pvesh get /nodes/pve-01/lxc --output-format json"))
        qemu_list = json.loads(ssh("pvesh get /nodes/pve-01/qemu --output-format json"))
        node_status = json.loads(ssh("pvesh get /nodes/pve-01/status --output-format json"))
        resources = json.loads(ssh("pvesh get /cluster/resources --output-format json"))
    except Exception as e:
        console.print(f"[red]SSH error:[/red] {e}")
        sys.exit(1)

    # PVE 9 no longer populates cpu/maxcpu in the per-node lxc/qemu endpoints
    # (they read as hard 0/absent); /cluster/resources still carries live values.
    # Its "mem" is the host-side view: qemu RSS for VMs (every guest page ever
    # touched — never returned without ballooning), cgroup usage for LXCs.
    res_by_vmid = {r["vmid"]: r for r in resources if r.get("vmid")}
    host_cpu = next((r.get("cpu", 0) for r in resources
                     if r.get("type") == "node" and r.get("node") == "pve-01"),
                    node_status["cpu"])

    host_mem_total = int(node_status["memory"]["total"] / 1024**2)
    host_mem_used = int(node_status["memory"]["used"] / 1024**2)
    host_cpu_pct = host_cpu * 100
    host_cpus = node_status["cpuinfo"]["cpus"]

    table = Table(
        title="[bold]pve-01[/bold] · resource overview",
        box=box.ROUNDED,
        header_style="bold white",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("ID", style="dim", width=5, justify="right")
    table.add_column("Name", width=22)
    table.add_column("", width=3)
    table.add_column("Status", width=8)
    table.add_column("Alloc", width=7, justify="right")
    table.add_column("RSS", width=7, justify="right")
    table.add_column("Cache", width=7, justify="right")
    table.add_column("Touch", width=7, justify="right")
    table.add_column("Memory", width=28)
    table.add_column("CPU", width=6, justify="right")

    all_items = [(c, "lxc") for c in lxc_list] + [(v, "vm") for v in qemu_list]
    all_items.sort(key=lambda x: x[0]["vmid"])

    total_alloc = total_rss = total_cache = total_touched = 0
    weighted_cpu_num = weighted_cpu_den = 0.0

    for item, kind in all_items:
        vmid = item["vmid"]
        name = item["name"]
        status = item["status"]
        maxmem_mb = int(item.get("maxmem", 0) / 1024**2)
        res = res_by_vmid.get(vmid, item)
        cpu_ratio = res.get("cpu", 0)
        maxcpu = res.get("maxcpu", item.get("cpus", 1))
        cpu_pct = f"{cpu_ratio * 100:.1f}%"
        touched_mb = int(res.get("mem", 0) / 1024**2)

        type_text = Text("LXC", style="cyan") if kind == "lxc" else Text("VM", style="magenta")
        status_text = Text("running", style="green") if status == "running" else Text(status, style="dim")

        rss_str = cache_str = touched_str = ""
        bar: Text = Text("")

        total_alloc += maxmem_mb
        weighted_cpu_num += cpu_ratio * maxcpu
        weighted_cpu_den += maxcpu

        if status == "running":
            touched_str = f"{touched_mb}M"
            total_touched += touched_mb
            mem = inner_mem(vmid, kind)
            if mem:
                rss, cache, _ = mem
                rss_str = f"{rss}M"
                cache_str = f"{cache}M"
                bar = mem_bar(rss, cache, maxmem_mb)
                total_rss += rss
                total_cache += cache
            else:
                # in-guest query failed (e.g. QEMU agent down) — fall back to the
                # hypervisor's view so the guest still counts toward totals;
                # no RSS/cache split available, hence the ~ marker
                rss_str = f"~{touched_mb}M"
                bar = mem_bar(touched_mb, 0, maxmem_mb)
                total_rss += touched_mb

        table.add_row(
            str(vmid), name, type_text, status_text,
            f"{maxmem_mb}M", rss_str, cache_str, touched_str, bar, cpu_pct,
        )

    # guests total row — guest RSS against host RAM, weighted CPU across host cores
    table.add_section()
    total_bar = mem_bar(total_rss, total_cache, host_mem_total)
    guest_cpu_pct = (weighted_cpu_num / weighted_cpu_den * 100) if weighted_cpu_den else 0
    table.add_row(
        "", Text("guests total", style="bold"), "", "",
        Text(f"{total_alloc}M", style="bold"),
        Text(f"{total_rss}M", style="bold"),
        Text(f"{total_cache}M", style="bold"),
        Text(f"{total_touched}M", style="bold"),
        total_bar,
        Text(f"{guest_cpu_pct:.1f}%", style="bold"),
    )

    # host row — kernel view of the whole node
    table.add_section()
    host_bar = mem_bar(host_mem_used, 0, host_mem_total)
    table.add_row(
        "", Text("pve-01 (host)", style="bold white"), "", "",
        Text(f"{host_mem_total}M", style="bold white"), "", "",
        Text(f"{host_mem_used}M", style="bold white"),
        host_bar,
        Text(f"{host_cpu_pct:.1f}%", style="bold white"),
    )

    console.print()
    console.print(table)
    console.print("  [dim]█ RSS   ▒ cache   ░ free   ·   Touch = host-resident (VMs: pages ever touched, only grows; LXC: cgroup usage)[/dim]")
    console.print()
    for line in nvme_health_lines():
        console.print(line)
    console.print()
    if exporting:
        console.print(f"  [dim]as of {datetime.now():%Y-%m-%d %H:%M:%S}[/dim]")
    console.print()

    if exporting:
        html = console.export_html(theme=UBUNTU_THEME, code_format=HTML_FORMAT)
        if args.html:
            Path(args.html).write_text(html)
            console.print(f"HTML written to {args.html}")
        if args.publish:
            try:
                publish(html)
                console.print(f"published → {STATUS_URL}")
            except Exception as e:
                console.print(f"[red]publish failed:[/red] {e}")
                sys.exit(1)


if __name__ == "__main__":
    main()

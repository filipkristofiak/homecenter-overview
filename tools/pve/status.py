#!/usr/bin/env python3
"""
Proxmox resource overview — runs from Mac, SSHes into pve-01.

Usage:
    python tools/pve/status.py
"""

import json
import subprocess
import sys
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text
    from rich import box
except ImportError:
    print("Missing dependencies. Run: pip install rich")
    sys.exit(1)

PVE_HOST = "***@*.*.*.*" # user@host
SSH_KEY = str(Path.home() / ".ssh" / "homelab_id")


def ssh(cmd: str) -> str:
    result = subprocess.run(
        ["ssh", "-i", SSH_KEY, "-o", "BatchMode=yes", PVE_HOST, cmd],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()

ß
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


def main():
    console = Console()

    try:
        lxc_list = json.loads(ssh("pvesh get /nodes/pve-01/lxc --output-format json"))
        qemu_list = json.loads(ssh("pvesh get /nodes/pve-01/qemu --output-format json"))
        node_status = json.loads(ssh("pvesh get /nodes/pve-01/status --output-format json"))
    except Exception as e:
        console.print(f"[red]SSH error:[/red] {e}")
        sys.exit(1)

    host_mem_total = int(node_status["memory"]["total"] / 1024**2)
    host_mem_used = int(node_status["memory"]["used"] / 1024**2)
    host_cpu_pct = node_status["cpu"] * 100
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
    table.add_column("Memory", width=28)
    table.add_column("CPU", width=6, justify="right")

    all_items = [(c, "lxc") for c in lxc_list] + [(v, "vm") for v in qemu_list]
    all_items.sort(key=lambda x: x[0]["vmid"])

    total_alloc = total_rss = total_cache = 0
    weighted_cpu_num = weighted_cpu_den = 0.0

    for item, kind in all_items:
        vmid = item["vmid"]
        name = item["name"]
        status = item["status"]
        maxmem_mb = int(item.get("maxmem", 0) / 1024**2)
        maxcpu = item.get("maxcpu", item.get("cpus", 1))
        cpu_ratio = item.get("cpu", 0)
        cpu_pct = f"{cpu_ratio * 100:.1f}%"

        type_text = Text("LXC", style="cyan") if kind == "lxc" else Text("VM", style="magenta")
        status_text = Text("running", style="green") if status == "running" else Text(status, style="dim")

        rss_str = cache_str = ""
        bar: Text = Text("")

        total_alloc += maxmem_mb
        weighted_cpu_num += cpu_ratio * maxcpu
        weighted_cpu_den += maxcpu

        if status == "running":
            mem = inner_mem(vmid, kind)
            if mem:
                rss, cache, _ = mem
                rss_str = f"{rss}M"
                cache_str = f"{cache}M"
                bar = mem_bar(rss, cache, maxmem_mb)
                total_rss += rss
                total_cache += cache

        table.add_row(
            str(vmid), name, type_text, status_text,
            f"{maxmem_mb}M", rss_str, cache_str, bar, cpu_pct,
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
        total_bar,
        Text(f"{guest_cpu_pct:.1f}%", style="bold"),
    )

    # host row — kernel view of the whole node
    table.add_section()
    host_bar = mem_bar(host_mem_used, 0, host_mem_total)
    table.add_row(
        "", Text("pve-01 (host)", style="bold white"), "", "",
        Text(f"{host_mem_total}M", style="bold white"),
        Text(f"{host_mem_used}M", style="bold white"), "",
        host_bar,
        Text(f"{host_cpu_pct:.1f}%", style="bold white"),
    )

    console.print()
    console.print(table)
    console.print("  [dim]█ RSS   ▒ cache   ░ free[/dim]")
    console.print()


if __name__ == "__main__":
    main()

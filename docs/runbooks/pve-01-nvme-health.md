# NVMe Health Monitoring — pve-01

## What was done

pve-01 runs everything (hypervisor + all LXC/VM disks) from a single NVMe drive
(rated 160 TBW), so its health is monitored from three angles:

1. **SMART metrics in Prometheus** — a collector script on pve-01 reads the NVMe SMART
   health log every 5 minutes and exposes it via node exporter's textfile collector.
2. **Alert rules in Prometheus** — wear, spare capacity, media errors, temperature and
   the drive's own critical-warning flag.
3. **smartd** — independent periodic self-checks on the host, mails `root` on failure
   (second signal path that does not depend on the monitoring stack).

As a side effect, pve-01 now also runs a full node exporter, so host-level CPU, memory,
disk-latency and filesystem metrics are in Prometheus alongside the guests.

The `tools/pve/status.py` terminal overview (see [pve-status.md](pve-status.md)) shows
a one-line health summary parsed from the collector's output, with the same thresholds
as the alert rules.

---

## File layout

```
ansible/
  playbooks/pve-host.yml               applies node_exporter + pve_host to pve-01
  roles/pve_host/
    tasks/main.yml                     install smartmontools + nvme-cli, enable smartd,
                                       deploy collector + systemd units
    templates/nvme-metrics.j2          Python collector → /usr/local/bin/nvme-metrics
    files/nvme-metrics.service         oneshot unit running the collector
    files/nvme-metrics.timer           every 5 min (+2 min after boot)
  roles/monitoring/
    templates/prometheus.yml.j2        node job includes groups['proxmox_hosts']; rule_files
    templates/alerts.yml.j2            NVMe alert rules
    templates/docker-compose.yml.j2    mounts alerts.yml into the Prometheus container
```

On pve-01 itself:

| Path | Purpose |
|---|---|
| `/usr/local/bin/nvme-metrics` | collector (parses `nvme smart-log -o json`) |
| `/etc/systemd/system/nvme-metrics.{service,timer}` | schedule |
| `/var/lib/prometheus/node-exporter/nvme.prom` | output read by node exporter |

---

## Deploy

```bash
cd ansible
ansible-playbook playbooks/pve-host.yml     # collector + smartd on pve-01
ansible-playbook playbooks/monitoring.yml   # scrape target + alert rules on monitoring-01
```

Both playbooks are idempotent. The monitoring playbook restarts the docker-compose
stack when the config changes (brief Prometheus/Grafana blip).

---

## Verify

```bash
# metrics exposed on the host
ssh -i ~/.ssh/homelab_id ***@*.*.*.* \
  'curl -s localhost:9100/metrics | grep ^nvme_'

# Prometheus scrapes pve-01 (job=node, nodename=pve-01, health=up)
open http://*.*.*.*:9090/targets

# alert rules loaded and inactive
open http://*.*.*.*:9090/alerts

# timer status on the host
ssh -i ~/.ssh/homelab_id ***@*.*.*.* \
  'systemctl list-timers nvme-metrics.timer; systemctl status nvme-metrics.service'
```

---

## Metrics reference

All series carry `device`, `model`, `serial` labels (plus `nodename=pve-01` from the
scrape config).

| Metric | Meaning |
|---|---|
| `nvme_critical_warning` | Drive's own warning bitfield. **0 = healthy.** Bits: 0x01 spare below threshold, 0x02 temperature, 0x04 reliability degraded, 0x08 media read-only, 0x10 volatile backup failed |
| `nvme_percentage_used_percent` | Consumed endurance estimate (can exceed 100) — the single best "life left" number |
| `nvme_available_spare_percent` / `..._threshold_percent` | Remapped-block reserve vs. the level at which the drive raises a critical warning |
| `nvme_media_errors_total` | Unrecovered media/data-integrity errors — should stay 0 forever |
| `nvme_temperature_celsius` | Composite temperature (throttling starts ~70–80 °C) |
| `nvme_written_bytes_total` / `nvme_read_bytes_total` | Cumulative traffic (derived: 1 data unit = 512 000 bytes) |
| `nvme_data_units_written_total` etc. | Raw counters from the SMART log |
| `nvme_unsafe_shutdowns_total`, `nvme_power_cycles_total`, `nvme_power_on_hours_total`, `nvme_error_log_entries_total` | Informational |

Useful queries:

```promql
# write rate in GB/day — Proxmox is notorious for grinding SSDs with small writes
rate(nvme_written_bytes_total[6h]) * 86400 / 1e9

# projected years to rated endurance (160 TBW for this drive)
(160e12 - nvme_written_bytes_total) / (rate(nvme_written_bytes_total[7d]) * 86400 * 365)
```

Baseline at deployment (2026-07-18): 0 % wear, 100 % spare, 0 media errors, 37 °C,
~0.95 TB written of 160 TBW.

---

## Alert rules

Defined in `roles/monitoring/templates/alerts.yml.j2`, visible at
`http://*.*.*.*:9090/alerts`.

| Alert | Condition | Severity | Action |
|---|---|---|---|
| NvmeCriticalWarning | bitfield > 0 for 5m | critical | check `nvme smart-log /dev/nvme0n1` on pve-01; decode bits above |
| NvmeSpareLow | spare ≤ threshold + 5 for 15m | critical | flash is failing — replace the drive |
| NvmeMediaErrors | any increase in 24h | critical | verify backups, plan replacement |
| NvmeWearHigh | wear ≥ 80 % for 1h | warning | order a replacement before 100 % |
| NvmeHighTemperature | > 70 °C for 15m | warning | check airflow / heatsink |
| NvmeMetricsStale | `nvme.prom` older than 30m | warning | `systemctl status nvme-metrics.service` on pve-01 |

---

## Troubleshooting

**NvmeMetricsStale fires / metrics missing:**

```bash
ssh -i ~/.ssh/homelab_id ***@*.*.*.*
systemctl status nvme-metrics.service     # last run + errors
/usr/local/bin/nvme-metrics               # run manually, prints traceback on failure
nvme list -o json                         # collector depends on this output shape
```

The collector writes atomically (temp file + rename); a failed run leaves the previous
`nvme.prom` in place, which is what the staleness alert catches.

**Manual health check (bypasses the whole stack):**

```bash
nvme smart-log /dev/nvme0n1
smartctl -a /dev/nvme0n1
```

---

## Key decisions

| Decision | Value | Reason |
|---|---|---|
| Collection method | textfile collector + timer | reuses existing node_exporter role; no extra daemon (vs. smartctl_exporter) |
| Collector language | Python 3, stdlib only | always present on PVE; parses `nvme smart-log -o json` |
| Interval | 5 min | SMART values change slowly; no point scraping faster |
| smartd | enabled alongside | independent alerting path (mail to root) if the monitoring stack is down |
| Alerting | Prometheus rules only | no Alertmanager deployed yet — alerts are visible, not pushed |

---

## Limitations / follow-ups

- **No push notifications** — rules fire in Prometheus/Grafana but nothing is routed
  anywhere. Deploying Alertmanager (or Grafana contact points) is the natural next step.
- **SMART won't predict everything** — controllers die suddenly without warning. This
  monitoring reduces surprise; it does not reduce blast radius. Scheduled `vzdump`
  backups off the drive (e.g. to TrueNAS) are the actual mitigation.
- LVM-thin pool usage on the host is not yet alerted on (visible via pve-exporter /
  node exporter filesystem metrics).

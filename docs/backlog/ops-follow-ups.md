# Operations follow-ups

## Alerting

**Alerting rules** — a `rule_files` block now exists and loads
`roles/monitoring/templates/alerts.yml.j2` (currently NVMe health rules for pve-01,
see [pve-01-host.md](../runbooks/pve-01-host.md)). Guest-level rules are still
missing; useful starting points to add to that file:

| Alert | Condition | Why it matters |
|---|---|---|
| High disk usage | filesystem > 85% full | LXC disks are fixed-size; no autogrow |
| High memory | memory used > 90% | containers have hard RAM limits set in Terraform |
| Node down | target unreachable for > 2m | catches container crashes or network issues |

**Alertmanager** — even with rules defined, Prometheus needs Alertmanager running to
route alerts somewhere (email, Slack, etc.). Not yet deployed.

- **No push notifications** — rules fire in Prometheus/Grafana but nothing is routed
  anywhere. Deploying Alertmanager (or Grafana contact points) is the natural next step.
- LVM-thin pool usage on the host is not yet alerted on (visible via pve-exporter /
  node exporter filesystem metrics).

| Item | Follow-up |
|---|---|
| Alertmanager (email/Slack alerts) | Not yet deployed — needs new LXC or addition to monitoring stack |

## Status page

The page is only as fresh as the last manual run. To make it self-updating, run the
script on a schedule *on monitoring-01* (systemd timer, every 1–2 min). Deliberately
deferred because it requires a new trust edge — monitoring-01 would need an SSH key
authorized on `root@pve-01`. When doing it:

- use a dedicated key, restricted in `authorized_keys` (`from=`, ideally
  `command=` wrappers), not the general homelab key
- add SSH `ControlMaster` reuse — the script opens ~10 sequential SSH connections
  per run
- deploy the timer + key via the monitoring role so it stays in code

## Network

- Consider moving Proxmox host to VLAN 23 (UniFi management network) long-term for cleaner separation between hypervisor management and workloads

## k3s

| Decision | Value | Reason |
|---|---|---|
| Future storage tier | TrueNAS + democratic-csi | Spare 512 GB SATA SSD; replaceable data only (TrueNAS is a VM on the same host) |

## Guest backups

| Item | Follow-up |
|---|---|
| Other guest backups | VM 203 is backed up weekly to TrueNAS; other guest disks are not. See [pve-01-backups.md](../runbooks/pve-01-backups.md). |

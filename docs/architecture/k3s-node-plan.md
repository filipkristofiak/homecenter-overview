# k3s Node Plan — `k3s-01`

Status: **built 2026-07-18** (VM + k3s + monitoring integration; in-cluster
workloads pending). This document captures sizing and design decisions for a
single-node k3s cluster on `pve-01`.

## Purpose

One k3s node serving two workload classes:

1. **Stable home services** — candidates to migrate over time (monitoring stack
   first; see [Non-goals](#non-goals) for why Plex stays out).
2. **Learning projects** — a small "data platform": pandas processing jobs,
   Postgres for storage, Redpanda as message broker, plus an orchestrator.

## VM specification

| Item | Value | Rationale |
|------|-------|-----------|
| Name | `k3s-01` | Follows `<service>-XX` convention (`naming.md`) |
| VM ID | 204 | Next free ID |
| IP | `*.*.*.*` | Next free static on VLAN 27 |
| DNS | `k3s-01.lab.local` | |
| Form | VM (Debian 12 cloud-init, same template as `homeautomation-01`) | k3s in LXC fights cgroups/overlayfs even privileged; VM is the clean path |
| vCPU | 8, **no affinity pinning** | Bursty pandas jobs benefit from P-cores; `homeautomation-01` already owns E-cores 12–19. Overcommit is fine on this mostly idle host |
| RAM | 16 GB dedicated, no ballooning | See budget below; can grow to 24 GB and still leave ~** GB host headroom |
| Root disk | 40 GB (`local-lvm`) | OS + k3s + container images |
| Data disk | 150 GB (`local-lvm`, thin) | Persistent volumes via k3s built-in local-path provisioner. Thin-provisioned — grow later is trivial, shrink is not |

Host capacity at planning time (2026-07-18): ~** GB RAM free, ~*** GB free on
`local-lvm` (NVMe). This VM consumes 16 GB RAM and 190 GB nominal disk (far less
actual until written).

### RAM budget (why 16 GB works)

| Component | Est. RAM |
|-----------|----------|
| k3s control plane + system pods | ~2 GB |
| Postgres | 2–4 GB |
| Redpanda (single node, capped) | 2 GB |
| Orchestrator (Dagster/Argo Workflows) | ~1 GB |
| pandas job burst headroom | 4–6 GB |
| Monitoring stack, if migrated | 2–3 GB |

## Storage design

Two tiers, split by availability and latency requirements:

- **Tier 1 — local NVMe (build now):** the 150 GB data disk, exposed through the
  local-path provisioner. Holds all fsync-heavy and availability-sensitive
  state: Postgres, Redpanda, Prometheus TSDB. Rough headroom: Postgres 20–50 GB,
  Redpanda 20–40 GB, Prometheus 15–30 GB (30-day retention), rest scratch.
- **Tier 2 — TrueNAS-backed (future expansion):** a spare 512 GB SATA SSD goes
  into a free port on the SATA controller passed through to the `truenas` VM →
  single-disk pool → served to k3s via
  [democratic-csi](https://github.com/democratic-csi/democratic-csi) (TrueNAS
  API driver). iSCSI storage class for anything database-shaped, NFS for
  shared/bulk. For replaceable data only — both VMs live on the same host, so
  TrueNAS downtime hangs any pod mounting its volumes. Traffic stays on the
  host's virtual bridge, so the SATA drive itself is the bottleneck, which is
  acceptable. No expansion card purchase: not worth it for one DRAM-less SATA
  drive slower than the existing NVMe.

## Workload notes

- **Redpanda:** by default grabs most of the machine's memory. Must be capped —
  `--memory 2G --overprovisioned` (or Helm chart equivalents) on a shared node.
  Set per-topic retention limits; default is keep-everything.
- **Orchestrator:** Dagster preferred for a pandas-centric stack (~1 GB, good
  local dev story). Airflow works but costs 2–3 GB and more moving parts.
- **Monitoring migration:** running kube-prometheus-stack is itself a learning
  exercise; note it is heavier than the current `monitoring-01` LXC setup.
  Migrate only after the cluster is stable — don't move the thing that tells
  you the cluster is broken onto the cluster first.

## Network

- VLAN 27 is an internal VLAN with unrestricted inter-zone traffic — no
  new firewall rules needed for cluster operation or Ansible/kubectl access.
- If workloads on `k3s-01` ever need to reach VLAN 39 devices or be
  reached from them, explicit rules are required (VLAN 39 is isolated).

## Non-goals

- **Plex stays in its LXC.** QuickSync iGPU passthrough is trivial to an LXC
  (device nodes) but requires full iGPU passthrough or SR-IOV to a VM —
  hardware transcoding would be lost for no gain.
- **No multi-node / HA.** Single node, single host; k3s HA is out of scope.
- **No SATA expansion card** unless multiple drives are added or NVMe space
  runs out.

## Implementation checklist

1. ✅ Terraform: `vm_k3s` resource in `terraform/pve-01/main.tf` (40 GB scsi0 +
   150 GB scsi1 data disk). Applied 2026-07-18.
2. ✅ Ansible: `k3s.yml` playbook + `k3s` role (deliberately skips `common` —
   no Docker next to k3s's containerd; includes qemu-guest-agent, data disk
   mount at `/var/lib/rancher/k3s/storage`, kubeconfig fetch to
   `~/.kube/k3s-01.yaml`) + `node_exporter` role. Host added to `pve_lxc`
   inventory group, which auto-registers it in the Prometheus `node` job.
   Verified: node Ready (k3s v1.36.2), PVC smoke test provisioned on the data
   disk, node-exporter target up.
3. ⬜ In-cluster bootstrap (Helm/manifests, tracked in repo): Postgres,
   Redpanda (memory-capped), Dagster.
4. ⬜ Later: spare SATA SSD → TrueNAS pool → democratic-csi storage classes.

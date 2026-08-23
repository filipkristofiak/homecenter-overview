# CI/CD Runner — `runner-01` (proposed)

Status: **discussion only, nothing provisioned**. This document captures
options considered for a dedicated CI/CD runner that would execute the full
homecenter deployment (Terraform + Ansible) instead of running it by hand
from a laptop. No decision has been finalized; revisit before provisioning.

## Purpose

Currently `terraform apply` and `ansible-playbook` are run manually, and
`terraform.tfvars` / `ansible/.vault_pass` / the `~/.ssh/homelab_id` key live
only on one Mac. Goal: a host that can run the entire deployment pipeline on
push, without secrets or state being trapped on a single laptop.

## Where to run it: VM, LXC, or k3s pod

A runner holds the most privileged material in the homelab: the Proxmox API
token, the ansible-vault password, and the root SSH key to every host. That
changes the isolation calculus versus other services on `pve-01`.

| Option | Verdict | Reasoning |
|---|---|---|
| **k3s pod** | Rejected | `k3s-01` is itself something the pipeline manages. A workflow that touches k3s (reboot, upgrade, Terraform recreate) could kill the runner executing that very job — circular dependency. |
| **LXC** | Workable, not preferred | Shares the host kernel with pve-01. Fine for Jellyfin/monitoring; weaker boundary for something holding credentials that can destroy/recreate the whole environment. |
| **VM** | **Leaning towards this** | Matches the isolation level already used for `k3s-01` / `homeautomation-01` / `truenas`. Cheap insurance given the blast radius of a compromised runner. |

## Proposed VM spec

Sized for orchestration (Terraform/Ansible/`ssh`), not heavy compute — closer
to `homeautomation-01` than `k3s-01`. Host has plenty of headroom (14-core
Intel host, ~** GB installed RAM, guest memory usage across the whole host
currently ~11% RSS).

| Item | Value | Rationale |
|---|---|---|
| Name | `runner-01` | Follows `<service>-XX` convention (`naming.md`) |
| VM ID | 205 | Next free ID |
| IP | `*.*.*.*` | Next free static on VLAN 27 |
| Form | VM, Debian 12 cloud-init (same template as `homeautomation-01`/`k3s-01`) | See isolation discussion above |
| vCPU | 2, `host` type, no affinity pinning | Bursty, not latency-sensitive — same reasoning as `k3s-01` |
| RAM | 2048 MB | GitHub Actions runner + Terraform + Ansible are light (a few hundred MB RSS in practice) |
| Disk | 32 GB, single `scsi0` | OS + runner binary + provider/collection caches + repo checkouts |

**Open dial:** if the runner ever builds/pushes container images (e.g. for
the k3s data-lab stack), Docker layer caching eats disk fast and 32 GB gets
tight. Grow the disk or add a second `scsi1` volume for build cache at that
point — same split pattern as `k3s-01`'s OS/PV disks. Not needed for the
Terraform+Ansible use case this is starting from.

## Terraform state

No remote backend today — `terraform.tfstate` lives only on the Mac
(gitignored), which the runner can't use as-is. Two options, not yet decided:

1. **Runner becomes the sole executor.** State lives on `runner-01`'s disk,
   backed up periodically (e.g. to TrueNAS). Simplest, no backend migration.
2. **Remote backend on TrueNAS.** MinIO app (S3-compatible) or an NFS mount,
   so state isn't trapped on one box and both the runner and a laptop could
   `plan`/`apply` against the same state. More moving parts; only worth it if
   applying from multiple places is actually needed.

Leaning towards (1) to start — single-host, sequential applies, no real
locking requirement yet.

## Secrets

Not either/or with the current local files — two patterns considered:

1. **Dual copies.** Keep `terraform.tfvars` / `.vault_pass` / SSH key on the
   Mac as-is for manual runs; separately store the same values as GitHub
   encrypted secrets, injected into the job environment at runtime and never
   persisted to disk outside the job. Simplest, but the two copies can drift
   (rotate a credential in one place, forget the other).
2. **`sops` + `age`, single source of truth.** Encrypt the same files with
   `sops` (age backend), commit the encrypted blobs to the repo. Both the Mac
   and `runner-01` hold a copy of the same age private key and decrypt from
   the one committed source — no drift, and GitHub's secret store never sees
   plaintext. Slightly more setup.

Leaning towards (2) — removes the sync problem permanently rather than
trading it for a different one, and keeps secret custody off GitHub's cloud
store.

## GitHub Actions networking (no inbound available)

Not a blocker. Self-hosted GitHub Actions runners are **outbound-only** — the
runner process long-polls GitHub's API over HTTPS asking for work; GitHub
never opens a connection to the runner. No port-forward or public IP needed,
same model as any outbound HTTPS client.

Alternative considered: Gitea/Forgejo Actions for a fully self-hosted control
plane too. Rejected for now — would mean also hosting (or mirroring) the git
remote instead of GitHub, a bigger change for limited benefit given the repo
is already on GitHub.

## Secrets vault / config provider — deferred

Considered co-locating a general-purpose secrets vault (HashiCorp
Vault/OpenBao, Infisical) and a non-secret config store (Consul-style) on
this VM. Decision: **wait for an actual consumer.**

- The runner's own 3 secrets are already handled by the pattern above — no
  vault service needed for that.
- The real future consumer is the planned k3s data-lab (Postgres, Argo/
  Dagster — see `k3s-node-plan.md`). Once that lands, its secrets are more
  naturally handled in-cluster (native Kubernetes `Secret`s, graduating to
  External Secrets Operator only if needed) rather than by a standalone vault
  VM built ahead of any real requirement.
- If a vault is eventually justified, note that stock HashiCorp Vault/OpenBao
  need manual unsealing after every restart without cloud KMS auto-unseal
  (not available in a pure homelab) — Infisical or `sops`+`age` avoid that
  operational friction.
- A config provider (non-secret, e.g. Consul KV) has no concrete consumer
  yet either — deploy-time config is already served fine by git-tracked
  variables/host tables. Only justified once something reads config live at
  runtime without a redeploy.

## Open questions (not yet decided)

- **Workflow trigger model:** push-to-main runs everything, or PR-gated
  (`plan` on PR, `apply` on merge)? Given solo/homelab use, a lighter model
  than full plan/apply-approval may be enough.
- **Blast radius per run:** re-run the entire deployment on every push, or
  scope to what changed (path filters, e.g. touching
  `ansible/roles/jellyfin/` only re-runs `jellyfin.yml`)? Full-run is simpler; scoped
  is safer as more services are added.
- **Bootstrap problem:** the runner VM must itself be created by Terraform/
  Ansible, but CI can't provision the box it will later run on. First
  provisioning of `runner-01` has to happen manually (or from the Mac)
  before CI can take over subsequent runs.

## Implementation checklist

Nothing started — captured here for when this moves from discussion to
provisioning.

1. ⬜ Terraform: `vm_runner` resource in `terraform/pve-01/main.tf` (VM 205,
   `*.*.*.*`, spec above). First apply must be manual (bootstrap problem).
2. ⬜ Decide + implement secrets pattern (dual-copy vs `sops`+`age`).
3. ⬜ Decide + implement state pattern (local-on-runner vs TrueNAS remote
   backend).
4. ⬜ Install/register GitHub Actions self-hosted runner on `runner-01`.
5. ⬜ Write workflow YAML — trigger model and path-scoping TBD (see Open
   questions).
6. ⬜ Ansible: `ci_runner` role (Terraform/Ansible/gh-runner tooling install).

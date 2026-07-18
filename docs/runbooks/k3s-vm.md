# k3s Node VM — pve-01

## What was done

Provisioned `k3s-01` as a Debian 12 VM (ID 204) on pve-01 via Terraform and
installed a single-node k3s cluster via Ansible. The cluster serves two workload
classes: stable home services (candidates migrate over time) and data-platform
learning projects (Postgres, Redpanda, Dagster, pandas jobs).

Design and sizing rationale: [`docs/architecture/k3s-node-plan.md`](../architecture/k3s-node-plan.md).

Built and verified 2026-07-18: node Ready (k3s v1.36.2), PVC smoke test passed,
node-exporter scraped by Prometheus.

---

## File layout

```
terraform/pve-01/
  variables.tf              k3s_vm_ip (*.*.*.*/24), k3s_vm_id (204)
  main.tf                   proxmox_virtual_environment_vm "vm_k3s" (VLAN 27)
                            scsi0 40 GB (OS) + scsi1 150 GB (PV data disk)

ansible/
  inventory/hosts.yml       k3s-01 in pve_lxc group — *.*.*.*
                            (group membership auto-adds the Prometheus node target)
  playbooks/k3s.yml         entry-point playbook — k3s + node_exporter roles
  roles/k3s/
    defaults/main.yml       k3s_channel, k3s_data_disk, k3s_data_mount,
                            k3s_kubeconfig_local_path
    tasks/main.yml          QoL (PS1, UseDNS), prerequisites (qemu-guest-agent,
                            nfs-common, open-iscsi), data disk mkfs+mount,
                            k3s config + install, kubeconfig fetch
    handlers/main.yml       Restart sshd, Restart k3s
```

The `common` role is deliberately **not** applied: it installs Docker, and k3s
runs its own containerd — two container runtimes on one host is confusion
waiting to happen. The role carries common's QoL tasks itself.

---

## Deploy order

### 1. Provision the VM (Terraform)

Requires the Debian 12 cloud-init template (ID 9000) on pve-01 — creation steps
are in `docs/runbooks/homeautomation-vm.md` and the `main.tf` comment.

```bash
cd terraform/pve-01
terraform apply
```

Clones the template into VM 204, injects SSH key + static IP via cloud-init,
resizes scsi0 to 40 GB, and attaches the 150 GB scsi1 data disk.

**Expected warning:** `timeout while waiting for the QEMU agent` — the Debian
cloud image doesn't ship `qemu-guest-agent`; Ansible installs it in the next
step. The apply still succeeds.

No post-apply CPU pinning: `homeautomation-01` owns E-cores 12–19; k3s
deliberately floats across the scheduler for P-core bursts.

### 2. Configure the node (Ansible)

```bash
cd ansible
ansible-playbook playbooks/k3s.yml
```

Ansible will:
- Install prerequisites incl. `qemu-guest-agent` (fixes Proxmox IP/status display)
- Format `/dev/sdb` (scsi1) as ext4 and mount it at `/var/lib/rancher/k3s/storage`
  — the local-path provisioner's default directory, so all PVs land on the data disk
- Write `/etc/rancher/k3s/config.yaml` (node-name, tls-san) and install k3s
  (stable channel) via the official script
- Wait for the node to become Ready
- Copy the kubeconfig to `~/.kube/k3s-01.yaml` on your Mac with the server IP
  substituted

### 3. Register the node in Prometheus

```bash
ansible-playbook playbooks/monitoring.yml
```

Re-templates `prometheus.yml` — the `node` job iterates the `pve_lxc` inventory
group, so `k3s-01:9100` appears automatically.

### 4. Verify

```bash
export KUBECONFIG=~/.kube/k3s-01.yaml
kubectl get nodes            # k3s-01  Ready  control-plane
kubectl get pods -A          # coredns, traefik, local-path-provisioner, metrics-server all Running
curl -s 'http://*.*.*.*:9090/api/v1/targets?state=active' | grep -o '*.*.*.*:9100[^"]*'
```

---

## Smoke test — try it yourself

End-to-end proof that dynamic volume provisioning works and PVs land on the
dedicated 150 GB data disk. Run from your Mac:

```bash
export KUBECONFIG=~/.kube/k3s-01.yaml

kubectl apply -f - <<'EOF'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: smoke-test
spec:
  accessModes: [ReadWriteOnce]
  resources: { requests: { storage: 1Gi } }
---
apiVersion: v1
kind: Pod
metadata:
  name: smoke-test
spec:
  restartPolicy: Never
  containers:
    - name: writer
      image: busybox
      command: ["sh", "-c", "echo homecenter > /data/hello && cat /data/hello"]
      volumeMounts: [{ name: vol, mountPath: /data }]
  volumes:
    - name: vol
      persistentVolumeClaim: { claimName: smoke-test }
EOF

# Pod runs once, writes to the PV, prints the file, exits
kubectl wait --for=jsonpath='{.status.phase}'=Succeeded pod/smoke-test --timeout=120s
kubectl logs smoke-test          # → homecenter
kubectl get pvc smoke-test       # → Bound

# Prove the volume physically lives on the data disk (/dev/sdb)
ssh -i ~/.ssh/homelab_id ***@*.*.*.* 'ls /var/lib/rancher/k3s/storage/'
# → pvc-<uuid>_default_smoke-test

# Clean up (reclaim policy is Delete — the PV directory is removed too)
kubectl delete pod/smoke-test pvc/smoke-test
```

Things worth noticing while it runs:
- The PVC sits in `Pending` until the pod exists — the storage class uses
  `WaitForFirstConsumer`, so the volume is only provisioned where (and when) a
  consumer is scheduled.
- `kubectl describe pvc smoke-test` shows the provisioning events.

---

## Key decisions

| Decision | Value | Reason |
|---|---|---|
| VM type | Full VM (not LXC) | k3s in LXC fights cgroups/overlayfs even privileged |
| VLAN | 27 — internal | Cluster + Ansible + kubectl need unrestricted LAN access |
| VM ID / IP | `204` / `*.*.*.*` | Sequential after homeautomation-01 |
| CPU | 8 vCPU, `host` type, no pinning | AVX for numpy/pandas; no live migration on single host; E-cores belong to homeautomation-01 |
| RAM | 16 GB dedicated, no ballooning | k8s memory accounting needs stable totals; ~** GB host headroom remains |
| Disks | 40 GB OS + 150 GB data (thin) | PVs isolated from OS disk; grow-only, so thin + generous |
| PV storage | local-path on data disk | Zero-config, fits single node; data disk mounted at provisioner default path |
| Ingress / LB | traefik + klipper (k3s defaults) | No reason to deviate on a single node |
| k3s version | `stable` channel | Single-node homelab; pin via `k3s_channel` if reproducibility ever matters |
| No Docker | k3s containerd only | Avoids two runtimes; `common` role skipped |
| Future storage tier | TrueNAS + democratic-csi | Spare 512 GB SATA SSD; replaceable data only (TrueNAS is a VM on the same host) |

---

## Day-2 operations

### kubectl from the Mac

```bash
export KUBECONFIG=~/.kube/k3s-01.yaml   # or pass --kubeconfig per command
kubectl get nodes -o wide
```

### Upgrading k3s

Re-running the installer upgrades in place (config in
`/etc/rancher/k3s/config.yaml` is preserved; single node = brief API downtime,
workloads keep running):

```bash
ssh -i ~/.ssh/homelab_id ***@*.*.*.* \
  'INSTALL_K3S_CHANNEL=stable /usr/local/bin/k3s-install.sh'
```

### Service control on the node

```bash
systemctl status k3s          # server logs: journalctl -u k3s -f
k3s kubectl get pods -A       # kubectl always available on the node itself
k3s check-config              # sanity-check kernel/cgroup prerequisites
```

### Disk pressure

PVs live on `/dev/sdb` (`df -h /var/lib/rancher/k3s/storage`); images and
containerd state live on the 40 GB root disk. If either runs hot: grow the
Proxmox disk (`qm resize 204 scsi0|scsi1 +20G`), then inside the VM grow the
partition/filesystem. kubelet starts evicting pods at 85% imagefs usage.

---

## Troubleshooting

- **Node NotReady after VM restart** — `journalctl -u k3s -e` on the node;
  most common cause is the data disk missing from fstab mount (`mount -a`).
- **PVC stuck Pending** — no consumer pod yet (`WaitForFirstConsumer` is
  normal), or the local-path provisioner pod is down: `kubectl -n kube-system
  get pods | grep local-path`.
- **kubectl connection refused from Mac** — k3s API is `*.*.*.*:6443`;
  check the service is up and the kubeconfig points at the VM IP, not 127.0.0.1.
- **Proxmox shows no IP for VM 204** — `qemu-guest-agent` not running inside
  the VM; re-run the playbook.

---

## Pre-flight checklist (fresh deploy)

- [ ] Debian 12 cloud-init template (ID 9000) exists on pve-01: `qm list`
- [ ] VM ID `204` is free and IP `*.*.*.*` is not in use: `ping -c1 *.*.*.*`
- [ ] SSH key set in `terraform.tfvars`
- [ ] ~190 GB nominal free on `local-lvm`: `pvesm status`

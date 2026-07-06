# VLAN Fixup Systemd Service — pve-01

## Problem

The `bpg/proxmox` Terraform provider does not persist bridge VLAN assignments for
LXC veth interfaces. After every reboot (or `terraform apply`), each container's
veth interface loses its `PVID Egress Untagged` assignment for VLAN 27, breaking
container networking.

## Solution

A systemd oneshot service (`vlan-fixup.service`) deployed via Ansible runs on pve-01
after boot. It reads all LXC configs in `/etc/pve/lxc/*.conf`, extracts the VLAN tag
from each container's `net0` line, and re-applies the bridge VLAN assignment via
`bridge vlan add`.

The script is fully dynamic — no hardcoded container IDs. Adding or removing a
container only requires re-running the Ansible playbook.

## Ansible Playbook

**Role:** `ansible/roles/pve_vlan_fixup`
**Playbook:** `ansible/playbooks/pve-vlan-fixup.yml`
**Target host:** `pve-01` (`*.*.*.***`) in the `proxmox_hosts` inventory group

### Deploy / update the service

```bash
ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/pve-vlan-fixup.yml
```

Re-run this after adding or removing LXC containers so the service script reflects
the current container state.

## Installed Files on pve-01

| File | Description |
|---|---|
| `/usr/local/sbin/vlan-fixup.sh` | Script that applies bridge VLAN assignments |
| `/etc/systemd/system/vlan-fixup.service` | Systemd unit that runs the script on boot |

## How the Script Works

For each `/etc/pve/lxc/<id>.conf`:

1. Extracts the VLAN tag from the `net0:` line (`tag=<vlan>`)
2. Checks if the veth interface (`veth<id>i0`) exists — skips if the container is stopped
3. Runs `bridge vlan add dev veth<id>i0 vid <vlan> pvid untagged`

## Current Containers (as of last Ansible run)

| Container | CT ID | IP | VLAN | veth interface |
|---|---|---|---|---|
| nut-01 | 200 | *.*.*.*/24 | 27 | veth200i0 |
| monitoring-01 | 201 | *.*.*.*/24 | 27 | veth201i0 |
| plex-01 | 202 | *.*.*.*/24 | 27 | veth202i0 |
| homeautomation-01 | 203 | *.*.*.*/24 | 39 | — (VM, not LXC) |

## Systemd Service Details

The service is ordered after `pve-guests.target` — the Proxmox target reached once
all `start_on_boot` containers have started — so veth interfaces are guaranteed to
exist before the script runs.

```
After=network.target pve-guests.target
Wants=pve-guests.target
Type=oneshot
RemainAfterExit=yes
```

## Verification

### Check service status

```bash
systemctl status vlan-fixup
```

### Check logs

```bash
journalctl -t vlan-fixup
```

Expected output per container:

```
vlan-fixup: applied VLAN 27 to veth200i0 (CT 200)
vlan-fixup: applied VLAN 27 to veth201i0 (CT 201)
vlan-fixup: applied VLAN 27 to veth202i0 (CT 202)
vlan-fixup: applied VLAN 27 to veth203i0 (CT 203)
```

### Verify bridge VLAN assignments

```bash
bridge vlan show dev veth200i0
bridge vlan show dev veth201i0
bridge vlan show dev veth202i0
bridge vlan show dev veth203i0
```

Each should show:

```
port              vlan-id
veth<id>i0        27 PVID Egress Untagged
```

### Run the fix manually (without rebooting)

```bash
/usr/local/sbin/vlan-fixup.sh
```

## Runbook: After terraform apply

1. Verify containers are running: `pct list`
2. Run the fixup script manually: `/usr/local/sbin/vlan-fixup.sh`
3. Confirm connectivity from inside a container: `ping *.*.*.1`

## Runbook: Adding a new LXC container

1. Add container to Terraform and apply
2. Re-run the Ansible playbook — the script regenerates automatically
3. Run the fixup script manually for the new container or reboot pve-01

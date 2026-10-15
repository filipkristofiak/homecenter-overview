# VLAN Fixup Systemd Service — pve-01

## Historical motivation

The role was written to restore LXC bridge VLAN assignments reportedly lost
after reboot or Terraform apply. That failure has **not** been reproduced on
the current host: on 2026-10-10, CTs 200, 201, and 205 each had VLAN 27
`PVID Egress Untagged` despite the service not being installed.

## Implementation status

The Ansible role implements a systemd oneshot service (`vlan-fixup.service`)
that reads LXC configs in `/etc/pve/lxc/*.conf`, extracts each `net0` VLAN tag,
and re-applies bridge VLAN assignments via `bridge vlan add`. The script is
dynamic; no hardcoded container IDs.

**Not deployed on pve-01 as checked on 2026-10-10:** `systemctl is-enabled
vlan-fixup.service` returned `not-found`. The running LXCs nevertheless had
correct VLAN assignments. Do not deploy this role without first observing a
lost assignment after reboot or apply. Use the
[manual checks](pve-01-network-fix.md#post-apply-verify-lxc-vlan-assignments)
if one is missing.

## Ansible Playbook

**Role:** `ansible/roles/pve_vlan_fixup`
**Playbook:** `ansible/playbooks/pve-vlan-fixup.yml`
**Target host:** `pve-01` (`*.*.*.*`) in the `proxmox_hosts` inventory group

### Deploy only if the problem recurs

```bash
ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/pve-vlan-fixup.yml
```

The script reads LXC configs at runtime; adding a container does not require
regenerating the script.

## Files installed by the role

| File | Description |
|---|---|
| `/usr/local/sbin/vlan-fixup.sh` | Script that applies bridge VLAN assignments |
| `/etc/systemd/system/vlan-fixup.service` | Systemd unit that runs the script on boot |

## How the Script Works

For each `/etc/pve/lxc/<id>.conf`:

1. Extracts the VLAN tag from the `net0:` line (`tag=<vlan>`)
2. Checks if the veth interface (`veth<id>i0`) exists — skips if the container is stopped
3. Runs `bridge vlan add dev veth<id>i0 vid <vlan> pvid untagged`

## Current containers (checked 2026-10-10)

| Container | CT ID | IP | VLAN | veth interface |
|---|---|---|---|---|
| nut-01 | 200 | *.*.*.*/24 | 27 | veth200i0 |
| monitoring-01 | 201 | *.*.*.*/24 | 27 | veth201i0 |
| jellyfin | 205 | *.*.*.*/24 | 27 | veth205i0 |
| homeautomation-01 | 203 | *.*.*.*/24 | 39 | — (VM, not LXC) |

## Systemd Service Details

When installed, the service is ordered after `pve-guests.target`, reached after
the guests are started, so it can find their veth interfaces.

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

Expected output for the three current LXCs (after the service is deployed):

```
vlan-fixup: applied VLAN 27 to veth200i0 (CT 200)
vlan-fixup: applied VLAN 27 to veth201i0 (CT 201)
vlan-fixup: applied VLAN 27 to veth205i0 (CT 205)
```

### Verify bridge VLAN assignments

```bash
bridge vlan show dev veth200i0
bridge vlan show dev veth201i0
bridge vlan show dev veth205i0
```

Each should show:

```
port              vlan-id
veth<id>i0        27 PVID Egress Untagged
```

### Run the fix manually (after deploying the role)

```bash
/usr/local/sbin/vlan-fixup.sh
```

## Runbook: After Terraform apply or adding an LXC

1. Verify running containers with `pct list`.
2. Inspect their bridge assignments using the
   [manual checks](pve-01-network-fix.md#post-apply-verify-lxc-vlan-assignments).
3. If an assignment is missing, correct that veth manually and verify container
   connectivity to `*.*.*.1`. Consider deploying the role only if the
   problem recurs; if installed, its script reads LXC configs dynamically.

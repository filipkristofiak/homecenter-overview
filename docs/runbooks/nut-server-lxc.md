# NUT Server LXC — pve-01

## What was done

Added Terraform and Ansible drafts to provision and configure a NUT (Network UPS Tools)
server as a privileged LXC container on pve-01. The container monitors the APC UPS
connected via USB to pve-01 and exposes the UPS status over the network (port 3493),
enabling integrations such as Home Assistant.

No infrastructure was changed yet — these are drafts ready to apply.

---

## File layout

```
terraform/pve-01/
  providers.tf              bpg/proxmox provider ~0.76
  variables.tf              endpoint, api_token, ssh key, IP, CT ID
  main.tf                   LXC container resource (nut-01, VLAN 27)
  terraform.tfvars.example  copy → terraform.tfvars and fill in secrets

ansible/
  ansible.cfg               sets inventory path and roles path
  inventory/hosts.yml       nut-01 (pve_lxc group) + existing lab-01
  playbooks/nut-server.yml  entry-point playbook
  roles/nut/
    defaults/main.yml       all tunable variables (UPS name, passwords, IP, port)
    tasks/main.yml          install packages, deploy configs, enable services, smoke-test
    handlers/main.yml       per-daemon restarts triggered by config changes
    templates/
      nut.conf.j2           MODE=netserver
      ups.conf.j2           driver=usbhid-ups, port=auto
      upsd.conf.j2          LISTEN 0.0.0.0:3493
      upsd.users.j2         admin + monitor accounts
      upsmon.conf.j2        primary monitor, shutdown command
```

---

## Deploy order

### 1. Provision the container (Terraform)

```bash
cd terraform/pve-01
cp terraform.tfvars.example terraform.tfvars   # fill in real values
terraform init
terraform apply
```

### 2. USB passthrough (manual, one-time)

The bpg/proxmox provider does not yet support raw LXC config entries.
After `terraform apply`, add the following to `/etc/pve/lxc/200.conf` on pve-01:

```
lxc.cgroup2.devices.allow: c 189:* rwm
lxc.mount.entry: /dev/bus/usb dev/bus/usb none bind,optional,create=dir
```

Restart the container:

```bash
pct stop 200 && pct start 200
```

Verify the USB device is visible inside the container:

```bash
pct enter 200
ls /dev/bus/usb
```

### 3. Configure NUT (Ansible)

```bash
cd ansible
ansible-playbook playbooks/nut-server.yml
```

Passwords default to `changeme` in `roles/nut/defaults/main.yml`.
Override them via extra vars or ansible-vault before running:

```bash
ansible-playbook playbooks/nut-server.yml \
  -e nut_admin_password=<secret> \
  -e nut_monitor_password=<secret>
```

### 4. Verify

```bash
# from any host on VLAN 27
upsc  apc-ups@*.*.*.*
```

---

## Key decisions

| Decision | Value | Reason |
|---|---|---|
| Container type | Privileged LXC | Required for USB device bind-mount into container |
| CT ID | `200` | First available; change in `terraform.tfvars` if taken |
| Hostname | `nut-01` | Follows `<service>-XX` pattern from naming conventions |
| IP | `*.*.*.*/24` | VLAN 27, static; pick any free address |
| Gateway | `*.*.*.1` | VLAN 27 gateway |
| NUT driver | `usbhid-ups` | Correct driver for APC UPS connected over USB |
| UPS port | `auto` | NUT auto-detects USB HID UPS; no manual path needed |
| NUT mode | `netserver` | Exposes upsd on port 3493 for remote clients (e.g. Home Assistant) |
| OS template | Debian 12 standard | Consistent with rest of homelab direction |
| RAM | 256 MB | NUT is lightweight; increase only if needed |
| Disk | 4 GB | Sufficient for OS + NUT logs |

### Pre-flight checklist

- [ ] Debian 12 template downloaded on pve-01: `pveam update && pveam download local debian-12-standard_12.7-1_amd64.tar.zst`
- [ ] APC UPS visible on pve-01 before provisioning: `lsusb | grep -i apc`
- [ ] CT ID `200` is free on pve-01: `pct list`
- [ ] IP `*.*.*.*` is not in use: `ping -c1 *.*.*.*`
- [ ] SSH key added to `terraform.tfvars`
- [ ] Passwords replaced before running Ansible



## post deployment 2nd play to setup USB permissions

Summary of changes:

- [tasks/main.yml](/ansible/roles/nut/tasks/main.yml) — `nut-driver` → `nut-driver@apc-ups` in the service loop
- [handlers/main.yml](/ansible/roles/nut/handlers/main.yml) — same fix in both handler entries
- [nut-server.yml](/ansible/playbooks/nut-server.yml) — added a second play targeting `pve-01` that deploys `/etc/udev/rules.d/99-apc-ups.rules` with `MODE="0666"` for the APC UPS (vendor ID `051d`) and triggers a udev reload

The udev rule uses APC's USB vendor ID (`051d`). If you need to match more specifically (e.g. by product ID), you can add `ATTR{idProduct}=="..."` to narrow it down.
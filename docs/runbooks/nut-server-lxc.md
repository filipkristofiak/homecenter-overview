# NUT Server LXC — pve-01

NUT monitors the APC UPS on pve-01 through USB passthrough into a privileged LXC; `upsd` serves UPS status on TCP 3493.
`nut-server.yml` also writes the APC udev rule on pve-01 (`99-apc-ups.rules`).

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
pct shutdown 200 && pct start 200
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
upsc apc-ups@*.*.*.*
```

---

## Key decisions

| Decision | Value | Reason |
|---|---|---|
| Container type | Privileged LXC | Required for USB device bind-mount into container |
| NUT driver | `usbhid-ups` | Correct driver for APC UPS connected over USB |
| UPS port | `auto` | NUT auto-detects USB HID UPS; no manual path needed |
| NUT mode | `netserver` | Exposes upsd on port 3493 for remote clients (e.g. Home Assistant) |
| OS template | Debian 12 standard | Consistent with rest of homelab direction |
| RAM | 256 MB | NUT is lightweight; increase only if needed |
| Disk | 4 GB | Sufficient for OS + NUT logs |

### Pre-flight checklist

- [ ] Debian 12 template available on pve-01: [template prerequisites](pve-01-rebuild.md#3-templates-on-pve-01)
- [ ] APC UPS visible on pve-01 before provisioning: `lsusb | grep -i apc`
- [ ] SSH key added to `terraform.tfvars`
- [ ] Passwords replaced before running Ansible

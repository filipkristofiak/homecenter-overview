# pve-01 rebuild

Rebuild order for pve-01 and its guests. Guest identities: [ip-addressing.md](../network/ip-addressing.md).

## 1. Prerequisites on the control machine

- Ensure the `~/.ssh/homelab_id` keypair exists. Key-generation details: [REDACTED].
- Copy `terraform/pve-01/terraform.tfvars.example` to `terraform/pve-01/terraform.tfvars`; fill in the endpoint, API token and SSH public key. Proxmox API-token setup details: [REDACTED].
- Provide `ansible/.vault_pass` for the existing encrypted secrets.
- Run `ansible-galaxy collection install community.docker ansible.posix`.
- Build lab-deck `dist/` first, per [periscope: build and apply](periscope.md#build-and-apply); `monitoring.yml` fails without it.

## 2. Host network and TrueNAS

Apply [pve-01 network](pve-01-network.md), then [TrueNAS rebuild](truenas-vm.md#rebuild). NFS must work before Jellyfin and backups.

## 3. Templates on pve-01

Run as root on pve-01. The LXC filename must match `terraform/pve-01/main.tf`; VM template `9000` serves both guest VMs.

```bash
pveam update && pveam download local debian-12-standard_12.12-1_amd64.tar.zst
wget -P /var/lib/vz/template/iso/ \
  https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2

qm create 9000 --name debian-12-cloudinit --memory 1024 \
  --cores 1 --net0 virtio,bridge=vmbr0 --ostype l26

qm importdisk 9000 \
  /var/lib/vz/template/iso/debian-12-genericcloud-amd64.qcow2 local-lvm

qm set 9000 --scsihw virtio-scsi-pci --scsi0 local-lvm:vm-9000-disk-0 \
  --ide2 local-lvm:cloudinit --boot c --bootdisk scsi0 \
  --agent enabled=1 --serial0 socket --vga serial0

qm template 9000
qm list | grep 9000
```

## 4. Provision guests

Complete [UniFi network setup](unifi-network-pve01.md) for any new VLAN. From the repo root run `cd terraform/pve-01 && terraform init && terraform apply`. Verify on pve-01 with `pct list` (200, 201, 205) and `qm list` (203, 204).

## 5. Post-apply manual steps (pve-01, root)

- [NUT USB passthrough](nut-server-lxc.md#2-usb-passthrough-manual-one-time).
- Enable LXC nesting for CT 201 and 205: commands in the `main.tf` resource comments.
- Pin VM 203 to the E-cores: `qm set 203 --affinity 12-19`.

## 6. Configure services (from ansible/)

1. [pve-01 host](pve-01-host.md): `ansible-playbook playbooks/pve-host.yml`.
2. [Node exporter](node-exporter.md): `ansible-playbook playbooks/node-exporter.yml`.
3. [NUT](nut-server-lxc.md): set real NUT passwords as documented, then `ansible-playbook playbooks/nut-server.yml -e nut_admin_password=<secret> -e nut_monitor_password=<secret>` (replace placeholders with shell-quoted secrets).
4. [PVE exporter token setup](pve-exporter.md#first-time-setup): create the read-only token in the Proxmox UI, then `ansible-vault edit inventory/group_vars/pve_lxc/vault.yml` to store it before monitoring deploys.
5. [Monitoring](monitoring-lxc.md): `ansible-playbook playbooks/monitoring.yml`.
6. [Jellyfin](jellyfin-lxc.md): `ansible-playbook playbooks/jellyfin.yml`.
7. [Home Assistant](homeautomation-vm.md): `ansible-playbook playbooks/homeassistant.yml`.
8. [k3s](k3s-vm.md): `ansible-playbook playbooks/k3s.yml`.

## 7. First-run UI steps

- Complete HA onboarding and add [the MQTT integration](homeautomation-vm.md#5-connect-home-assistant-to-mqtt-once-in-its-ui).
- Log in to Grafana as `admin` with vaulted `grafana_admin_password`; import dashboard `1860` and select the Prometheus datasource.
- In Jellyfin, verify the API-managed libraries and restricted `kodi` playback user.
- Configure [backup storage and job](pve-01-backups.md#set-up-or-re-create).

## 8. Smoke test

```bash
# NUT
upsc [REDACTED] | grep -E "battery|status"

# Prometheus
curl -s http://*.*.*.*:9090/-/healthy

# Grafana
curl -s http://*.*.*.*:3000/api/health

# Prometheus targets (all should be UP)
curl -s 'http://*.*.*.*:9090/api/v1/targets' \
  | python3 -m json.tool | grep '"health"'

# Jellyfin
curl -s -o /dev/null -w "%{http_code}" http://*.*.*.*:8096/health

# Home Assistant
curl -s -o /dev/null -w "%{http_code}" http://*.*.*.*:8123

# k3s
kubectl --kubeconfig ~/.kube/k3s-01.yaml get nodes
```

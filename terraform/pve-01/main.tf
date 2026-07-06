# -----------------------------------------------------------------------------
# Plex Media Server LXC — pve-01
#
# Runs Plex Media Server as a privileged container. Media lives on TrueNAS
# (pool: spinners, dataset: media) and is NFS-mounted at /mnt/media inside
# the container.
#
# NFS note:
#   Ansible mounts the TrueNAS NFS share via /etc/fstab with _netdev so the
#   mount waits for the network. The TrueNAS NFS export must allow the plex
#   user's UID (default 972) or use mapall — see the runbook for details.
#
# Hardware transcoding note (optional, future):
#   To enable Intel Quick Sync GPU passthrough for transcoding, add after apply:
#     lxc.cgroup2.devices.allow: c 226:* rwm
#     lxc.mount.entry: /dev/dri dev/dri none bind,optional,create=dir
#   Then restart the container: pct restart <id>
# -----------------------------------------------------------------------------

resource "proxmox_virtual_environment_container" "lxc_plex" {
  description = "Plex Media Server – streams media from TrueNAS NFS (VLAN *)"
  node_name   = "pve-01"
  vm_id       = var.plex_lxc_id

  tags = ["plex", "media", "infra"]

  start_on_boot = true
  started       = true
  unprivileged  = false # privileged for NFS mounts and optional GPU passthrough

  # NOTE: nesting=1 must be set manually after apply — Proxmox only allows feature flag changes
  # for privileged containers via root@pam, not API tokens:
  #   pct set 202 --features nesting=1 && pct restart 202
  lifecycle {
    ignore_changes = [features]
  }

  cpu {
    cores = 2 # software transcoding is CPU-heavy; increase for 4K
  }

  memory {
    dedicated = 2048 # Plex recommends ≥1 GB; 2 GB comfortable for 1080p
  }

  disk {
    datastore_id = "local-lvm"
    size         = 16 # OS + Plex metadata, thumbnails, transcode temp
  }

  initialization {
    hostname = "plex-01"

    ip_config {
      ipv4 {
        address = var.plex_lxc_ip
        gateway = "*.*.*.*"
      }
    }

    user_account {
      keys = [var.ssh_public_key]
    }
  }

  network_interface {
    name    = "eth0"
    bridge  = "vmbr0"
    vlan_id = *
  }

  operating_system {
    template_file_id = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    type             = "debian"
  }
}

# -----------------------------------------------------------------------------
# Home Automation VM — pve-01
#
# Runs the full home automation stack (HA + Mosquitto + Zigbee2MQTT) as Docker
# containers managed by docker-compose, inside a dedicated Debian 12 VM.
#
# Placed on VLAN * — isolated zone. Cross-VLAN firewall rules in
# UniFi allow only: TCP 8123 inbound (UI), TCP 6638 to SLZB-06M, TCP 22 for
# Ansible, TCP 9100 for Prometheus node-exporter.
#
# Pre-requisite: a Debian 12 cloud-init template must exist on pve-01.
# Create it once from the Proxmox shell:
#
#   wget -P /var/lib/vz/template/iso/ \
#     https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2
#   qm create <var.debian12_template_id> --name debian-12-cloudinit --memory 1024 \
#     --cores 1 --net0 virtio,bridge=vmbr0 --ostype l26
#   qm importdisk <var.debian12_template_id> \
#     /var/lib/vz/template/iso/debian-12-genericcloud-amd64.qcow2 local-lvm
#   qm set <var.debian12_template_id> --scsihw virtio-scsi-pci \
#     --scsi0 local-lvm:vm-<id>-disk-0 --ide2 local-lvm:cloudinit \
#     --boot c --bootdisk scsi0 --agent enabled=1 --serial0 socket --vga serial0
#   qm template <var.debian12_template_id>
#
# Home Automation UI → http://***:8123
# -----------------------------------------------------------------------------

resource "proxmox_virtual_environment_vm" "vm_homeautomation" {
  description = "Home automation stack – HA + Mosquitto + Zigbee2MQTT via docker-compose (VLAN *)"
  node_name   = "pve-01"
  vm_id       = var.homeautomation_vm_id
  name        = "homeautomation-01"

  tags = ["homeassistant", "smarthome", "infra"]

  started  = true
  on_boot  = true

  clone {
    vm_id = var.debian12_template_id
    full  = true
  }

  cpu {
    cores = 2
    type  = "x86-64-v2-AES"
    # Pin to E-cores (efficiency cores 12–19) after apply:
    # qm set 203 --affinity 12-19
  }

  memory {
    dedicated = 2048
  }

  disk {
    datastore_id = "local-lvm"
    interface    = "scsi0"
    size         = 32   # OS + Docker images + HA config + recorder DB
    discard      = "on"
    file_format  = "raw"
  }

  initialization {
    ip_config {
      ipv4 {
        address = var.homeautomation_vm_ip
        gateway = "*.*.*.*"
      }
    }

    user_account {
      username = "root"
      keys     = [var.ssh_public_key]
    }
  }

  network_device {
    bridge  = "vmbr0"
    model   = "virtio"
    vlan_id = *
  }

  agent {
    enabled = true
  }
}

# -----------------------------------------------------------------------------
# Monitoring LXC — pve-01
#
# Runs Grafana and Prometheus as Docker containers managed by docker-compose.
# Grafana → http://<ip>:3000   Prometheus → http://<ip>:9090
#
# Docker-in-LXC note:
#   Container runs privileged so the Docker daemon can manage its own cgroups
#   and network namespaces without restriction.
# -----------------------------------------------------------------------------

resource "proxmox_virtual_environment_container" "lxc_monitoring" {
  description = "Monitoring stack – Grafana + Prometheus via docker-compose (VLAN *)"
  node_name   = "pve-01"
  vm_id       = var.monitoring_lxc_id

  tags = ["grafana", "prometheus", "monitoring", "infra"]

  start_on_boot = true
  started       = true
  unprivileged  = false # privileged required for Docker daemon

  # NOTE: nesting=1 must be set manually after apply — Proxmox only allows feature flag changes
  # for privileged containers via root@pam, not API tokens:
  #   pct set 201 --features nesting=1 && pct restart 201
  lifecycle {
    ignore_changes = [features]
  }

  cpu {
    cores = 2
  }

  memory {
    dedicated = 1024 # Prometheus TSDB + Grafana + OS headroom
  }

  disk {
    datastore_id = "local-lvm"
    size         = 20 # Prometheus data retention; increase for longer retention
  }

  initialization {
    hostname = "monitoring-01"

    ip_config {
      ipv4 {
        address = var.monitoring_lxc_ip
        gateway = "*.*.*.*"
      }
    }

    user_account {
      keys = [var.ssh_public_key]
    }
  }

  network_interface {
    name    = "eth0"
    bridge  = "vmbr0"
    vlan_id = *
  }

  operating_system {
    template_file_id = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    type             = "debian"
  }
}


# -----------------------------------------------------------------------------
# NUT Server LXC — pve-01
#
# Hosts the NUT (Network UPS Tools) daemon monitoring the APC UPS via USB.
# Runs as a privileged container so the host USB device can be bind-mounted.
#
# USB passthrough note:
#   The bpg/proxmox provider does not yet expose raw LXC config entries.
#   After `terraform apply`, add the following lines to /etc/pve/lxc/<id>.conf
#   on pve-01 (replace <id> with var.nut_lxc_id, default 200):
#
#     lxc.cgroup2.devices.allow: c 189:* rwm
#     lxc.mount.entry: /dev/bus/usb dev/bus/usb none bind,optional,create=dir
#
#   Then restart the container:  pct restart 200
#   Verify device visible inside: ls /dev/bus/usb
# -----------------------------------------------------------------------------

resource "proxmox_virtual_environment_container" "lxc_nut_server" {
  description = "NUT server – APC UPS monitoring (VLAN *)"
  node_name   = "pve-01"
  vm_id       = var.nut_lxc_id

  tags = ["nut", "ups", "infra"]

  start_on_boot = true
  started       = true
  unprivileged  = false # privileged required for USB device passthrough

  # NOTE: nesting=1 must be set manually after apply — Proxmox only allows feature flag changes
  # for privileged containers via root@pam, not API tokens:
  #   pct set 200 --features nesting=1 && pct restart 200
  lifecycle {
    ignore_changes = [features]
  }

  cpu {
    cores = 1
  }

  memory {
    dedicated = 256
  }

  disk {
    datastore_id = "local-lvm"
    size         = 4
  }

  initialization {
    hostname = "nut-01"

    ip_config {
      ipv4 {
        address = var.nut_lxc_ip
        gateway = "*.*.*.*"
      }
    }

    user_account {
      keys = [var.ssh_public_key]
    }
  }

  network_interface {
    name    = "eth0"
    bridge  = "vmbr0"
    vlan_id = *
  }

  operating_system {
    # Download the template first on pve-01:
    #   pveam update && pveam download local debian-12-standard_12.12-1_amd64.tar.zst
    template_file_id = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
    type             = "debian"
  }
}

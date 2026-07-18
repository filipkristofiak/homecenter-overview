variable "proxmox_endpoint" {
  description = "Proxmox API endpoint, e.g. https://***:8006/"
  type        = string
}

variable "proxmox_api_token" {
  description = "Proxmox API token — format: USER@REALM!TOKEN_ID=SECRET"
  type        = string
  sensitive   = true
}

variable "ssh_public_key" {
  description = "SSH public key injected into the LXC container for root access"
  type        = string
}

variable "nut_lxc_ip" {
  description = "Static IPv4 address for the NUT LXC container (CIDR), on VLAN *"
  type        = string
  default     = "*.*.*.*/24"
}

variable "nut_lxc_id" {
  description = "Proxmox VM/CT ID for the NUT container"
  type        = number
  default     = 200
}

variable "monitoring_lxc_ip" {
  description = "Static IPv4 address for the monitoring LXC container (CIDR), on VLAN *"
  type        = string
  default     = "*.*.*.*/24"
}

variable "monitoring_lxc_id" {
  description = "Proxmox VM/CT ID for the monitoring container"
  type        = number
  default     = 201
}

variable "plex_lxc_ip" {
  description = "Static IPv4 address for the Plex LXC container (CIDR), on VLAN *"
  type        = string
  default     = "*.*.*.*/24"
}

variable "plex_lxc_id" {
  description = "Proxmox VM/CT ID for the Plex container"
  type        = number
  default     = 202
}

variable "plex_truenas_nfs_server" {
  description = "TrueNAS IP address serving the NFS media share"
  type        = string
  default     = "*.*.*.*"
}

variable "homeautomation_vm_ip" {
  description = "Static IPv4 address for the home automation VM (CIDR), on VLAN *"
  type        = string
  default     = "*.*.*.*/24"
}

variable "homeautomation_vm_id" {
  description = "Proxmox VM ID for the home automation VM"
  type        = number
  default     = 203
}

variable "k3s_vm_ip" {
  description = "Static IPv4 address for the k3s node VM (CIDR), on VLAN *"
  type        = string
  default     = "*.*.*.*/24"
}

variable "k3s_vm_id" {
  description = "Proxmox VM ID for the k3s node VM"
  type        = number
  default     = 204
}

variable "debian12_template_id" {
  description = "Proxmox VM ID of the Debian 12 cloud-init template to clone from (see main.tf comment for setup steps)"
  type        = number
  default     = 9000
}

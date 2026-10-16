# UniFi Network — pve-01 Deployment Notes

Use this checklist when provisioning a new guest or adding a VLAN to pve-01.

Subnets and allocations: [IP addressing](../network/ip-addressing.md).
`network/unifi/configs/` captures only the first 25 firewall policies; it is not
a complete firewall audit.

## New guest or new VLAN

1. Claim the next free IP and CT/VM ID from [ip-addressing.md](../network/ip-addressing.md).
2. Set `vlan_id` on the Terraform NIC.
3. If the VLAN is new to pve-01, add it to `bridge-vids`
   ([pve-01-network.md](pve-01-network.md)) and to the tagged list of the pve-01 switch port.
4. **Remove the VLAN from UDR7 Port 2's excluded networks**. Port 2 is the active
   switch uplink; an excluded VLAN is silently dropped, so guests get no DHCP lease
   and can't ARP the gateway (see the
   [VLAN 39 outage journal](../journal/2026-07-20-homeautomation-vm-vlan6-outage.md)).
5. Add explicit zone policies for every port the guest must reach across zones.
   For example, an IoT device initiating a connection to Home Assistant on VLAN 39
   needs a targeted allow to `*.*.*.*` and the required port, not the whole zone.
6. mDNS doesn't cross VLANs; enable the UniFi mDNS proxy if discovery is needed.
7. Verify a DHCP/static address, gateway ARP and service reachability.
8. Update [ip-addressing.md](../network/ip-addressing.md) only.

# pve-01 network

Addresses: [IP addressing](../network/ip-addressing.md).

## Host bridge

```
iface nic0 inet manual

auto vmbr0
iface vmbr0 inet manual
    bridge-ports nic0
    bridge-stp off
    bridge-fd 0
    bridge-vlan-aware yes
    bridge-vids 27 39

auto vmbr0.27
iface vmbr0.27 inet static
    address *.*.*.*/24
    gateway *.*.*.1
```

`bridge-vids` must list every VLAN a guest uses; add the VLAN here before creating a guest on it.

## Switch port

USW2.5 Port 3 ("Homelab") uses native VLAN 23 and tagged VLANs 27 and 39.

Remove each new VLAN from UDR7 Port 2's excluded networks; see the [UniFi network checklist](unifi-network-pve01.md).

## Check LXC VLAN tags

Check after a reboot or apply; fix only an assignment that is actually missing:

```bash
pct list  # current LXCs: 200, 201, 205; VM 203 is not an LXC
bridge vlan show dev veth200i0
bridge vlan show dev veth201i0
bridge vlan show dev veth205i0

# Run only the command(s) for running containers missing VLAN 27:
bridge vlan add dev veth200i0 vid 27 pvid untagged
bridge vlan add dev veth201i0 vid 27 pvid untagged
bridge vlan add dev veth205i0 vid 27 pvid untagged
```

VM 203 uses VLAN 39 through `vmbr0` and needs no LXC veth command.
The affected container must be running for its veth interface to exist.

## History

[Original trunk fix and later verification](../journal/2026-04-08-pve-01-network-fix.md).

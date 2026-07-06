# LXC SSH Slow Login (~25s delay)

## Symptom

SSH into any privileged LXC takes ~25 seconds before the prompt appears. TCP connect is instant, key auth completes immediately — the delay happens after authentication during session setup.

## Root cause

`pam_systemd.so` is listed as `optional` in `/etc/pam.d/common-session`. On every login it tries to register the session with `systemd-logind` over D-Bus. Inside a privileged LXC without nesting enabled, `systemd-logind` fails to start (`status=226/NAMESPACE` — cannot create cgroup/user namespaces). PAM waits ~25s for a D-Bus response that never comes, then gives up and lets you in.

## Fix

Enable `nesting` on the container. This allows cgroup namespace creation inside the LXC, which lets `systemd-logind` start correctly:

```bash
# on pve-01 — must be run as root, not via API token
pct set <id> --features nesting=1
pct restart <id>
```

Verify `systemd-logind` is now running inside the container:

```bash
systemctl status systemd-logind
```

## Why the obvious fixes didn't work

| Attempted fix | Why it failed |
|---|---|
| `UseDNS no` in `/etc/ssh/sshd_config` | Delay was not DNS — it was PAM |
| `GSSAPIAuthentication no` in sshd_config | Not GSSAPI — it was PAM |
| Commenting out `pam_systemd.so` in `/etc/pam.d/sshd` | sshd PAM uses `@include common-session` which pulls `pam_systemd.so` in after the sshd-specific block — the inline comment had no effect |
| Commenting out `pam_loginuid.so` | Not the culprit |

The actual fix location is `/etc/pam.d/common-session`, but fixing the root cause (nesting) is preferable to disabling PAM modules.

## Terraform note

The `features` block on privileged LXC containers can only be changed via `root@pam` — the Terraform API token (`terraform@pam`) does not have permission. Setting `nesting=1` is a manual post-apply step. All LXC resources in `main.tf` have `lifecycle { ignore_changes = [features] }` to prevent Terraform from attempting to reconcile this field.

## Affected containers

All privileged LXCs: nut-01 (200), monitoring-01 (201), plex-01 (202).

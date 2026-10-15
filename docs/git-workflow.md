# Git workflow

Soft policy for this repo. It applies to humans and agents. Deviate when it makes sense, and say why in the commit body.

## Branches

Never commit directly to `main`. Each logical change gets a short-lived branch from up-to-date `main`:

```
<prefix>/<topic>
```

`topic` is lowercase kebab-case, ≤ 40 chars, and starts with the role/host/tool when that helps (`ha-unprivileged`, `monitoring-drop-nut-job`).

| Prefix | Use for | Example |
|---|---|---|
| `feat/` | New capability: service, role, host, tool, dashboard | `feat/k3s-argocd` |
| `fix/` | Repair broken or wrong behaviour, config, or security posture | `fix/ha-unprivileged` |
| `chore/` | Housekeeping with no behaviour change for users: dead config, version bumps, inventory sync, snapshots | `chore/bump-grafana-12.5` |
| `docs/` | Documentation only: runbooks, architecture, plans | `docs/git-workflow` |
| `refactor/` | Restructure IaC without changing deployed result | `refactor/monitoring-role-vars` |
| `ops/` | Live-infrastructure operations recorded in the repo: migrations, maintenance windows, hardware swaps, incident fixes plus their runbooks | `ops/truenas-disk-swap` |
| `spike/` | Throwaway experiment. Not merged to `main`; redo kept results on a proper branch | `spike/loki-logs` |

One branch = one logical change. If unrelated changes are mixed in the working tree, split them across branches and stage explicit paths.

Older branches (`feature/`, `maintenance/`, `migration/`, `review/`, `test/`, `tools/`, `bckp/`) predate this policy. Leave them as they are and do not rename them.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <summary>

<optional body: why, and how it was applied/verified>
```

- `type`: `feat`, `fix`, `chore`, `docs`, `refactor`, `ops`. It normally matches the branch prefix.
- `scope`: the role, host, or area touched, such as `homeassistant`, `monitoring`, `k3s`, `nut`, `terraform`, `unifi`, `pve`, `truenas`, or `git`. Omit it when the change spans the whole repo.
- `summary`: imperative, lowercase, ≤ 72 chars, and no trailing period.
- Body: explain why the change was needed. For infra changes, include how it was applied (`ansible-playbook playbooks/x.yml`, `terraform apply`) and the check that proved it. If the change is not applied yet, say `not yet applied`.

`main` should describe what is deployed. Merge infra changes after applying and verifying them, or mark them `not yet applied` in the body.

## Merging

Default is local fast-forward only, which keeps history linear:

```bash
git fetch origin
git switch -c <prefix>/<topic> origin/main   # or from up-to-date main
# edit, then stage explicit paths
git add <paths>
git commit
git rebase origin/main                       # only if main moved
git switch main
git merge --ff-only <prefix>/<topic>
git push origin main
git branch -d <prefix>/<topic>
git push origin --delete <prefix>/<topic>    # only if the branch was pushed
```

- Push the branch itself only when work spans sessions or needs a PR.
- Use a GitHub PR (optional) for large, multi-session, or review-worthy changes: `gh pr create`, then `gh pr merge --rebase --delete-branch`.
- Never force-push `main`. Never use `git merge` without `--ff-only` on `main`. If the fast-forward fails, rebase the branch on `origin/main` and retry.
- Use the `origin` remote explicitly.

## Never commit

`terraform/pve-01/terraform.tfvars`, `ansible/.vault_pass`, `tools/unifi/.env`, decrypted vault content, private keys, or Terraform state. `ansible/group_vars/pve_lxc/vault.yml` is committed only when it is ansible-vault encrypted.

## Agents

- Commit only when the user asks.
- Follow this file when creating branches, writing commit messages, and merging.
- Report the branch name, commit hash(es), and the pushed `main` hash.

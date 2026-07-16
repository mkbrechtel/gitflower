# gitflower

A git-based development platform — local-first, git-centric. A Python
**FastAPI** (web UI) + **click** (CLI) application built exclusively on Debian
`python3-*` apt packages.

```bash
sudo apt install python3-fastapi python3-click python3-pygit2 python3-yaml
```

(That's the whole dependency list — plus `python3-pytest` for the tests.
`uvicorn` and `pydantic` arrive as hard dependencies of `python3-fastapi`.)

## The two feature lines

**Branch workflows (per repository).** A pre-push hook engine with a branch
router: ordered rules map branch glob patterns to workflows, and unconfigured
branches are rejected — the rule list is an allow-list. Patterns keep the Go
original's `filepath.Match` semantics (`*` never crosses `/`).

```bash
gitflower init       # write .gitflower/config.yaml with defaults
gitflower install    # install the pre-push hook shim
gitflower config show
```

```yaml
# .gitflower/config.yaml
branch_rules:
- pattern: main
  workflow: protected
- pattern: issues/*
  workflow: issue-tracker
- pattern: releases/v*
  workflow: release-manager
protected_branches:
- pattern: main
  allow_direct_push: false
  require_linear_history: true
  allowed_push_users: []
  require_clean_working_tree: false
```

**Repo hosting + web UI (global).** Bare repositories under a configured
directory, browsable in the browser and clonable read-only over smart-HTTP.

```bash
gitflower create myorg/myproject.git
gitflower list --format table|json|yaml
gitflower web        # serve the UI (default :8747)
```

```yaml
# ~/.config/gitflower/config.yaml (or /etc/gitflower/config.yaml)
repos:
  directory: ./repos/
  scan_depth: 3
  default_branch: main
web:
  address: ":8747"
```

## The API is the frontend

Every browse endpoint serves three representations from the same URL:

| Request | Response |
|---|---|
| browser navigation | full HTML page |
| `Accept: application/json` or `?format=json` | the data as JSON |
| `GF-Fragment: 1` header or `?format=fragment` | the bare HTML fragment |
| `?format=raw` (file views) | raw file bytes |

The UI is native web components — no framework, no build step. Fragments ship
declarative shadow roots, so their styles are browser-scoped; `components.js`
adds htmx-style navigation (link interception + `pushState` + View
Transitions) and commit-graph lane highlighting on top. Everything works
without JavaScript. The OpenAPI schema lives at `/api`.

The commit-graph visualization (lane layout with linear-run folding) is
ported from cyblox's portal.

## Development

```bash
PYTHONPATH=src python3 -m pytest          # unit + route + hook e2e tests
PYTHONPATH=src python3 -m pytest -m e2e   # browser e2e (selenium + chromium)
```

The browser suite needs `sudo apt install python3-selenium chromium-driver`
(Debian has no python3-playwright; this is the apt-only equivalent).

### Debian package

```bash
dpkg-buildpackage -us -uc -b   # runs the test suite during build
sudo apt install ../gitflower_0.1.0_all.deb
sudo systemctl status gitflower   # web UI on 127.0.0.1:8747
sudo -u gitflower gitflower --config /etc/gitflower/config.yaml create demo.git
```

The package ships a hardened systemd unit and `/etc/gitflower/config.yaml`
as a conffile. A static `gitflower` system user owns
`/var/lib/gitflower/repos`; creating repos via that user keeps git's
repository-ownership check (`safe.directory`) satisfied naturally.

## Specs

`docs/spec/` carries the `.review` format and review-tool specs
(dot-review-format.md, gitflower-review.md) from the earlier work in
cute-devops. They describe a planned feature line — a git-notes-based code
review format — not yet implemented in this rewrite.

This repository uses the [Worktree Treehouses 🌳](https://cute-devops.patterns.how/patterns/approaches/worktree-treehouses)
shared-worktree layout. The bare repo lives at `/srv/repos/gitflower.git`; the
shared work directory is `/work/gitflower`. See `CLAUDE.md` in the work
directory for how to spawn a worktree.

## License

EUPL-1.2 — see `LICENSES/EUPL-1.2.txt`.

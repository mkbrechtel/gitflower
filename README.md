# gitflower

A git-based development platform — local-first, git-centric. A Python
**FastAPI** (web UI) + **click** (CLI) application built exclusively on Debian
`python3-*` apt packages.

```bash
sudo apt install python3-fastapi python3-click python3-pygit2 python3-yaml python3-jmespath
```

(That's the whole dependency list — plus `python3-pytest` for the tests.
`uvicorn` and `pydantic` arrive as hard dependencies of `python3-fastapi`.)

## The two feature lines

**Branch workflows (per repository).** A pre-receive hook engine with a branch
router: rules map branch glob patterns to workflows, and unconfigured branches
are rejected — the rule list is an allow-list. The most specific matching
pattern wins, so the order rules are written in does not matter. Patterns keep
the Go original's `filepath.Match` semantics (`*` never crosses `/`).

Settings live in the bare repository's own git config, so they are server-side
policy rather than something a clone carries. Enforcement happens where the
push lands: `--no-verify` cannot bypass it.

```bash
cd /srv/repos/myproject.git
gitflower init       # report the effective defaults
gitflower install    # install the pre-receive hook shim
gitflower config show
git config gitflower.branch.main.allowDirectPush true
```

```ini
# /srv/repos/myproject.git/config
[gitflower]
	pinnedBranch = main
	pinnedBranch = integration
	hiddenBranch = archive
[gitflower "branch.main"]
	workflow = protected
	requireLinearHistory = true
[gitflower "branch.issues/*"]
	workflow = issue-tracker
[gitflower "branch.releases/v*"]
	workflow = release-manager
```

A repository with no `gitflower.*` keys is governed by exactly those defaults.

**Repo hosting + web UI (global).** Bare repositories under a configured
directory, browsable in the browser and clonable read-only over smart-HTTP.
In-tree issues — markdown files under `issues/`, identified by an `id:` in
their front matter — are browsable across branches at
`/repos/<path>/issues/` and filterable with JMESPath.

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

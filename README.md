# gitflower

A git-based development platform — local-first, git-centric. Being rewritten
as a Python **FastAPI** (web UI) + **click** (CLI) application, built on Debian
`python3-*` apt packages.

## Development

This repository uses the [Worktree Treehouses 🌳](https://cute-devops.patterns.how/patterns/approaches/worktree-treehouses)
shared-worktree layout. The bare repo lives at `/srv/repos/gitflower.git`; the
shared work directory is `/work/gitflower`. See `CLAUDE.md` in the work
directory for how to spawn a worktree.

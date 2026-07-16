---
title: Issues view — in-tree issues across branches
status: open
created: 2026-07-16
---

# Issues view — in-tree issues across branches

gitflower gets a per-repo issues view. Issues are plain markdown files in the repository tree — free-format, with optional YAML frontmatter, and gitflower imposes no schema on either. The view shows the issues of a repo across its branches, because an issue file can be open on `main`, edited on one work branch, and resolved or archived on another, all at once.

## Model

**Location.** Issue files live under `issues/` by default. The directory is configurable per repository via git config.

**Identity.** An issue is identified by its file path. Renames are tracked — moving an issue into `issues/archive/` or into a category subfolder keeps its identity and history (rename detection, as `git log --follow` does).

**How issues enter the repo.** One issue per branch: filing an issue creates a branch carrying the new issue file, and merging that branch files the issue into the target. The web frontend gets an issue editor that does exactly this. The same flow serves QA (file issues against a QA branch; developers pull that branch and resolve them) and collaborating AI agents.

**Cross-branch state.** The issue set is the union across the configured branch tips. Versions are deduplicated by blob OID — branches whose `issues/` tree OID equals the default branch's have no issue changes and are skipped outright. Each divergent branch's issues are classified against the merge-base with the default branch: added, modified, deleted, or renamed on that branch.

**Branch selection.** Which branches feed the view is configurable per repository as ref patterns (e.g. `main`, `work/*`, `qa/*`), with all local branches as the default.

## Index

Reading issue state live means scanning trees across many branches and running rename detection per issue — too slow to do on every page load, and pygit2 offers no `--follow`. gitflower therefore maintains a derived index under a dedicated ref namespace (e.g. `refs/gitflower/issues`): per branch, the issue paths, blob OIDs, parsed frontmatter, and resolved rename chains. The index is a cache, never the source of truth — it can be deleted and rebuilt from the trees at any time, and is updated incrementally (post-receive, or lazily when a tip moved since the last indexing).

## Querying

Filtering is JMESPath over the indexed issue data — frontmatter plus computed fields (path, per-branch state). gitflower defines no status/label/assignee vocabulary; each project puts whatever it wants in frontmatter and queries it, and gitflower supports them all arbitrarily.

## Web UI

Endpoints follow the existing pattern (same URL serves page, fragment, and JSON): an issues list per repo with a JMESPath filter parameter, and an issue detail view showing the file rendered per branch with its divergences and its history timeline. The ambition beyond that is a kanban/graph/timeline presentation over the branches — visualizing where each issue sits in flight. UI design starts from this model once the index exists.

## Tasks

- [ ] Spec the index ref format (`refs/gitflower/issues`) and its incremental update
- [ ] Rename tracking in the indexer (pygit2 `find_similar` walk)
- [ ] Per-repo git config keys: issues directory, branch patterns
- [ ] `gitread` support: union/classification of issue files across tips
- [ ] JMESPath filtering over indexed frontmatter (`python3-jmespath`)
- [ ] List + detail endpoints and fragments
- [ ] Issue editor flow: create branch + issue file from the web UI
- [ ] Kanban/graph/timeline view over branches

# Considerations

## Why an index, and why prior art avoided in-tree files

Tools like git-bug and git-appraise store issues as structured objects in their own ref namespace instead of as files in the tree — likely because in-tree files have no cheap query path: every listing is a multi-branch tree scan and every history view needs rename detection. gitflower keeps the files (human-editable, mergeable, reviewable in MRs) and adds the missing piece as a derived index in refs, rather than moving the truth out of the tree.

## No issue schema

A fixed frontmatter vocabulary (status, labels, assignee) was considered and rejected. Projects differ; JMESPath over free frontmatter lets each project define its own logic without gitflower standing in the way. Consequence: gitflower's UI can only generically render what it finds, and "fancy" views (kanban columns) will need per-repo configuration mapping query expressions to UI.

## Git config over `.gitflower/config.yaml`

Per-repo issue settings live in git config rather than the in-tree `.gitflower/config.yaml`, so the hosting side can read them from the bare repo without checking out a tree, and settings apply uniformly across all branches.

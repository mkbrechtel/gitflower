---
id: 752b213c-49c9-4b85-85fe-a44052d08c06
title: Issues view — in-tree issues across branches
status: open
created: 2026-07-16
---

# Issues view — in-tree issues across branches

gitflower gets a per-repo issues view. Issues are plain markdown files in the repository tree — free-format, with frontmatter entirely project-defined; gitflower prescribes no fields. The view shows the issues of a repo across its branches, because an issue file can be open on `main`, edited on one work branch, and resolved or archived on another, all at once. The feature joins gitflower's two lines: the web UI browses the issues, and the hooks engine guards their invariants.

## Model

**Location.** Issue files live under `issues/` by default. The directory is configurable per repository via git config. Moves within the directory change only the folder — an issue's basename is immutable.

**Identity.** An issue is its filename: `issues/<name>.md` anywhere under the issues directory means issue `<name>`. Birth is registered by the ref `refs/issues/<name>` pointing at the commit that created the file; `issues/<name>.md@<commit>` is a permanent reference to a version. The lineage from birth to a branch's current path is a chain of exact renames (blob OID unchanged, directory-only), so archiving to `issues/archive/` or categorizing into subfolders keeps identity on every branch.

**Registration and move discipline.** The `issue-tracker` workflow enforces the invariants at push time: a new issue whose name is already registered to a different birth is rejected (ref creation is atomic — git arbitrates name collisions), and an issue file may only move blob-exact, never move-and-edit in one commit. Under these rules rename tracking is sound by construction, not by heuristic. The receive hook registers `refs/issues/<name>` for new issues; the indexer backfills registrations lazily for pre-existing history.

**Display.** An issue's display title is its frontmatter `title` if present, else its first markdown heading, else its name. Projects wanting pinned identifiers add an `id:` field by convention and query it — the core never reads it.

**Versions.** An issue's version is its blob OID. Its history is the set of transitions: commit C introduces version v when the issue's blob is v at C and at none of C's parents. The same version can be introduced independently on several branches, and each transition knows the version at the parent commits — transitions form a version DAG, with issue edits diverging and merging just like commits.

**How issues enter the repo.** One issue per branch: filing an issue creates a branch carrying the new issue file, and merging that branch files the issue into the target. The web frontend gets an issue editor that does exactly this — stamping nothing, committing moves separately. The same flow serves QA (file issues against a QA branch; developers pull that branch and resolve them) and collaborating AI agents.

**Cross-branch state.** The issue set is the union across the configured branch tips. Each divergent branch's issues are classified against the merge-base with the default branch — added, modified, deleted, or moved — by pure OID and path comparison; content diffs are computed only on demand. Branches whose issues-directory tree OID equals the default branch's are skipped outright.

**Branch selection.** Which branches feed the view is configurable per repository as ref patterns (e.g. `main`, `work/*`, `qa/*`), with all local branches as the default.

## Implementation

With identity in the tree path and birth in a ref, every relation the view needs is git-native: trees map paths to OIDs, path-scoped history is the accelerated kind of walk, and registration is a ref read. gitflower stores no semantic index of its own — only caches.

**History walks are git subprocesses; object reads are pygit2.** `git log --raw --all -- <issues-dir>` emits the complete transitions feed: every commit that touched the issues directory, with old and new blob OID, status, and OID-exact renames per file. Parsing this feed yields transitions, lineages, and births. Shelling out to git follows the existing smart-HTTP pattern.

**Commit-graph maintenance.** gitflower hosts the bare repos and keeps `git commit-graph write --reachable --changed-paths` fresh (post-receive or `git maintenance`). The changed-path Bloom filters let the path-scoped walk skip commits that didn't touch the issues directory without computing a diff; generation numbers speed up merge-base and containment queries.

**Map-reduce caching.** Every cache layer is keyed by an immutable OID, so entries never invalidate — caches only grow and evict: blob OID → parsed frontmatter; issues-tree OID → {path: blob OID} listing; tip commit → issue documents. A list query reduces the per-tip pieces into the document array and applies the JMESPath expression. No materialized index is needed; if a repo outgrows on-demand walks, a cache ref under `refs/gitflower/` can be added later without changing the model.

**Query functions** (gitread level): `issues(repo, q=None, branches=None)`, `issue(repo, name)`, `issues_for_commit(repo, sha)`, `issue_at(repo, name, commit)`. List and classification answer from cached tree listings without walking; timelines walk path-scoped on demand.

## Querying

Filtering is JMESPath over issue documents of the shape `{name, title, birth: {commit, path}, frontmatter, branches: {name: {path, oid, state}}, transitions}` — frontmatter and computed cross-branch state reachable in one expression (`[?frontmatter.status=='open']`, `[?branches.qa]`). gitflower defines no vocabulary; each project puts whatever it wants in frontmatter and queries it.

## Web UI

Endpoints follow the existing pattern (same URL serves page, fragment, and JSON):

- `GET /repos/{path}/issues/` — list; `?q=<jmespath>` filters, `?branch=` scopes.
- `GET /repos/{path}/issues/{name}` — detail: versions per branch, divergences, the version DAG as timeline. The name is the stable identity; `@<commit>` pins a version.
- Existing views gain cross-links: commit detail shows the issues it transitions, blob view shows "this file is issue X".

The ambition beyond that is a kanban/graph/timeline presentation over the branches; the version DAG renders with the existing graph machinery.

## Tasks

- [ ] Per-repo git config keys: issues directory, branch patterns
- [ ] Feed parser: `git log --raw` into transitions, lineages, births
- [ ] Registration: `refs/issues/<name>` from the receive hook, collision rejection, lazy backfill
- [ ] `issue-tracker` workflow: enforce blob-exact, directory-only moves
- [ ] Commit-graph maintenance on hosted repos (post-receive)
- [ ] OID-keyed caches: frontmatter, tree listings, tip documents
- [ ] JMESPath filtering (`python3-jmespath`)
- [ ] List and detail endpoints and fragments
- [ ] Issue editor flow: create branch plus issue file, moves committed separately
- [ ] Kanban/graph/timeline view over branches

# Considerations

## Identity in the path, not in frontmatter

A mandatory `id: <uuid>` frontmatter field was designed in detail and rejected. It puts identity inside blob content — the one place git cannot index at any speed: `git grep` answers only the present per tip, and pickaxe (`git log -S`) reports occurrence-count changes only (it finds the filing commit but not edits, and with default rename detection not even moves). uuid identity therefore forces gitflower to build and own an id → oid map as its core index. Filename identity plus birth refs relocates identity into the tree and the ref namespace — the things git indexes natively — and the core index disappears. Projects that want pinned uuids keep them as a frontmatter convention, fully queryable via JMESPath.

## Heuristic rename detection rejected

Identity via similarity-based rename detection (`git log --follow` semantics) was rejected: move+edit in one commit breaks the chain silently below the similarity threshold, results depend on diff config and rename limits, and template-derived issue files are similar enough to mispair. Only blob-exact renames count, and the `issue-tracker` hook makes their exactness an enforced invariant rather than a convention.

## Why prior art avoided in-tree files

Tools like git-bug and git-appraise store issues as structured objects in their own ref namespace instead of as files in the tree — likely because in-tree files with content-based identity have no cheap query path. With identity moved into paths and refs, the queries become the ones git already accelerates, so gitflower keeps the files (human-editable, mergeable, reviewable in MRs) without paying that price.

## History of deleted branches

On-demand git queries only see history reachable from live refs; `refs/issues/<name>` pins each issue's birth commit, but versions that existed only on a deleted branch become unreachable after gc. Accepted for v1. If full version retention matters later, a cache ref pinning version blobs (content addressing makes this free in storage) can be added without changing the model.

## Subprocess git over pygit2 for history walks

pygit2 1.17 exposes no commit-graph, Bloom filter, or bitmap API, while `git log --raw` emits exactly the data the feed parser needs. Object and tree reads stay pygit2; history walks shell out, as smart-HTTP already does.

## No issue schema

A fixed frontmatter vocabulary (id, title, status, labels, assignee) was considered and rejected in stages, ending at zero defined fields. Projects differ; JMESPath over free frontmatter lets each project define its own logic without gitflower standing in the way. Consequence: gitflower's UI can only generically render what it finds, and "fancy" views (kanban columns) will need per-repo configuration mapping query expressions to UI.

## Git config over `.gitflower/config.yaml`

Per-repo issue settings live in git config rather than the in-tree `.gitflower/config.yaml`, so the hosting side can read them from the bare repo without checking out a tree, and settings apply uniformly across all branches.

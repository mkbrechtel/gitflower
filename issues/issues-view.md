---
id: 752b213c-49c9-4b85-85fe-a44052d08c06
title: Issues view — in-tree issues across branches
status: open
created: 2026-07-16
---

# Issues view — in-tree issues across branches

gitflower gets a per-repo issues view. Issues are plain markdown files in the repository tree — free-format, with a single gitflower-defined frontmatter field: `id`. Everything else in the frontmatter is project-defined. The view shows the issues of a repo across its branches, because an issue file can be open on `main`, edited on one work branch, and resolved or archived on another, all at once. The feature joins gitflower's two lines: the web UI browses the issues, and the hooks engine guards their invariants.

## Model

**Location.** Issue files live under `issues/` by default. The directory is configurable per repository via git config.

**Identity.** An issue is identified by the `id: <uuid>` in its frontmatter, stamped by the issue editor on filing. The id survives every file operation — moves (archiving to `issues/archive/`, categorizing into subfolders), edits, move-and-edit in one commit, basename renames — and connects the issue's versions across branches by field equality. A file without an id falls back to path identity, with only exact renames (unchanged blob OID) tracked across moves.

**Id integrity.** The `issue-tracker` workflow guards the id at push time: a tree must not contain two issue files with the same id, and a commit must not change an existing issue's id. `gitflower issues fsck` detects duplicates across branches (independently filed twins) and orphaned files.

**Display.** An issue's display title is its frontmatter `title` if present, else its first markdown heading, else its filename.

**Versions.** An issue's version is its blob OID. Its history is the set of transitions: commit C introduces version v when the issue's blob is v at C and at none of C's parents. The same version can be introduced independently on several branches, and each transition knows the version at the parent commits — transitions form a version DAG, with issue edits diverging and merging just like commits. Versions group into an issue by their id, so continuity needs no move discipline.

**How issues enter the repo.** One issue per branch: filing an issue creates a branch carrying the new issue file with a freshly stamped id, and merging that branch files the issue into the target. The web frontend gets an issue editor that does exactly this. The same flow serves QA (file issues against a QA branch; developers pull that branch and resolve them) and collaborating AI agents.

**Cross-branch state.** The issue set is the union across the configured branch tips. Each divergent branch's issues are classified against the merge-base with the default branch — added, modified, deleted, or moved — by pure OID and path comparison; content diffs are computed only on demand. Branches whose issues-directory tree OID equals the default branch's are skipped outright.

**Branch selection.** Which branches feed the view is configurable per repository as ref patterns (e.g. `main`, `work/*`, `qa/*`), with all local branches as the default.

## Implementation

The id → oid map — which blob OIDs carry which issue id — is the one relation git cannot answer itself, at any speed: ids live inside blob content, and git indexes names and hashes, never content. This map is the core structure gitflower builds and owns. Every other relation (oid → introducing commits, containment, classification) git computes fast and is queried live.

**History walks are git subprocesses; object reads are pygit2.** `git log --raw --all -- <issues-dir>` emits the complete transitions feed: every commit that touched the issues directory, with old and new blob OID, status, and renames per file. The id → oid map falls out of the feed: each never-seen OID gets its frontmatter parsed once, appending an (id → oid) entry. The map is append-only and content-addressed — no invalidation, ever. Shelling out to git follows the existing smart-HTTP pattern.

**Commit-graph maintenance.** gitflower hosts the bare repos and keeps `git commit-graph write --reachable --changed-paths` fresh (post-receive or `git maintenance`). The changed-path Bloom filters let the path-scoped walk skip commits that didn't touch the issues directory without computing a diff; generation numbers speed up merge-base and containment queries.

**Map-reduce caching.** Every cache layer is keyed by an immutable OID, so entries never invalidate — caches only grow and evict: blob OID → parsed frontmatter; issues-tree OID → {path: blob OID} listing; tip commit → issue documents. A list query reduces the per-tip pieces into the document array and applies the JMESPath expression. v1 computes the id → oid map lazily this way; when a repo outgrows on-demand walks, the map is materialized under `refs/gitflower/issues/<uuid>` (issue data, transitions, and version blobs — content addressing makes pinning the blobs free in storage, and pinned versions survive branch deletion).

**Query functions** (gitread level): `issues(repo, q=None, branches=None)`, `issue(repo, uuid)`, `issues_for_commit(repo, sha)`, `issue_at(repo, uuid, commit)`. List and classification answer from cached tree listings without walking; timelines walk path-scoped on demand.

## Querying

Filtering is JMESPath over issue documents of the shape `{id, title, frontmatter, branches: {name: {path, oid, state}}, transitions}` — frontmatter and computed cross-branch state reachable in one expression (`[?frontmatter.status=='open']`, `[?branches.qa]`). Beyond `id`, gitflower defines no vocabulary; each project puts whatever it wants in frontmatter and queries it.

## Web UI

Endpoints follow the existing pattern (same URL serves page, fragment, and JSON):

- `GET /repos/{path}/issues/` — list; `?q=<jmespath>` filters, `?branch=` scopes.
- `GET /repos/{path}/issues/{uuid}` — detail: versions per branch, divergences, the version DAG as timeline; `@<commit>` pins a version. The uuid is a stable permalink surviving every move and rename.
- Existing views gain cross-links: commit detail shows the issues it transitions, blob view shows "this file is issue X".

The ambition beyond that is a kanban/graph/timeline presentation over the branches; the version DAG renders with the existing graph machinery.

## Tasks

- [ ] Per-repo git config keys: issues directory, branch patterns
- [ ] Feed parser: `git log --raw` into transitions grouped by id; frontmatter memoization by blob OID
- [ ] `issue-tracker` workflow: reject duplicate ids in a tree and id changes in a commit
- [ ] Commit-graph maintenance on hosted repos (post-receive)
- [ ] OID-keyed caches: frontmatter, tree listings, tip documents
- [ ] JMESPath filtering (`python3-jmespath`)
- [ ] List and detail endpoints and fragments
- [ ] `gitflower issues fsck`: cross-branch duplicate ids, orphaned files, map verification via `--find-object`
- [ ] Issue editor flow: create branch plus issue file, stamping `id`
- [ ] Materialized index refs `refs/gitflower/issues/<uuid>` with version pinning (scale option)
- [ ] Kanban/graph/timeline view over branches

# Considerations

## Identity options evaluated

Identity was the blocking question; five options were written down and evaluated before deciding on A.

**A. Frontmatter uuid (chosen).** Survives every file operation including move-and-edit commits and basename renames, needs no registration authority, and stitches branches by field equality. Costs accepted: gitflower defines one frontmatter field, owns the id → oid map as its core structure (mitigated by OID-keyed memoization over the transitions feed), and guards uniqueness through the hook and fsck.

**B. Filename with birth-registration refs (`refs/issues/<name>`).** Fully git-native and best-in-class URLs, but basenames become immutable, moves must be blob-exact and hook-disciplined, uniqueness exists only at push time, and the registration refs are semantic state not derivable from trees.

**C. Birth blob OID.** Intrinsic and registration-free, but template-identical initial content collides: two issues born with the same bytes share one OID — content addressing deduplicates exactly what identity must distinguish.

**D. Birth event (creating commit + path).** Unconditionally unique and registration-free, but references are two-part and verbose, resolution needs a lineage-roots lookup, continuity still requires move discipline, and an unmerged issue's birth commit becomes unreachable after its branch is deleted.

**E. Path with heuristic rename detection.** Move+edit breaks the chain silently, results depend on diff config, template files mispair, and a single-history walk cannot connect divergent moves across branches. No property beats the other options.

| | A uuid | B name+ref | C birth blob | D birth event | E follow |
|---|---|---|---|---|---|
| Unique by construction | ~ (stamping) | ~ (at push) | ✗ (templates) | ✓ | ✗ |
| Git-native queries | ✗ | ✓ | ~ | ~ | ~ |
| No registration needed | ✓ | ✗ | ✓ | ✓ | ✓ |
| Human-readable | ✗ | ✓ | ✗ | ~ | ✓ |
| Survives basename rename | ✓ | ✗ | ✓ | ✓ | ~ |
| Survives move+edit commit | ✓ | ✗ | ✗ | ✗ | ✗ |
| Zero schema | ✗ | ✓ | ✓ | ✓ | ✓ |
| No bespoke core index | ✗ | ✓ | ~ (roots map) | ~ (roots map) | ✓ |

A is the only option that survives all file operations without imposing discipline on how people commit; the index cost it carries is the one gitflower can pay entirely in infrastructure, invisible to users.

## No in-object queries in git

Git's two content-aware queries were evaluated for id → oid and both fall short. `git grep <uuid> <tip> -- issues/` answers only the present, per tip. Pickaxe (`git log -S<uuid>`) is an unindexed full-history walk that reports occurrence-count changes only: it finds the filing commit but not edits (the uuid's count is unchanged) and, with rename detection on by default, not even moves. Hence the id → oid map is built and owned by gitflower.

## Why prior art avoided in-tree files

Tools like git-bug and git-appraise store issues as structured objects in their own ref namespace instead of as files in the tree — likely because in-tree files with content-based identity have no cheap query path. gitflower keeps the files (human-editable, mergeable, reviewable in MRs) and pays the price knowingly: the id → oid map is derived from one Bloom-accelerated path-scoped walk and memoized forever.

## History of deleted branches

On-demand git queries only see history reachable from live refs; versions that existed only on a deleted branch become unreachable after gc. Accepted for v1. The materialized index refs (scale option) pin version blobs — content addressing makes this free in storage — and keep an issue's full history alive past its branch's lifetime.

## Subprocess git over pygit2 for history walks

pygit2 1.17 exposes no commit-graph, Bloom filter, or bitmap API, while `git log --raw` emits exactly the data the feed parser needs. Object and tree reads stay pygit2; history walks shell out, as smart-HTTP already does.

## One defined field, no further schema

A fuller frontmatter vocabulary (title, status, labels, assignee) was considered and rejected; only `id` is defined, because identity is the one thing the platform itself must resolve. Projects differ on everything else; JMESPath over free frontmatter lets each project define its own logic without gitflower standing in the way. Consequence: gitflower's UI can only generically render what it finds, and "fancy" views (kanban columns) will need per-repo configuration mapping query expressions to UI.

## Git config over `.gitflower/config.yaml`

Per-repo issue settings live in git config rather than the in-tree `.gitflower/config.yaml`, so the hosting side can read them from the bare repo without checking out a tree, and settings apply uniformly across all branches.

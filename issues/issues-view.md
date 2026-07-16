---
id: 752b213c-49c9-4b85-85fe-a44052d08c06
title: Issues view — in-tree issues across branches
status: open
created: 2026-07-16
---

# Issues view — in-tree issues across branches

gitflower gets a per-repo issues view. Issues are plain markdown files in the repository tree — free-format, with frontmatter entirely project-defined; gitflower prescribes no fields. The view shows the issues of a repo across its branches, because an issue file can be open on `main`, edited on one work branch, and resolved or archived on another, all at once. The feature joins gitflower's two lines: the web UI browses the issues, and the hooks engine guards their invariants.

## Model

**Location.** Issue files live under `issues/` by default. The directory is configurable per repository via git config.

**Identity.** The issue's unique, stable identity is the open question that shapes the whole feature: where identity lives decides what gitflower must index, enforce, and standardize. The candidates are collected and evaluated in [Identity options](#identity-options); everything else in this issue is written to work with any of them.

**Display.** An issue's display title is its frontmatter `title` if present, else its first markdown heading, else its filename.

**Versions.** An issue's version is its blob OID. Its history is the set of transitions: commit C introduces version v when the issue's blob is v at C and at none of C's parents. The same version can be introduced independently on several branches, and each transition knows the version at the parent commits — transitions form a version DAG, with issue edits diverging and merging just like commits. Version continuity across file moves relies on blob-exact renames; the `issue-tracker` workflow enforces that moves are blob-exact and never combined with an edit in one commit, making lineage sound by construction for every identity option.

**How issues enter the repo.** One issue per branch: filing an issue creates a branch carrying the new issue file, and merging that branch files the issue into the target. The web frontend gets an issue editor that does exactly this. The same flow serves QA (file issues against a QA branch; developers pull that branch and resolve them) and collaborating AI agents.

**Cross-branch state.** The issue set is the union across the configured branch tips. Each divergent branch's issues are classified against the merge-base with the default branch — added, modified, deleted, or moved — by pure OID and path comparison; content diffs are computed only on demand. Branches whose issues-directory tree OID equals the default branch's are skipped outright.

**Branch selection.** Which branches feed the view is configurable per repository as ref patterns (e.g. `main`, `work/*`, `qa/*`), with all local branches as the default.

## Identity options

What identity must provide: a permanent reference that survives moves, edits, and branch divergence; a way to write it down (URLs, cross-references from commits and other issues); and uniqueness within the repo. The options differ in where the identity lives — blob content, tree path, ref namespace, or history — and that placement determines what git can answer natively versus what gitflower must build and enforce.

### A. Frontmatter uuid

`id: <uuid>` in the file, stamped by the editor on filing. Survives every file operation that preserves the field — moves, edits, basename renames, cross-branch divergence — and stitching versions across branches is a field comparison. The cost: identity lives inside blob content, the one place git cannot index at any speed (`git grep` answers only the present per tip; pickaxe reports occurrence-count changes only — it finds the filing commit but not edits, and with default rename detection not even moves). gitflower would have to build and own an id → oid map as its core index, parse every blob's frontmatter, and impose the field — breaking the zero-schema stance. Copy-paste and templates can duplicate ids, so uniqueness needs checking anyway.

### B. Filename with birth registration

An issue is `issues/<name>.md`; the basename is immutable and moves change directories only. Birth is registered by the ref `refs/issues/<name>` pointing at the creating commit; atomic ref creation lets git arbitrate name collisions at push time. Fully git-native for queries (trees index paths; path-scoped walks are the Bloom-accelerated kind), best-in-class URLs and references, zero schema. The costs: basenames can never change; uniqueness is only enforced at push (offline-created issues can collide until then, and the losing push is rejected — friction); registration requires the hook to be in the loop; and the registration refs are genuine semantic state — which birth owns a name is not derivable from trees alone.

### C. Birth blob OID

The issue's identity is the blob OID of its first version; later versions map onto it through the transition lineage. Intrinsic and registration-free: the id exists the moment the file is created, offline, with no central authority, and later basename renames don't touch identity. The flaw is templates: two issues filed with byte-identical initial content (a template, an empty file) share the birth blob OID and collapse into one issue — content addressing deduplicates exactly what identity must distinguish. Resolution from id to current state also needs a lineage-roots lookup (cacheable, but the id itself is not a path git can walk).

### D. Birth event (creating commit + path)

The issue's identity is where and when it was born: the creating commit plus the path within it. Unique unconditionally — commits are unique, the path disambiguates a commit creating several issues, and template-identical content in different commits stays distinct. Intrinsic and registration-free like C, zero schema, derivable purely from history, and it permits basename renames. Handles read reasonably: `login-timeout@189d289` (birth basename plus short commit). Costs: references are two-part and slightly verbose; resolution needs the same lineage-roots lookup as C; and the birth commit of an issue whose branch was deleted before merging becomes unreachable after gc (the general deleted-branch caveat, hitting identity itself).

### E. Path with heuristic rename detection

The rejected baseline: identity is the current path, connected across moves by similarity-based rename detection (`git log --follow` semantics). Move+edit in one commit breaks the chain silently below the similarity threshold, results depend on diff config and rename limits, template-derived files mispair, and detection walks a single history so it cannot connect divergent moves across branches. Listed for completeness; no property of E beats the other options.

### Key versus handle

The options answer two different needs and can be layered: a **stable key** (permanent, unique — what cross-references and the index use) and a **human handle** (what URLs and people use, allowed to change). Pairings worth considering: D as key with the current filename as handle; B as handle-first design where the name *is* the key at the price of immutability; A as an opt-in convention on top of any of them for projects wanting portable ids. The decision is which key gitflower's core commits to.

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

## Implementation

These pieces stand regardless of the identity decision; the decision only determines what extra structure exists (A: an id → oid map as core index; B: registration refs plus push-time arbitration; C/D: a small lineage-roots cache).

**History walks are git subprocesses; object reads are pygit2.** `git log --raw --all -- <issues-dir>` emits the complete transitions feed: every commit that touched the issues directory, with old and new blob OID, status, and OID-exact renames per file. Parsing this feed yields transitions, lineages, and births. Shelling out to git follows the existing smart-HTTP pattern.

**Commit-graph maintenance.** gitflower hosts the bare repos and keeps `git commit-graph write --reachable --changed-paths` fresh (post-receive or `git maintenance`). The changed-path Bloom filters let the path-scoped walk skip commits that didn't touch the issues directory without computing a diff; generation numbers speed up merge-base and containment queries.

**Map-reduce caching.** Every cache layer is keyed by an immutable OID, so entries never invalidate — caches only grow and evict: blob OID → parsed frontmatter; issues-tree OID → {path: blob OID} listing; tip commit → issue documents. A list query reduces the per-tip pieces into the document array and applies the JMESPath expression. No materialized index is needed; if a repo outgrows on-demand walks, a cache ref under `refs/gitflower/` can be added later without changing the model.

**Query functions** (gitread level): `issues(repo, q=None, branches=None)`, `issue(repo, id)`, `issues_for_commit(repo, sha)`, `issue_at(repo, id, commit)`. List and classification answer from cached tree listings without walking; timelines walk path-scoped on demand.

## Querying

Filtering is JMESPath over issue documents of the shape `{id, title, birth: {commit, path}, frontmatter, branches: {name: {path, oid, state}}, transitions}` — frontmatter and computed cross-branch state reachable in one expression (`[?frontmatter.status=='open']`, `[?branches.qa]`). gitflower defines no vocabulary; each project puts whatever it wants in frontmatter and queries it.

## Web UI

Endpoints follow the existing pattern (same URL serves page, fragment, and JSON):

- `GET /repos/{path}/issues/` — list; `?q=<jmespath>` filters, `?branch=` scopes.
- `GET /repos/{path}/issues/{id}` — detail: versions per branch, divergences, the version DAG as timeline; `@<commit>` pins a version.
- Existing views gain cross-links: commit detail shows the issues it transitions, blob view shows "this file is issue X".

The ambition beyond that is a kanban/graph/timeline presentation over the branches; the version DAG renders with the existing graph machinery.

## Tasks

- [ ] **Decide issue identity** — evaluate [Identity options](#identity-options); blocks reference format, index shape, and hook scope
- [ ] Per-repo git config keys: issues directory, branch patterns
- [ ] Feed parser: `git log --raw` into transitions, lineages, births
- [ ] `issue-tracker` workflow: enforce blob-exact, directory-only moves
- [ ] Commit-graph maintenance on hosted repos (post-receive)
- [ ] OID-keyed caches: frontmatter, tree listings, tip documents
- [ ] JMESPath filtering (`python3-jmespath`)
- [ ] List and detail endpoints and fragments
- [ ] Issue editor flow: create branch plus issue file, moves committed separately
- [ ] Kanban/graph/timeline view over branches

# Considerations

## Why prior art avoided in-tree files

Tools like git-bug and git-appraise store issues as structured objects in their own ref namespace instead of as files in the tree — likely because in-tree files with content-based identity have no cheap query path. Identity options that live in paths, refs, or history keep the queries git-native; option A would reintroduce the price prior art avoided.

## History of deleted branches

On-demand git queries only see history reachable from live refs; versions that existed only on a deleted branch become unreachable after gc. Accepted for v1. If full version retention matters later, a cache ref pinning version blobs (content addressing makes this free in storage) can be added without changing the model — and would also keep option D's birth commits reachable.

## Subprocess git over pygit2 for history walks

pygit2 1.17 exposes no commit-graph, Bloom filter, or bitmap API, while `git log --raw` emits exactly the data the feed parser needs. Object and tree reads stay pygit2; history walks shell out, as smart-HTTP already does.

## No issue schema

A fixed frontmatter vocabulary (id, title, status, labels, assignee) was considered and rejected in stages, ending at zero defined fields. Projects differ; JMESPath over free frontmatter lets each project define its own logic without gitflower standing in the way. Consequence: gitflower's UI can only generically render what it finds, and "fancy" views (kanban columns) will need per-repo configuration mapping query expressions to UI.

## Git config over `.gitflower/config.yaml`

Per-repo issue settings live in git config rather than the in-tree `.gitflower/config.yaml`, so the hosting side can read them from the bare repo without checking out a tree, and settings apply uniformly across all branches.

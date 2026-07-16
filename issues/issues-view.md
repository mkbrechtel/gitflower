---
id: 752b213c-49c9-4b85-85fe-a44052d08c06
title: Issues view — in-tree issues across branches
status: open
created: 2026-07-16
---

# Issues view — in-tree issues across branches

gitflower gets a per-repo issues view. Issues are plain markdown files in the repository tree — free-format, and gitflower defines exactly two frontmatter fields: `id` and `title`. The view shows the issues of a repo across its branches, because an issue file can be open on `main`, edited on one work branch, and resolved or archived on another, all at once.

## Model

**Location.** Issue files live under `issues/` by default. The directory is configurable per repository via git config.

**Identity.** An issue is identified by the `id: <uuid>` in its frontmatter; `title` names it. All other frontmatter is project-defined. The id keeps identity stable across moves (archiving to `issues/archive/`, categorizing into subfolders), edits, and branches; the issue editor stamps both fields on filing. A file without an id falls back to path identity, with only exact renames (unchanged blob OID) tracked across moves.

**Versions.** An issue's version is its blob OID. Its history is the set of transitions: commit C introduces version v when the issue's blob is v at C and at none of C's parents. The same version can be introduced independently on several branches, and each transition knows the issue's OIDs at the parent commits — transitions form a version DAG, with issue edits diverging and merging just like commits.

**How issues enter the repo.** One issue per branch: filing an issue creates a branch carrying the new issue file, and merging that branch files the issue into the target. The web frontend gets an issue editor that does exactly this. The same flow serves QA (file issues against a QA branch; developers pull that branch and resolve them) and collaborating AI agents.

**Cross-branch state.** The issue set is the union across the configured branch tips. Each divergent branch's issues are classified against the merge-base with the default branch — added, modified, deleted, or renamed — by pure OID and path comparison; content diffs are computed only on demand. Branches whose `issues/` tree OID equals the default branch's are skipped outright.

**Branch selection.** Which branches feed the view is configurable per repository as ref patterns (e.g. `main`, `work/*`, `qa/*`), with all local branches as the default.

## Implementation

**History walks are git subprocesses; object reads are pygit2.** `git log --raw --all -- <issues-dir>` emits the complete transitions feed: every commit that touched the issues directory, with old and new blob OID, status, and OID-exact renames per file. The indexer parses this feed, resolves each new OID's frontmatter, and groups transitions by issue id. Frontmatter parsing is memoized by blob OID and never invalidates — OIDs are immutable. Shelling out to git follows the existing smart-HTTP pattern.

**Commit-graph maintenance.** gitflower hosts the bare repos and keeps `git commit-graph write --reachable --changed-paths` fresh (post-receive or `git maintenance`). The changed-path Bloom filters let the path-scoped walk skip commits that didn't touch the issues directory without computing a diff; generation numbers speed up merge-base and containment queries.

**Index refs.** The parsed state is materialized under a dedicated ref namespace:

```
refs/gitflower/issues/<uuid>   one ref per issue → index commit, tree:
    issue.json          id, title, frontmatter, per-branch {path, blob OID}
    versions/<oid>      the issue blob itself
    transitions.json    [{oid, parents: [oids], commit, author, date}]
refs/gitflower/issues-state    per-branch indexed tips, by-blob/ and by-commit/ reverse maps
```

Storing each version blob in the index tree costs nothing — content addressing means the object already exists — but pins it against gc, so an issue's full history survives deletion of the branch it lived on. Updates are incremental and append-only: commits are immutable, so each commit's transitions are computed once ever; when a tip moves, only the new commits are walked and the small tips file rewritten. The index is a cache, never the source of truth: deleting `refs/gitflower/*` and reindexing reproduces it exactly, and `git log --find-object=<oid>` serves as the verification oracle for an fsck command.

**Query functions** (gitread level): `issues(repo, q=None, branches=None)`, `issue(repo, uuid)`, `issues_for_commit(repo, sha)`, `issue_for_blob(repo, oid)`, `reindex(repo)`. List and classification answer from `issue.json` without walking or diffing; the reverse maps serve the commit and blob cross-links.

## Querying

Filtering is JMESPath over issue documents of the shape `{id, title, frontmatter, branches: {name: {path, oid, state}}, transitions}` — frontmatter and computed cross-branch state reachable in one expression (`[?frontmatter.status=='open']`, `[?branches.qa]`). gitflower defines no vocabulary beyond `id` and `title`; each project puts whatever it wants in frontmatter and queries it.

## Web UI

Endpoints follow the existing pattern (same URL serves page, fragment, and JSON):

- `GET /repos/{path}/issues/` — list; `?q=<jmespath>` filters, `?branch=` scopes.
- `GET /repos/{path}/issues/{uuid}` — detail: versions per branch, divergences, the version DAG as timeline. The uuid makes this a stable permalink that survives archiving and recategorization.
- Existing views gain cross-links: commit detail shows the issues it transitions, blob view shows "this file is issue X".

The ambition beyond that is a kanban/graph/timeline presentation over the branches; the version DAG renders with the existing graph machinery.

## Tasks

- [ ] Per-repo git config keys: issues directory, branch patterns
- [ ] Indexer: parse the `git log --raw` feed into transitions grouped by id; frontmatter memoization by blob OID
- [ ] Index refs: write/read `refs/gitflower/issues/<uuid>` trees and `issues-state`
- [ ] Commit-graph maintenance on hosted repos (post-receive)
- [ ] gitread query functions including reverse lookups
- [ ] JMESPath filtering (`python3-jmespath`)
- [ ] List and detail endpoints and fragments
- [ ] `gitflower issues fsck`: reindex and compare against `--find-object`
- [ ] Issue editor flow: create branch plus issue file, stamping `id` and `title`
- [ ] Kanban/graph/timeline view over branches

# Considerations

## Why an index, and why prior art avoided in-tree files

Tools like git-bug and git-appraise store issues as structured objects in their own ref namespace instead of as files in the tree — likely because in-tree files have no cheap query path: every listing is a multi-branch tree scan with frontmatter parsing. gitflower keeps the files (human-editable, mergeable, reviewable in MRs) and adds the missing piece as a derived index in refs, rather than moving the truth out of the tree.

## No git-side oid → commit index

`git log --find-object=<oid>` answers "which commits introduced this blob" but as a filtered full-history walk per query. Git's two acceleration structures don't cover it: changed-path Bloom filters are keyed by path, not OID, and pack bitmaps answer reachability, not introduction. The design sidesteps this by always walking path-scoped (Bloom-accelerated) and reading the OIDs from the `--raw` output, recording transitions at index time so oid → commit becomes a lookup.

## Subprocess git over pygit2 for history walks

pygit2 1.17 exposes no commit-graph, Bloom filter, or bitmap API, while `git log --raw` emits exactly the data the indexer needs. Object and tree reads stay pygit2; history walks shell out, as smart-HTTP already does.

## Rename detection rejected for identity

Identity via git rename detection (`git log --follow` semantics) was considered and rejected. Exact renames are reliable, but move+edit in one commit breaks the chain silently below the similarity threshold, results depend on diff config and rename limits, and issue files created from a template are similar enough to be mispaired. Above all, rename detection walks a single history and cannot connect the same issue moved to different paths on different branches. A frontmatter uuid has none of these problems and costs nothing in the editor-driven filing flow.

## No issue schema beyond id and title

A fixed frontmatter vocabulary (status, labels, assignee) was considered and rejected. Projects differ; JMESPath over free frontmatter lets each project define its own logic without gitflower standing in the way. Consequence: gitflower's UI can only generically render what it finds, and "fancy" views (kanban columns) will need per-repo configuration mapping query expressions to UI.

## Git config over `.gitflower/config.yaml`

Per-repo issue settings live in git config rather than the in-tree `.gitflower/config.yaml`, so the hosting side can read them from the bare repo without checking out a tree, and settings apply uniformly across all branches.

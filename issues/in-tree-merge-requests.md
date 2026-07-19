---
#SPDX-FileCopyrightText: 2026 Markus Katharina Brechtel <markus.katharina.brechtel@thengo.net>
#SPDX-License-Identifier: EUPL-1.2
---

# In-tree merge requests — design

gitflower manages merge requests in git itself: an MR is a request commit and the resolution that concludes it — usually a merge — tracked under a per-MR ref namespace and rendered in the web UI's merge-requests section. This issue records the design decisions taken so far and the questions still open, ahead of writing the spec.

## Scope

This feature covers only the MR itself: the request and its resolution. Reviews are follow-ups to an MR and have their own specs ([`../docs/spec/dot-review-format.md`](../docs/spec/dot-review-format.md)); how a repository organizes what happens around the merge — merging into an integration branch and reviewing the merge there, integrator modifications, checks, releasing to the mainline, or just yoloing everything to main — is the integration workflow, out of scope here.

## Decisions

**Opening an MR is an empty commit.** An MR is opened by an empty commit — no tree change — whose message summarizes what is about to be merged. The commit's own SHA is the MR id (`<oid>` below): intrinsic to the repository, needs no allocation or recording mechanism, and abbreviates for humans the way any git SHA does.

**An MR has no formal target branch.** A message starting `MR: <summary>` is an unspecified merge request: this line of work aims to be merged into the mainline (the default branch) over an appropriate path — the path is not predefined, and integration may happen via intermediate merges over a longer line. `MR@<branch>: <summary>` specifies an explicit target branch, for special circumstances.

**The namespace is three refs.** When an MR commit appears in a push, a git hook puts it on `refs/mrs/<oid>/request`. The MR concludes through its resolution:

- `refs/mrs/<oid>/request` — the merge request commit, topping the line of work to be merged.
- `refs/mrs/<oid>/merge` — the merge commit that concludes the MR positively, typically into an integration branch (or directly into the mainline).
- `refs/mrs/<oid>/resolution` — the commit that concludes the MR: the merge itself (same commit as `/merge`), or an empty commit whose message starts `Closure: <reason>` (the MR is closed — withdrawn, abandoned) or `Rejection: <reason>` (the MR is refused).

**MR state is derived, not stored.** An MR is open while `/resolution` is absent; once concluded it is merged (`/resolution` is the merge), closed (`Closure:`), or rejected (`Rejection:`). There is no status field that could drift from reality.

**Request commits are immutable — rework supersedes.** New work on the same line gets a new MR commit; the request never moves.

**Reviews are follow-ups.** Reviews, approvals, and checks respond to an MR — most usefully to its merge commit, whose tree is the actual integrated result — but they are not part of the MR namespace or this feature.

**Policy is configuration — stubbed for now.** What gitflower enforces around requests and concluding merges (who may merge, into which branches, under what conditions) is defined in gitflower's configuration. Initially this is a stub: the configuration surface exists, the enforcement is implemented later.

## Graphs

An MR concluded by an integrator merging it into an integration branch:

```
main        integration      MR (refs/mrs/<oid>/…)
────        ───────────      ───────────────────

M0
 \
  `──────── I0
 │           \
 │            `────────────── W1  author's work, based on I0
 │           │                │
 │           │                W2
 │           │                │
 │           │                R   /request   "MR: <summary>", empty commit
 │           │                │
 │           I1 ◄─────────────'   /merge     the merge concludes the MR
 │           │                               (/resolution points here too)
 │           │
 M1 ◄────────'                    everything after — reviewing the merge, checks,
 │                                release to main — is the integration workflow
```

Stacked MRs: MR₂'s work is based on MR₁'s work; by the time MR₂ is merged, the integration branch already contains MR₁:

```
integration       MR₁                 MR₂ (stacked on MR₁'s work)
───────────       ───                 ───────────────────────────

I0
 \
  `─────────────── A1  work
 │                 │
 │                 A2
 │                 │ \
 │                 │  `─────────────── B1  work, based on A2
 │                 R₁  /request        │
 │                 │                   B2
 I1 ◄──────────────'   /merge          │
 │                                     R₂  /request
 │                                     │
 I2 ◄──────────────────────────────────'   /merge — I1 already contains MR₁
 │
```

## Open questions

### O1 — How does the hook recognize the concluding merge?

Is `/merge` set when a pushed merge commit first makes the request reachable from a branch (which branch classes count — anything, or configured integration/mainline branches?), or does the concluding merge identify itself explicitly (a trailer naming the request's oid)? Fast-forwards and merges that bring in several requests at once need an answer too.

### O2 — Supersede, and how negative resolutions are delivered

Is a superseding request a valid `/resolution` for the MR it replaces (as in earlier iterations), or is supersede expressed as a `Closure: superseded by <oid>`? Should the superseding request link back? And mechanically: `Closure:`/`Rejection:` commits sit on no branch — how do they reach the hook (pushed on the work branch, pushed directly to the resolution ref, a CLI command)?

### O3 — Who may conclude an MR?

Who cuts the concluding merge — anyone with push access to the target branch, a configured integrator per branch/section, the MR author? This is presumably the core of the policy stub.

### O4 — How do follow-up reviews find their MR?

Reviews target the merge commit (or the request); tooling and the web UI need the reverse direction — given an MR, find its reviews. Notes on the merge commit, review files referencing the oid, or scanning is an open bridging question to the dot-review spec.

### O5 — Web UI

Discovery is enumerating `refs/mrs/*/request`. Still open: the list view's columns (summary, author, open/concluded, where it was merged); and the detail view — the request message, the line of work (diff against the merge target or merge base), the concluding merge, and follow-up reviews once O4 is answered.

# Considerations

## Superseded: the phase pipeline

Before the two-ref simplification, the namespace was a pipeline `/request → /modifications → /merge → /checks → /reviews → /release → /resolution`, one chain linear along its first parent, with the merge phase before checks and reviews so both covered the merged tree, refusal-with-open-conflict-markers semantics, release-time pruning of conversation files, and approval-staleness rules. The simplification moved everything after the merge out of the MR feature: modifications are integrator work on the integration branch, checks and reviews are follow-ups, and release/resolution belong to the integration workflow. Earlier still, the same content lived as parallel `/reviews` + `/checks` sibling refs (non-linear, rejected), a single unsegmented reaction line (no good name found), a standing recomputed `/merger` candidate ref, and originally as conversation commits on the work branch itself with `refs/mrs/<id>` as a branch-tip mirror.

## Deferred: the integration workflow

Ideas captured for the separate integration-workflow feature: optimistic integration branches per section (`integration/<section>`) that advance the moment an integrator cuts the merge — the integrator's promise that team work will land; reviews of the merge commit on the integration branch, entered only after checks pass so no brain time is spent on faulty trees; negative review findings as a task queue on the integration branch, flagging it not mergeable toward the mainline, with fixes based off the merge commit flowing forward (no train-style ejection or rebuild); prior art git.git `next`/`seen`, GitHub merge queues, GitLab merge trains; open there: hard rejection means a revert with the known revert-then-re-merge pitfalls, and conflicted merges (the open-marker `Merge Conflicts` commit convention) as fork points for resolution work.

## Rejected: `.mr/` root directory

An earlier sketch placed manifest, discussion, and reviews under a hidden `.mr/` directory at the repo root. Rejected in favour of commit messages and the dot-review on-tree conventions.

## Rejected: notes refs as the shared storage

The dot-review spec's default of sharing reviews via `refs/notes/reviews` is not used for MRs: notes refs don't transport by default and need out-of-band consolidation. Notes remain in the picture only as the reviewer's local drafting state before submission.

## Rejected: manifest and discussion files

A per-MR manifest (title, target, status frontmatter) and one-file-per-message discussion threads were considered and dropped. The request commit's message carries the description, follow-up reviews carry the conversation, and state is derived from the namespace — a second file format would duplicate all three.

## Rejected: branch name, sequential number, or UUIDv7 as MR id

Branch-derived ids break on branch rename and forbid repeated MRs from one branch; hook-allocated sequential numbers need atomic server-side allocation and have no in-history home; a UUIDv7 would be collision-free and mintable client-side but needs a recording mechanism (a trailer or hook bookkeeping) on top of what git already provides. The request commit's SHA has all the same properties with no extra machinery.

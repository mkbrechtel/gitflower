---
#SPDX-FileCopyrightText: 2026 Markus Katharina Brechtel <markus.katharina.brechtel@thengo.net>
#SPDX-License-Identifier: EUPL-1.2
---

# In-tree merge requests — design

gitflower manages the whole merge-request workflow — opening, review, acceptance, rework — in git itself: the MR and its conversation are commits under a per-MR ref namespace, and the web UI renders them in a merge-requests section. This issue records the design decisions taken so far and the questions still open, ahead of writing the spec.

## Scope

The review feature is specced separately ([`../docs/spec/dot-review-format.md`](../docs/spec/dot-review-format.md)). This design assumes only: *review commits* exist, they approve or comment upon commits by carrying `.review` file(s) in the tree, and they land on the MR's reviews ref. Reviewer work-in-progress state (draft comments, read-tracking) lives in git notes on the reviewer's machine; submitting is what turns a draft into a review commit.

## Decisions

**Opening an MR is an empty commit.** An MR is opened by an empty commit — no tree change — whose message summarizes what is about to be merged. The commit's own SHA is the MR id (`<merge-id>` below): intrinsic to the repository, needs no allocation or recording mechanism, and abbreviates for humans the way any git SHA does.

**An MR has no formal target branch.** A message starting `MR: <summary>` is an unspecified merge request: this line of work aims to be merged into the mainline (the default branch) over an appropriate path — the path is not predefined, and integration may happen via intermediate merges over a longer line. `MR@<branch>: <summary>` specifies an explicit target branch, for special circumstances.

**A git hook materializes a ref namespace per MR.** When an MR commit appears in a push, the hook puts it on `refs/mrs/<merge-id>/mr`. The full namespace:

- `refs/mrs/<merge-id>/mr` — the merge request commit.
- `refs/mrs/<merge-id>/reviews` — review commits on top of the MR commit: human reviews and approvals, and machine notifications such as CI and linter results.
- `refs/mrs/<merge-id>/resolution` — the commit that resolves the MR. Either an empty commit whose message starts `Closure: <reason>` — the MR is closed definitely — or a merge commit that resolves the MR positively, possibly one that merges over a longer line toward the mainline, or another MR commit based on this one that supersedes it.
- `refs/mrs/<merge-id>/merger` — a candidate merge commit, present even when the merge conflicts. A conflicted merger commit says `Merge Conflicts …` in its message and carries the conflict markers in its tree. Once the MR is merged, this points at the actual merge commit, which may be the same commit as the resolution.

**Conversation is commits plus `.review` files — nothing else.** The MR commit's message is the description. All further conversation — comments, questions, verdicts, approvals, machine check results — happens as `.review` events in commits on the reviews ref, following the on-tree `reviews/…` path convention of the dot-review spec. There is no separate manifest or discussion-file format.

**MR commits are immutable — rework supersedes.** When a review requests changes, the author's new work gets a new MR commit on the extended line; the old MR's `/resolution` points at the superseding MR commit. Approvals never go stale, because each approval sits on top of exactly one immutable ancestry.

**The hook keeps `/merger` fresh from both sides.** The candidate merge is recomputed against the mainline's tip (or the `MR@<branch>` target) whenever either side advances — a push to the MR or a push to the mainline.

**The resolving merge merges the reviews tip.** A positive resolution merges `refs/mrs/<merge-id>/reviews` — the MR's ancestry plus its review commits — so the `.review` files, approvals, and machine notifications land in mainline history as a permanent record alongside the code.

**The reviews ref is a single line.** Review commits stack linearly on top of the MR commit; concurrent submitters fetch, rebase, and retry like on any contested branch.

**MR state is derived from the namespace, not stored.** Open: `mr` exists and `resolution` doesn't. Resolved: `resolution` exists — merged (a merge commit), closed (a `Closure:` commit), or superseded (a newer MR commit based on this one). Whether the candidate merge currently conflicts is read off the `merger` commit. There is no status field that could drift from reality.

**Merge policy is configuration — stubbed for now.** Which approvals or machine checks an MR needs before it may merge is defined in gitflower's configuration. Initially this is a stub: the configuration surface exists, the enforcement is implemented later.

## Open questions

### O1 — What does `/merger` merge?

The resolving merge takes the reviews tip, so consistency suggests the candidate merger does too — merging `refs/mrs/<merge-id>/reviews` into the mainline tip rather than the bare MR commit. Confirm, and decide whether a conflicted merger commit blocks anything (resolution, superseding) or is purely informational.

### O2 — Does a superseding MR inherit anything?

A superseded MR's approvals cover the old ancestry by design and don't carry over — but does the new MR's namespace link back (beyond the old `/resolution` pointing forward), and should the web UI thread superseding MRs into one conversation?

### O3 — Who may write which ref?

Permissions per namespace entry — for example: anyone with access may append to `/reviews`, only author or maintainer may set `/resolution`, only the hook writes `/mr` and `/merger`. Presumably part of the policy configuration; the stub should reserve room for it.

### O4 — What does the policy stub look like?

Where the merge policy lives in the existing configuration (`branch_rules` workflow name, a policy list like `protected_branches`, or a new section), so the stub can be wired now and implemented later.

### O5 — Web UI

Discovery is enumerating `refs/mrs/*/mr`. Still open: the list view's columns (summary, author, state, merger conflict status); and the detail view — description, the reviews rendered from the reviews ref, the candidate merger's diff, and the line of work the MR covers.

# Considerations

## Rejected in the ref-namespace refinement

Advancing `/mr` to follow rework was rejected because it reintroduces approval staleness; rework commits on the reviews ref would conflate content with conversation. One-sided or on-demand merger computation trades away the always-fresh conflict signal. Keeping the conversation namespace-only would lose the permanent in-history record. Per-actor review refs and merge commits on the reviews line were passed over for the simpler single contested line.

## Superseded: branch-carried conversation

An earlier iteration kept the whole conversation on the work branch itself: review commits pushed onto the branch under review, `refs/mrs/<id>` as a plain mirror of the branch tip, divergence handled by the author merging the target in, approvals pinning a SHA with an exemption for clean target-updates, and push restrictions distinguishing author code from reviewer conversation. The per-MR ref namespace replaces all of it: the work branch stays untouched by MR machinery, reviews stack on the reviews ref, divergence surfaces in the conflicted merger commit, and per-MR grouping of review files is implicit in the namespace.

## Rejected: `.mr/` root directory

An earlier sketch placed manifest, discussion, and reviews under a hidden `.mr/` directory at the repo root. Rejected in favour of the visible `reviews/…` convention shared with the dot-review on-tree format.

## Rejected: notes refs as the shared storage

The dot-review spec's default of sharing reviews via `refs/notes/reviews` is not used for MRs: notes refs don't transport by default and need out-of-band consolidation. Notes remain in the picture only as the reviewer's local drafting state before submission.

## Rejected: manifest and discussion files

A per-MR manifest (title, target, status frontmatter) and one-file-per-message discussion threads were considered and dropped. The opening commit's message carries the description, `.review` events carry the conversation, and state is derived from the namespace — a second file format would duplicate all three.

## Rejected: branch name, sequential number, or UUIDv7 as MR id

Branch-derived ids break on branch rename and forbid repeated MRs from one branch; hook-allocated sequential numbers need atomic server-side allocation and have no in-history home; a UUIDv7 would be collision-free and mintable client-side but needs a recording mechanism (a trailer or hook bookkeeping) on top of what git already provides. The opening commit's SHA has all the same properties with no extra machinery.

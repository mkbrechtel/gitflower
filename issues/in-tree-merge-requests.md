---
#SPDX-FileCopyrightText: 2026 Markus Katharina Brechtel <markus.katharina.brechtel@thengo.net>
#SPDX-License-Identifier: EUPL-1.2
---

# In-tree merge requests — design

gitflower manages the whole merge-request workflow — opening, review, acceptance, rework — in-tree: the conversation is attached to the repository's tree and history with commits, and the web UI renders it in a merge-requests section. This issue records the design decisions taken so far and the questions still open, ahead of writing the spec.

## Scope

The review feature is specced separately ([`../docs/spec/dot-review-format.md`](../docs/spec/dot-review-format.md)). This design assumes only: *review commits* exist, they approve or comment upon commits by carrying `.review` file(s) in the tree, and they get attached to an MR. Reviewer work-in-progress state (draft comments, read-tracking) lives in git notes on the reviewer's machine; submitting is what turns a draft into a review commit.

## Decisions

**Opening an MR is a commit.** An MR is initiated by making a commit whose message starts with `MR: <title>`. A git hook recognizes the opening commit and creates a tracking ref for the MR.

**A tracking ref mirrors the MR.** The hook keeps `refs/mrs/<id>` pointing at the MR branch's current tip. The ref namespace is the discovery index for tooling and the web UI, and the mirror survives branch deletion as the archive of the MR.

**The MR id is the opening commit's SHA.** The `MR: <title>` commit's own SHA identifies the MR — `refs/mrs/<sha>` — so the id is intrinsic to the repository, needs no allocation or recording mechanism, and abbreviates for humans the way any git SHA does.

**Conversation is commits plus `.review` files — nothing else.** The `MR: <title>` commit message is the MR description. All further conversation — comments, questions, verdicts, acceptance, rework notes — happens as `.review` events in review commits. There is no separate manifest or discussion-file format. In-tree review files follow the `reviews/…` path convention from the dot-review spec.

**Review commits land on the MR branch.** Reviewers push their review commits directly onto the branch under review, so the branch's history is the complete MR timeline: code, reviews, and rework interleaved.

**Divergence is handled by merging the target in.** When the target branch (e.g. `main`) moves while the MR is open, the author merges the target into the MR branch. Reviewed commit SHAs stay valid, so SHA-anchored reviews survive; the MR history gains update-merge commits.

**Approvals pin a SHA; clean target-updates are exempt.** An approval names the commit it covers. New author work after that commit voids the approval and requires re-approval; conversation-only commits and clean target-update merges do not.

**The conversation lands on the target at merge.** The integration merge is a plain merge: `reviews/…` files and the MR commits arrive on the target branch as a permanent, grep-able in-history record.

**MR state is derived from history, not stored.** Opened by the `MR:` commit, approved when a covering verdict exists, merged when the tip is reachable from the target, closed by an explicit closing commit. There is no status field that could drift from reality.

**Pushes to an open MR branch are restricted to MR-related commits.** Non-authors may push only MR-related commits — review commits, closure, and similar workflow acts — not code changes. Enforcement mechanics are an open question.

## Open questions

### O1 — What counts as an "MR-related commit" for push enforcement?

The hook must recognize which commits a non-author may push. Candidates: path-based (touches only `reviews/…`), message-based (recognized prefixes like `Review:`, `Close:`), trailer-based, or a combination. The same recognition likely feeds the state derivation (closing commit) and the approval-staleness rule (conversation-only commits).

### O2 — Must the MR be up to date with the target at merge time?

Divergence is resolved by merging the target in, but it is undecided whether the hook refuses the final integration when the MR branch does not currently contain the target's tip (test-what-you-merge), or whether the merger may integrate a diverged branch.

### O3 — What is a "clean" target-update merge?

Clean updates don't void approvals; updates that required real conflict resolution arguably should. The rule needs a mechanical definition — for example, the update-merge's tree matches an automatic re-merge of its parents.

### O4 — What is the closing act?

Closing without merging is an explicit commit — what shape? A message prefix (`Close: <reason>`), a `.review` verdict (e.g. `Rejected`), or both? And does the hook do anything at closure beyond freezing the `refs/mrs/<id>` mirror?

### O5 — Lifecycle of `refs/mrs/<id>`

Which hook maintains the mirror (post-receive on the server?), does it keep following the branch after merge, and is it kept forever? Repeated MRs from the same branch get distinct ids — confirm the mirror model handles an open MR after an earlier merged one on the same branch.

### O6 — Layout under `reviews/`

The dot-review spec's on-tree convention is `reviews/<object-kind>-<short-sha>.review`. Do MR review commits use exactly that flat layout, or are files grouped per MR (e.g. `reviews/<mr-id>/…`) so a merged target keeps records of many MRs apart?

### O7 — Web UI

Discovery is enumerating `refs/mrs/`. Still open: the list view's columns (title, author, state, ahead/behind, verdicts); and the detail view — a timeline interleaving code commits and review events across `merge-base..tip`, rendered `.review` sections, and a changes view with `reviews/…` paths filtered out of the diff.

# Considerations

## Rejected: `.mr/` root directory

An earlier sketch placed manifest, discussion, and reviews under a hidden `.mr/` directory at the repo root. Rejected in favour of the visible `reviews/…` convention shared with the dot-review on-tree format.

## Rejected: notes refs as the shared storage

The dot-review spec's default of sharing reviews via `refs/notes/reviews` is not used for MRs: notes refs don't transport by default and need out-of-band consolidation. Notes remain in the picture only as the reviewer's local drafting state before submission.

## Rejected: manifest and discussion files

A per-MR manifest (title, target, status frontmatter) and one-file-per-message discussion threads were considered and dropped. The opening commit's message carries the description, `.review` events carry the conversation, and state is derived from history — a second file format would duplicate all three.

## Rejected: branch name, sequential number, or UUIDv7 as MR id

Branch-derived ids break on branch rename and forbid repeated MRs from one branch; hook-allocated sequential numbers need atomic server-side allocation and have no in-history home; a UUIDv7 would be collision-free and mintable client-side but needs a recording mechanism (a trailer or hook bookkeeping) on top of what git already provides. The opening commit's SHA has all the same properties with no extra machinery.

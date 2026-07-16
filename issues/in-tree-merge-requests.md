---
#SPDX-FileCopyrightText: 2026 Markus Katharina Brechtel <markus.katharina.brechtel@thengo.net>
#SPDX-License-Identifier: EUPL-1.2
---

# In-tree merge requests — design

gitflower manages the whole merge-request workflow — opening, review, acceptance, rework — in git itself: the MR and everything that happens to it are commits under a per-MR ref namespace, and the web UI renders them in a merge-requests section. This issue records the design decisions taken so far and the questions still open, ahead of writing the spec.

## Scope

The review feature is specced separately ([`../docs/spec/dot-review-format.md`](../docs/spec/dot-review-format.md)). This design assumes only: *review commits* exist, they approve or comment upon commits by carrying `.review` file(s) in the tree, and they land in the MR's reviews phase. Reviewer work-in-progress state (draft comments, read-tracking) lives in git notes on the reviewer's machine; submitting is what turns a draft into a review commit.

## Decisions

**Opening an MR is an empty commit.** An MR is opened by an empty commit — no tree change — whose message summarizes what is about to be merged. The commit's own SHA is the MR id (`<merge-id>` below): intrinsic to the repository, needs no allocation or recording mechanism, and abbreviates for humans the way any git SHA does.

**An MR has no formal target branch.** A message starting `MR: <summary>` is an unspecified merge request: this line of work aims to be merged into the mainline (the default branch) over an appropriate path — the path is not predefined, and integration may happen via intermediate merges over a longer line. `MR@<branch>: <summary>` specifies an explicit target branch, for special circumstances.

**The MR runs through a pipeline of phases, each marked by a ref.** When an MR commit appears in a push, a git hook puts it on `refs/mrs/<merge-id>/request` and the pipeline begins. A successful run looks like `/request → /modifications → /merger → /checks → /reviews → /release → /resolution`:

- `refs/mrs/<merge-id>/request` — the merge request commit.
- `refs/mrs/<merge-id>/modifications` — mechanical preparation by bots on top of the request: a release bot assigning a version number, formatters, generated files. These commits modify the tree.
- `refs/mrs/<merge-id>/merger` — the merge into the target happens here: a merge commit joining the chain with the mainline's (or the `MR@<branch>` target's) tip. If the merge conflicts, the merge commit carries the open conflict markers and a message starting `Merge Conflicts` and is set as the resolution — the MR is refused and never enters checks or review. MRs with merge conflicts are never accepted.
- `refs/mrs/<merge-id>/checks` — machine checks on the merged tree: CI results, linter output.
- `refs/mrs/<merge-id>/reviews` — human reviews and approvals. The review targets the merger commit — the tree as it will actually look on the target, including all modifications and merge effects — and starts only after the checks concluded: no brain time or tokens are spent on faulty trees.
- `refs/mrs/<merge-id>/release` — the merged result lands on the target here.
- `refs/mrs/<merge-id>/resolution` — the commit that resolves the MR: the positive release, an empty commit whose message starts `Closure: <reason>` (the MR is closed definitely), a superseding MR commit based on this one, or the conflicted `Merge Conflicts` merge.

**The pipeline is one chain, linear along its first parent.** Each phase ref points at the last commit of its segment, stacked on the previous phase's tip; the merger commit is the one point where a second parent — the target's tip — joins the chain. Checks and reviews stack on top of the merger commit.

**Checks and reviews cover the merged result.** Because the merger phase precedes them, machine checks and human review examine the tree after merging into the target — so mechanical modifications and merge effects are checked and reviewed too, not just the author's work.

**Conversation is commits plus `.review` files — nothing else.** The MR commit's message is the description. Reviews, approvals, and machine check results are `.review` events in commits on the chain, following the on-tree `reviews/…` path convention of the dot-review spec; modification commits may change any part of the tree. There is no separate manifest or discussion-file format.

**Request commits are immutable — rework supersedes.** When a review requests changes, the author's new work gets a new MR commit; the old MR's `/resolution` points at the superseding request. Approvals never go stale, because each approval sits on top of exactly one immutable chain.

**Refusal is a fork point.** A refused MR remains useful: fork off its chain — from the conflicted `Merge Conflicts` merge to resolve the markers, or from the review findings to address them — and open a new MR based on that work; the refused MR's resolution points at the superseding request.

**The release merge may prune the conversation from the tree.** The merge commit may delete files again — the in-tree review and check files — so they are attached to history but don't linger in the mainline's tree.

**MR state is derived from the namespace, not stored.** Which phase refs exist and where they point is the state: in preparation, refused at the merger (resolution points at a `Merge Conflicts` merge), in checks, in review, released, closed, or superseded. There is no status field that could drift from reality.

**Merge policy is configuration — stubbed for now.** Which checks and approvals an MR needs before it may release is defined in gitflower's configuration. Initially this is a stub: the configuration surface exists, the enforcement is implemented later.

## Open questions

### O1 — Who advances the pipeline?

What moves the MR from phase to phase: the hook alone, bots reporting in, or a maintainer command? Concretely — what triggers the modification bots, who cuts the merger commit, what declares the checks phase passed (all policy-required checks green?), and who may release.

### O2 — What exactly happens at `/release`, and what about target drift?

The merger commit was cut against the target's tip at merger time; the target may have advanced by the time checks and reviews conclude. Does release require the merger to still be current (fast-forwardable — otherwise the pipeline loops back through merger → checks → reviews on a fresh merge), or may release re-merge without re-review? Tied to this: what the target branch actually advances to — the chain tip (bringing the conversation into target history, with the reviews as first-parent ancestry), a pruning commit on top of it, or a fresh merge commit — and how that interacts with the usual first-parent-is-mainline convention.

### O3 — Does a superseding MR link back?

A refused or reworked MR's `/resolution` points forward at the superseding request. Does the new MR's namespace link back as well, and should the web UI thread a supersede-chain into one conversation?

### O4 — Who may write which ref?

Permissions per phase — for example: machine identities write `/modifications` and `/checks`, anyone with access appends to `/reviews`, only author or maintainer set `/resolution`, only the hook writes `/request` and `/release`. Presumably part of the policy configuration; the stub should reserve room for it.

### O5 — What exactly does the release merge prune?

Deleting in-tree review and check files at merge time: always, by policy, or at the merger's discretion? And the boundary — modification commits like a version bump must survive pruning; is the rule simply "conversation files out, tree changes stay"?

### O6 — What does the policy stub look like?

Where the merge policy lives in the existing configuration (`branch_rules` workflow name, a policy list like `protected_branches`, or a new section), so the stub can be wired now and implemented later.

### O7 — Web UI

Discovery is enumerating `refs/mrs/*/request`. The pipeline suggests the rendering: the MR as a stage view (request → modifications → merger → checks → reviews → release), each stage showing its segment of the chain. Still open: the list view's columns (summary, author, phase, conflict state) and how the detail view presents the diff to be merged versus the conversation.

# Considerations

## Superseded: parallel reviews and checks refs

A previous iteration split human reviews and machine checks into two sibling refs, both based on the MR commit — which makes the record non-linear as soon as both need merging. Before that, a single unsegmented "reactions" line was considered, but no name for it felt right (`/responses`, `/evaluation`, `/proceedings`, `/vetting`, …). The pipeline resolves both problems: one chain, and each segment names itself by its phase. A standing `/merger` candidate ref recomputed from both sides — and, briefly, a merge test inside the checks phase — became the merger *phase* instead, so that checks and reviews operate on the merged tree rather than predicting it.

## Superseded: branch-carried conversation

An earlier iteration kept the whole conversation on the work branch itself: review commits pushed onto the branch under review, `refs/mrs/<id>` as a plain mirror of the branch tip, divergence handled by the author merging the target in, approvals pinning a SHA with an exemption for clean target-updates, and push restrictions distinguishing author code from reviewer conversation. The per-MR ref namespace replaces all of it: the work branch stays untouched by MR machinery and divergence surfaces in the conflict-tested merge.

## Rejected: advancing the request ref on rework

Moving `/request` (or the whole namespace) to follow reworked content was rejected because it reintroduces approval staleness; the immutable request plus supersede keeps every approval attached to exactly the chain it covered.

## Rejected: `.mr/` root directory

An earlier sketch placed manifest, discussion, and reviews under a hidden `.mr/` directory at the repo root. Rejected in favour of the visible `reviews/…` convention shared with the dot-review on-tree format.

## Rejected: notes refs as the shared storage

The dot-review spec's default of sharing reviews via `refs/notes/reviews` is not used for MRs: notes refs don't transport by default and need out-of-band consolidation. Notes remain in the picture only as the reviewer's local drafting state before submission.

## Rejected: manifest and discussion files

A per-MR manifest (title, target, status frontmatter) and one-file-per-message discussion threads were considered and dropped. The opening commit's message carries the description, `.review` events carry the conversation, and state is derived from the namespace — a second file format would duplicate all three.

## Rejected: branch name, sequential number, or UUIDv7 as MR id

Branch-derived ids break on branch rename and forbid repeated MRs from one branch; hook-allocated sequential numbers need atomic server-side allocation and have no in-history home; a UUIDv7 would be collision-free and mintable client-side but needs a recording mechanism (a trailer or hook bookkeeping) on top of what git already provides. The opening commit's SHA has all the same properties with no extra machinery.

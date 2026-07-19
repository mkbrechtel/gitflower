---
#SPDX-FileCopyrightText: 2026 Markus Katharina Brechtel <markus.katharina.brechtel@thengo.net>
#SPDX-License-Identifier: EUPL-1.2
title: Approving with .review — iterating the format and the review feature
status: open
created: 2026-07-16
---

# Approving with `.review` — iterating the format and the review feature

The `.review` format spec ([`../docs/spec/dot-review-format.md`](../docs/spec/dot-review-format.md)) and the tool spec ([`../docs/spec/gitflower-review.md`](../docs/spec/gitflower-review.md)) were written against the Go implementation and a notes-ref-first storage model. Two sibling designs have since moved the ground: the in-tree merge-request design (`work/docs/mr-design-questions`, [`in-tree-merge-requests.md`](./in-tree-merge-requests.md)) makes reviews commits that carry `.review` files in the tree, and the issues view (`work/issues/issues-view`, [`issues-view.md`](./issues-view.md)) puts issues in the tree as well. This issue collects the iteration both force on the review feature, centered on the question the specs leave open end to end: how a change actually gets approved.

## Proposed iteration

**Tree-first storage.** The submitted, shared form of a review is an in-tree `.review` file in a review commit under `reviews/…`, following the on-tree convention the format spec already sketches. The notes ref demotes to local drafting state — WIP comments, read-tracking — that never has to transport; submitting is what turns the draft into a review commit. This is exactly the split the MR design already assumes; the format spec's *Storage* and *Multi-reviewer merge* sections get rewritten to match. The format itself barely changes: the deterministic skeleton and append-only events that made `cat_sort_uniq` work are the same properties that let concurrent in-tree review files merge cleanly.

**A diff-range object section.** The tool spec scaffolds a `# Diff <base>..<tip> @ git diff <base>..<tip>` section that the format spec never defines — its object sections are Blob, Tree, Commit, and Merge-Commit only. An MR review covers a branch delta, and the merge commit that would carry it does not exist until integration, so the format gains a fifth object shape: a diff-range section naming both endpoint SHAs in the heading, with the same per-file `## File …` lifecycle subsections as `# Commit`. This closes the gap and gives approval something to anchor to before the merge exists.

**Approval is a verdict in a submitted review.** `- Verdict-reached-by: <Name> <<email>>; Approved` inside a `.review` whose object section names the covered SHAs. Approval covers exactly those objects — the MR design's "approvals pin a SHA" falls out of the format's zero-implicit-scope goal rather than needing its own rule. New author commits after the covered tip void the approval; conversation-only review commits and clean target-update merges do not (recognition shared with the MR design's O1/O3).

**The gate is a branch-protection workflow.** The Python rewrite's hook engine — branch router mapping glob patterns to workflows — gains a `review-gate` workflow alongside no-direct-push and linear-history: a push updating a protected branch must be a merge whose history contains a submitted `.review` approving the merged tip, from an eligible approver. This replaces the tool spec's "planned `review-gate` hook" sketch, which scanned notes refs; the in-tree model means the gate reads review commits instead. Kernel-style trailer recognition can stay as a compatibility signal.

**Python surfaces.** The format spec is language-neutral and survives as-is. The tool spec is bound to the Go bubbletea TUI and gets superseded rather than ported: the click CLI scaffolds a `.review` file for the branch delta and hands it to `$EDITOR`, and `gitflower review submit` commits it under `reviews/…`; the FastAPI web UI renders `.review` files read-only in the repo browser and the MR detail view (MR design O7). A TUI is a later possibility, not a rewrite target. The editor-based flow doubles as the agent flow — the format was designed to be written and read by LLMs without specialist tooling, so an agent reviews by appending events to the scaffold and submitting.

**Issues cross-over.** `## Issue` subsections stay review-scoped: they live and die with the review conversation. An issue that outlives the MR is promoted into an `issues/` file via the issues-view flow (a branch carrying the new file), and the review-side subsection gets resolved with a comment pointing at it.

## Convergence with the cute-devops review patterns

The pattern library describes review twice, and the two disagree with each other the same way the specs disagree with this issue: Merge Reviews 🔍 puts submitted `.review` files in the tree on a `review/merge-<sha>` branch and concludes with an empty `APPROVE:`/`REQUEST-CHANGES:` verdict commit; Continuous Review 🫧 keeps the review stream in `refs/notes/reviews` with a `[Review]` merge as the high-water line. The tree-first split above converges both around one storage rule — the tree holds every submitted review, notes hold only drafts.

**The continuous track submits through the tree too.** The `[Review]` high-water merge stops pointing at notes content and instead carries the session's `.review` file into the tree under `reviews/…` — the merge is the submission. Q6 then resolves as repurpose rather than delete: `gitflower review merge` survives as the continuous track's submit, and `continuous-review.md` on the pattern side updates its storage description to match.

**One approval signal.** The `Verdict-reached-by:` event in a submitted review is the authoritative approval — the gate parses exactly one signal. The pattern's empty verdict commits demote to optional greppable convenience or leave `merge-reviews.md`; keeping both authoritative would be two sources of truth, one always stale.

**The approval object can be the actual merge.** Merge Reviews insists the review targets the merge commit that lands, not a branch diff that may differ. The MR design's `/merge` ref makes that possible before `main` moves: the integrator's merge exists as an object ahead of the protected push. The diff-range section (Q1) then serves incremental and pre-merge review; what the *approving* review must cover is Q7.

**The shipped CLI redirects before it lands.** `work/feature/review-cli` implements the notes-first model this issue demotes, and is unmerged — cheaper to redirect now than to rework after landing. Its parser, scaffold and TUI carry over unchanged; its notes persistence becomes the draft layer (Q4 answered in practice — the autosave already is a draft), and `gitflower review submit` is added as the tree-first path. It also ships a Textual TUI from Debian `python3-textual`, which overtakes the no-TUI-commitment consideration below; the rationale stands for not *requiring* a TUI, but the superseded tool spec should describe the one that exists.

**Pattern-side edits.** cute-devops changes this issue implies, recorded here so the two repos move together: the verdict location in `merge-reviews.md`, the storage description in `continuous-review.md`, and the `review/` vs `reviews/` branch-prefix inconsistency between `merge-reviews.md` and the pure-git-workflows skill.

## Open questions

### Q1 — Exact shape of the diff-range section

Heading syntax (`# Diff <base>..<tip> @ git diff <base>..<tip>`?), whether `...` three-dot merge-base form is also allowed, and how the range review composes with the per-commit reviews of `base..tip` — the tool spec's scaffold emits both, but the format's one-object-per-file rule means they are separate notes today; in one in-tree file they need a defined containment.

### Q2 — Merge mechanics for concurrent review commits

Two reviewers submitting review commits touching the same `.review` path must merge without manual conflict resolution. Candidates: `reviews/*.review merge=union` via in-tree `.gitattributes`, a dot-review merge driver that re-renders the skeleton and unions events, or per-reviewer file names making collisions structurally impossible (interacts with MR design O6 on the `reviews/…` layout).

### Q3 — Who is an eligible approver

Reuse the allowed-users mechanism from the existing branch-protection workflows, a dedicated approver list per protected branch, or any committer who is not the MR author? Whether author self-approval is refused by the gate or merely surfaced belongs here too.

### Q4 — What remains of the local notes draft

With submission going through the tree, the drafting state could stay in a local notes ref (as the MR design assumes) or simply be the uncommitted `.review` file in the working tree. The notes draft buys read-tracking persistence across machines but costs a second storage path in the Python tool.

### Q5 — Fate of `gitflower-review.md`

Whether the tool spec is rewritten in place for the Python surfaces or marked superseded with a fresh, smaller spec. Bound up with which TUI-era features (read-rate pacing, dwell tracking, walk mode) keep a home in the format after the tool that produced them is gone — the event shapes cost nothing to keep, but spec text describing dead tooling misleads.

### Q6 — Fate of `gitflower review merge` and `[Review]` merges

The tool spec's `review merge` subcommand and its `[Review]`-merge base-ref detection predate the MR design, which derives everything from the MR branch history instead. Presumably both fold into the MR integration flow; confirm nothing else depends on `[Review]` markers before deleting them from the spec.

### Q7 — Does approval pin the tip or the merge?

The gate can accept an approving review covering the branch tip (approval travels with the MR; the integrator's merge follows), or require coverage of the actual `/merge` commit — Merge Reviews' rule, what lands is what was judged, at the cost of re-approval whenever the integrator's merge is created or redone. A middle path: tip approval suffices when the merge introduces exactly that tip and resolves nothing; a conflicted or otherwise modified merge needs its own approval. Recognizing "introduces exactly that tip" shares machinery with the MR design's O1.

## Tasks

- [ ] Decide Q1 and add the diff-range object section to `dot-review-format.md`
- [ ] Rewrite the *Storage* and *Multi-reviewer merge* sections of `dot-review-format.md` tree-first, demoting notes to draft state
- [ ] Decide Q2 and spec the merge mechanics (gitattributes vs. merge driver vs. layout)
- [ ] Spec the `review-gate` workflow in the hook engine, including approval-staleness recognition shared with the MR design
- [ ] Supersede or rewrite `gitflower-review.md` for the click CLI + editor flow (Q5)
- [ ] `.review` rendering in the web UI (read-only; joins the MR detail view, MR design O7)
- [ ] Editorial pass over `dot-review-format.md` (typos: "gitfßlower", "Loosley", "determin", "hierachy")
- [ ] Decide Q7 — what the approving review must cover for the gate
- [ ] Redirect `work/feature/review-cli` tree-first: notes persistence demotes to draft, `gitflower review submit` added
- [ ] File the cute-devops pattern edits (verdict location in `merge-reviews.md`, storage in `continuous-review.md`, review-branch prefix)

# Considerations

## Why tree-first

The MR design already rejected notes refs as shared review storage because notes don't transport by default and need out-of-band consolidation; repeating the argument here would just drift. The consequence for the format spec is what this issue records: the notes-first *Storage* section describes what is now the draft layer, not the system of record.

## Per-reviewer notes refs and cat_sort_uniq

The format spec's consolidator model (`refs/notes/reviews-<name>` merged via `cat_sort_uniq`) solved multi-reviewer concurrency for notes. Tree-first, git's ordinary merge machinery takes that job (Q2), and the consolidator section can be deleted rather than ported — keeping it would preserve a second concurrency mechanism nobody runs.

## Why no Python TUI commitment

Dependencies come from Debian apt packages only. Committing to a TUI means committing to a Debian-packaged TUI framework before one has been chosen, and the editor-plus-web split covers reading and writing without it. Revisit when someone actually misses it.

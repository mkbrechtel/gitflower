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

**Tree-first storage.** The submitted, shared form of a review is an in-tree `.review` file in a review commit under `reviews/…`, following the on-tree convention the format spec already sketches. The notes ref demotes to local drafting state — WIP comments, read-tracking — that never has to transport; submitting is what turns the draft into a review commit on a `reviews/…` branch, carrying the file under `reviews/` in the tree, and merging that branch into the integration branch publishes the review into the history the gate inspects. This is exactly the split the MR design already assumes; the format spec's *Storage* and *Multi-reviewer merge* sections get rewritten to match. The format itself barely changes: the deterministic skeleton and append-only events that made `cat_sort_uniq` work are the same properties that let concurrent in-tree review files merge cleanly.

**Every merge onto the integration branch is reviewed.** The integration branch is what later lands on `main`, so its merge commits are the review surface: an MR's `/merge` arrives as a merge onto integration, and the review anchors to that `# Review Merge-Commit` heading with its per-parent diff subsections — the branch delta exactly as it landed. Approval needs no separate range object, and the tool spec's scaffolded `# Diff <base>..<tip>` section has no successor: an **open review** — a bare `# Review` file collecting reviewer-added artifacts — serves pre-merge conversation and the continuous track's since-last-review scaffold instead.

**Approval is a verdict in a submitted review.** `- Verdict-reached-by: <Name> <<email>>; Approved` inside a `.review` whose object section names the covered SHAs. Approval covers exactly those objects — the MR design's "approvals pin a SHA" falls out of the format's zero-implicit-scope goal rather than needing its own rule. New author commits after the covered tip void the approval; conversation-only review commits and clean target-update merges do not (recognition shared with the MR design's O1/O3). For the `review-gate`, the covered object is always a merge commit itself — what lands is what was judged, and a redone integrator merge asks for a fresh approval. Other reviews carry the conversation, not the gate.

**Integration lands on `main` only clean.** The gate for the mainline merge checks every merge on the integration branch since it forked: each carries a submitted approving review, and every finding those reviews raised is resolved. Resolution is itself validated over further merges into the integration branch — fix merges and review updates — the MR design's fix-forward task queue in practice.

**Concurrent reviews merge as appends.** dot-review is append-only: an event line is self-contained and idempotent under duplication, so two reviewers' submissions to the same `.review` path merge with git's ordinary machinery and never need manual resolution. `reviews/…` carries a `.gitattributes` `merge=union` entry as the baseline; renderers renormalize on parse by re-emitting the deterministic skeleton. The remaining detail for the format spec's merge section: an appended line landing under a neighbor's heading when both sides extend adjacent subsections. This ports the properties that made `cat_sort_uniq` work from notes to the tree; the `reviews/…` layout itself stays with the MR design's O6.

**The gate is a branch-protection workflow.** The Python rewrite's hook engine — branch router mapping glob patterns to workflows — gains a `review-gate` workflow alongside no-direct-push and linear-history: a push updating a protected branch must be a merge whose history contains a submitted `.review` approving the merged tip, from an eligible approver. Eligibility comes from a **`CODEOWNERS` file with email addresses**: the familiar pattern-per-line syntax, owners written as plain `email@example.org` so they match the format's `Verdict-reached-by: <Name> <<email>>` attribution directly. The gate matches the approving verdict's email against the owners covering the paths the merge touches, reading the `CODEOWNERS` of the protected branch's own tip — policy a work branch could edit is not policy. This replaces the tool spec's "planned `review-gate` hook" sketch, which scanned notes refs; the in-tree model means the gate reads review commits instead. Kernel-style trailer recognition can stay as a compatibility signal.

**Python surfaces.** The format spec is language-neutral and survives as-is. The tool spec is bound to the Go bubbletea TUI and gets superseded by a fresh, smaller spec rather than rewritten in place: the click CLI scaffolds either a scoped review of a merge commit (complete diff sections, the gate's approval object) or an empty open review for exploratory and continuous work, hands it to `$EDITOR`, and `gitflower review submit` commits it under `reviews/…`; the FastAPI web UI renders `.review` files read-only in the repo browser and the MR detail view (MR design O7). A TUI is a later possibility, not a rewrite target. The editor-based flow doubles as the agent flow — the format was designed to be written and read by LLMs without specialist tooling, so an agent reviews by appending events to the scaffold and submitting.

**Issues cross-over.** `## Issue` subsections stay review-scoped: they live and die with the review conversation. An issue that outlives the MR is promoted into an `issues/` file via the issues-view flow (a branch carrying the new file), and the review-side subsection gets resolved with a comment pointing at it.

## Convergence with the cute-devops review patterns

The pattern library describes review twice, and the two disagree with each other the same way the specs disagree with this issue: Merge Reviews 🔍 puts submitted `.review` files in the tree on a `review/merge-<sha>` branch and concludes with an empty `APPROVE:`/`REQUEST-CHANGES:` verdict commit; Continuous Review 🫧 keeps the review stream in `refs/notes/reviews` with a `[Review]` merge as the high-water line. The tree-first split above converges both around one storage rule — the tree holds every submitted review, notes hold only drafts.

**The continuous track submits through the tree too.** The `[Review]` high-water merge stops pointing at notes content and instead carries the session's `.review` file into the tree under `reviews/…` — the merge is the submission. Q6 then resolves as repurpose rather than delete: `gitflower review merge` survives as the continuous track's submit, and `continuous-review.md` on the pattern side updates its storage description to match.

**One approval signal.** The `Verdict-reached-by:` event in a submitted review is the authoritative approval — the gate parses exactly one signal. The pattern's empty verdict commits demote to optional greppable convenience or leave `merge-reviews.md`; keeping both authoritative would be two sources of truth, one always stale.

**The approval object can be the actual merge.** Merge Reviews insists the review targets the merge commit that lands, not a branch diff that may differ. The MR design's `/merge` ref makes that possible before `main` moves: the integrator's merge exists as an object ahead of the protected push. The approving review covers the merge commit, as decided above.

**The shipped CLI redirects before it lands.** `work/feature/review-cli` implements the notes-first model this issue demotes, and is unmerged — cheaper to redirect now than to rework after landing. Its parser, scaffold and TUI carry over unchanged; its notes persistence becomes the local draft layer — the autosave already is one — and `gitflower review submit` is added as the tree-first path. It also ships a Textual TUI from Debian `python3-textual`, which overtakes the no-TUI-commitment consideration below; the rationale stands for not *requiring* a TUI, but the superseded tool spec should describe the one that exists.

**Pattern-side edits.** cute-devops changes this issue implies, recorded here so the two repos move together: the verdict location in `merge-reviews.md`, the storage description in `continuous-review.md`, and the `review/` vs `reviews/` branch-prefix inconsistency between `merge-reviews.md` and the pure-git-workflows skill.

## Open questions

### Q3 — Self-approval

Eligibility is decided — `CODEOWNERS` with email addresses — but an author can be an owner, so the residue stays open: does the gate refuse an author approving their own merge, or merely surface it?

### Q6 — Fate of `gitflower review merge` and `[Review]` merges

The tool spec's `review merge` subcommand and its `[Review]`-merge base-ref detection predate the MR design, which derives everything from the MR branch history instead. Presumably both fold into the MR integration flow; confirm nothing else depends on `[Review]` markers before deleting them from the spec.

## Tasks

- [x] Q1: no diff-range section — open reviews serve pre-merge conversation and the continuous scaffold
- [ ] Spec the `reviews/…` submission-branch flow and the all-findings-resolved gate for the integration→`main` merge
- [x] Rewrite the *Storage* and *Multi-reviewer merge* sections of `dot-review-format.md` tree-first, demoting notes to draft state
- [ ] Spec the append-only merge semantics in `dot-review-format.md` (`merge=union` baseline, renormalizing renderers, the adjacent-subsection hazard)
- [ ] Spec the `review-gate` workflow in the hook engine, including approval-staleness recognition shared with the MR design
- [ ] Spec the `CODEOWNERS` file (email owners, pattern syntax, read from the protected branch's tip) and its evaluation in `review-gate`
- [ ] Write the fresh spec superseding `gitflower-review.md`: click CLI + `$EDITOR` flow, scoped-merge and open-review scaffolds (Q5 decided: supersede)
- [ ] `.review` rendering in the web UI (read-only; joins the MR detail view, MR design O7)
- [x] Editorial pass over `dot-review-format.md` (typos: "gitfßlower", "Loosley", "determin", "hierachy")
- [ ] Redirect `work/feature/review-cli` tree-first: notes persistence demotes to draft, `gitflower review submit` added
- [ ] File the cute-devops pattern edits (verdict location in `merge-reviews.md`, storage in `continuous-review.md`, review-branch prefix)

# Considerations

## Why tree-first

The MR design already rejected notes refs as shared review storage because notes don't transport by default and need out-of-band consolidation; repeating the argument here would just drift. The consequence for the format spec is what this issue records: the notes-first *Storage* section describes what is now the draft layer, not the system of record.

## Per-reviewer notes refs and cat_sort_uniq

The format spec's consolidator model (`refs/notes/reviews-<name>` merged via `cat_sort_uniq`) solved multi-reviewer concurrency for notes. Tree-first, git's ordinary merge machinery takes that job (Q2), and the consolidator section can be deleted rather than ported — keeping it would preserve a second concurrency mechanism nobody runs.

## Why no Python TUI commitment

Dependencies come from Debian apt packages only. Committing to a TUI means committing to a Debian-packaged TUI framework before one has been chosen, and the editor-plus-web split covers reading and writing without it. Revisit when someone actually misses it.

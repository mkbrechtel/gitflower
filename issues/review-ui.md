---
#SPDX-FileCopyrightText: 2026 Markus Katharina Brechtel <markus.katharina.brechtel@thengo.net>
#SPDX-License-Identifier: EUPL-1.2
title: Review UI — web and TUI, one behavior
id: f0bf5eac-4a8a-4846-bda8-dfb7ef9cd9e2
status: open
created: 2026-07-20
---

# Review UI — web and TUI, one behavior

The review feature's interactive surfaces, split out of the retired `gitflower-review.md` tool spec (its gate half became [`../docs/spec/review-gate.md`](../docs/spec/review-gate.md)). One behavior model over the `.review` format ([`../docs/spec/dot-review-format.md`](../docs/spec/dot-review-format.md)), rendered by two frontends: the FastAPI web UI and a TUI. **Web and TUI expose the same behavior** — the same session model, the same events, the same derived states; only presentation differs.

## The behavior model

**Scaffold.** `gitflower review` scaffolds either a scoped review of a merge commit — complete diff sections per the format — or an empty open review for exploratory and continuous work. Re-opening is non-destructive: an existing draft loads as-is.

**Draft.** Drafting state lives in the local `refs/notes/reviews` ref keyed by the reviewed object, autosaved (debounced, ~2s), never transported. The scaffold can also be handed straight to `$EDITOR`; the editor flow doubles as the agent flow.

**Submit.** `gitflower review submit` turns the draft into a review commit under `reviews/` on a `reviews/…` branch; merging that branch into the integration branch publishes it. `gitflower review merge` survives as the continuous track's submission — the `[Review]` high-water merge carrying the session's file into the tree.

**Read tracking.** Lines start unread and flip by walking (auto-scroll at a read rate), dwell (visible long enough), or manually; on save, contiguous spans coalesce into `* Read-by: …; begin` / `; end` range markers, `* Skipped-by:` the same for explicit skips.

**Session behaviors both frontends provide**, carried over from the retired spec: comment-from-the-bottom (an event entered past a section's end inserts at its top — byte-identical on disk); an open-question lane listing every `- Question-asked-by:` without an answer (the derived clarification-required state); resolved issues rendered collapsed; duplicate issue titles flagged but not refused; `## Remark` numbering derived from position, never stored; a meta peek showing the heading's meta lines and unknown keys verbatim; foreign note bodies auto-imported as `## Note` subsections on first open.

## State

`work/feature/review-cli` ports the parser, scaffold, notes layer, session, and a Textual TUI from the Go implementation — built against the notes-as-truth model, so it needs the redirect tracked in [`review-approval.md`](./review-approval.md): notes demote to draft, `review submit` is added. The web UI today renders nothing review-related; first step is read-only rendering in the repo browser and the MR detail view.

## Open questions

### Q1 — Web write path

Same behavior in the web UI means writing reviews from the browser. Blocked on authentication and who-may-review — the same blocker as the issues-view filing flow (Phase 6 there).

### Q2 — Which TUI-era refinements are requirements

Read-rate pacing, dwell tracking, and walk mode came from the Go TUI. Decide per behavior whether it is part of the shared model (both frontends must have it) or a TUI presentation detail.

## Tasks

- [ ] Redirect `work/feature/review-cli` to the draft/submit split (shared task with review-approval.md)
- [ ] Read-only `.review` rendering in the web UI: repo browser and MR detail view
- [ ] One session model shared by TUI and web, presentation layers on top
- [ ] Web write path, once authentication lands (Q1)

# Considerations

## Why one behavior model

Two frontends implementing review logic independently drift; the format is the integration surface, and a single session model over it keeps both frontends honest renderers. This is the same "tooling is a view" doctrine the rest of gitflower follows.

## Carried from the retired spec

Comment-from-the-bottom exists because the natural moment for a wrap-up comment is after reading, not before — the shortcut avoids a second cursor concept. Scaffolding subcommands (`review begin` / `diff` / `files` …) stay collapsed into the top-level invocation until scripted use proves out — the on-disk format is the integration surface for other tools. The Go implementation predates the current format spec (H3 comment headings, no recipes, no header block, singular notes ref) and is prior art only.

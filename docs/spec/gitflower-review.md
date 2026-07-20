---
#SPDX-FileCopyrightText: 2026 Markus Katharina Brechtel <markus.katharina.brechtel@thengo.net>
#SPDX-License-Identifier: EUPL-1.2
---

# `gitflower review` — TUI and CLI for `.review` files

`gitflower review` is gitflower's front-end for the `.review` format. It scaffolds a review on the current branch, runs a bubbletea TUI for interactive reading and commenting, and persists the draft to the local `refs/notes/reviews` git notes ref (keyed by the reviewed commit's SHA, with an optional on-disk mirror); submission lands the review in the tree under `reviews/` per the format spec's *Storage*. The on-disk format is documented separately in [`dot-review-format.md`](./dot-review-format.md); this file specifies the tool — invocation, flags, TUI behaviour, persistence, and how the tool's output maps to the format spec. Where the two disagree, the format spec is authoritative and the tool gets rewritten to match.

## Invocation

`gitflower review [--branch <branch>]` scaffolds a new `.review` for `<branch>` (defaulting to the current branch) and opens the TUI. If a `.review` already exists on the notes ref for the reviewed tip commit it is loaded as-is — re-running is non-destructive.

**The default scaffold covers everything that changed since the last review.** The base ref is the tip of the most recent `[Review]` merge on the branch (falling back to `main`), and the scaffold emits the header block (`dot-review-File-Version: 0`, `dot-review-Intro:`, `dot-review-Docs-Link:`, closing `---`), the `# Review` heading with its meta lines (`SPDX-FileCopyrightText`, `SPDX-License-Identifier`, `Review-Head-Commit`, `Review-Branch`, `Created-By`), one `# Diff <base>..<tip> $ git diff <base>..<tip>` section spanning the full delta, and one `# Commit <sha> $ git show <sha>` section per commit in `base..tip`. The reviewer can add more sections on top (`# Repo Tree`, additional `# Commit` sections for earlier commits, `## File` entries via the Tree sidebar, …) but the default already names every artefact that changed since the last in-history review.

`--empty-review` opts out of the change-covering scaffold and writes only the header block plus the bare `# Review` heading with its meta lines. Useful when the reviewer wants to assemble the review piecewise from the TUI's Tree / Commits sidebars rather than start from the full diff.

With `--no-tui` the scaffold is written and the process exits with a "where your review went" footer: the live notes-ref pointer (follows future edits), the immutable blob SHA snapshot for verbatim recovery, and the file mirror path if `-o` was set.

## Flags

- `--base <ref>` — base ref for the review's diff range. Defaults to the tip of the most recent `[Review]` merge on the current branch, falling back to `main`.
- `--notes-ref <ref>` — notes ref to read and write. Defaults to `refs/notes/reviews`. Mostly a testing knob; production reviewers stick with the default so the gate hook and other tools find content where they expect it.
- `-o <path>` — mirror the `.review` body to a file at `<path>` in addition to the notes ref. The notes ref stays source of truth; the file is rewritten on every save.
- `--no-tui` — scaffold the `.review` and exit without launching the TUI.
- `--empty-review` — skip the change-covering scaffold. Writes only the header block and the bare `# Review` heading; the reviewer adds sections from the TUI.
- `--read-rate <lines/sec>` — auto-read pacing for the TUI (default `10`). Lines that remain visible without scroll for `(visible-lines / read-rate)` seconds flip from unread to read automatically.
- `--with-timestamps` — opt in to per-event timestamps. Off by default for privacy reasons. When on, every reviewer event grows a ` @<RFC3339>` slot between the email and the optional `; <args>`.

## Subcommands

### `gitflower review merge` (build tag `with_review_merge`)

Attaches the review to the branch history with a merge commit. The merge commit's subject is prefixed `[Review]`, and its body carries a verdict-count summary, a literal `git show <notes-sha>` recipe pointing at the notes-commit that holds the `.review` body, and the verdict trailers copied verbatim. The merge carries the `.review` body into the tree at its `reviews/…` path — submission through the tree is the point of the merge; the notes draft stays local.

The exact mechanism by which the merge brings the notes-ref content in as the merge's second parent is unsettled — the spec at this point only sketches the commit-message shape, not the graph shape. See *Considerations*: §*Attaching reviews to history* in [`dot-review-format.md`](./dot-review-format.md) for the open candidates (orphan archive commit, `-s ours` of the notes-ref tip with a filter step, content-addressed second parent, tree-blob-only). The implementation currently uses the orphan-archive shape; that may change before format v1.

Compiled out by default; rebuild with `go build -tags with_review_merge`.

## TUI

The on-disk `.review` is the source of truth. Opening parses what's there; nothing implicit re-runs `git diff` or `git log`. Every mutation re-renders the in-memory session and writes back through the same notes-ref path — debounced at two seconds, plus an immediate write on explicit save.

### Modes

**Tree mode.** Sidebar focused; one section selected; a peek pane shows the section's content. Used for navigating between sections and opening files, issues, or commits.

**Diff / file mode.** Entered by drilling into a file or commit. The cursor locks to one line in the main pane and reviewer events anchor to that line. `←` / `h` returns to tree mode.

### Sidebar

The sidebar surfaces the format-spec sections under these headings:

| Sidebar entry | Surfaces |
|---|---|
| **Sources** | `# Review` meta lines (`Review-Head-Commit`, `Review-Branch`, `Created-By`, …) and an unknown-keys panel — read-only. |
| **Verdicts** | The `- Reviewed-by:` / `- Approved-by:` / `- Rejected-by:` verdict events under `# Review`. |
| **General Issues** | `## Issue` subsections under `# Review`. |
| **Changes** | The `# Diff` section, folder-tree-grouped; drilling opens the file's `## File "<path>" modified` / `created` / `deleted` / `moved` subsection. |
| **Commits** | The `# Commit` sections in oldest-first order. |
| **Tree** | The `# Repo Tree` / `# Subfolder` sections at the tip SHA, expandable. |
| **File Review** | The `## File "<path>" $ git show <sha>` subsections the reviewer has opened in object-view mode. |

Sidebar keys: `j` / `k` move within a section, `Tab` cycles sections, `→` / `l` / `Enter` drill into the selected item, `i` opens a new-issue overlay (on General Issues), `e` edits the selected item, `q` quits.

### Source / diff / file pane keys

In diff or file mode the cursor sits on a single line; comments and markers anchor to it.

- `j` / `k` — move cursor by one line.
- `Space` — *walk*. The viewport auto-advances at `--read-rate` line/sec, marking traversed lines read.
- `c` or `Enter` — open the comment edit overlay anchored to the current line.
- `!` or `?` — open the question edit overlay.
- `a` / `g` — react Like (`Reacted-by: …; 👍`). `b` reacts Dislike (`; 👎`).
- `u` — mark the current line unread.
- `w` — toggle line-wrap.
- `>` / `<` — set the reviewer's verdict event.
- `n` / `N` — cycle to the next / previous event anchored at or near the current line.
- `d` — delete the event under the cursor.
- `s` — save now. Auto-save is debounced two seconds; manual save mostly exists for tests.
- `←` / `h` — return to tree mode.

### Event entry overlays

Single-line overlay for `Reacted-by:` (no body). Multi-line overlays with a text area for `Commented-by:`, `Question-asked-by:`, and verdicts (pre-populating the reviewer's current one). The `## Issue` overlay has a title field plus a body area; `Tab` switches focus between them. Submit with `Alt+Enter` or `Ctrl+S`; cancel with `Esc`.

Answers to questions are entered the same way as comments, anchored to the parent `- Question-asked-by:` event so they render as nested `- Answer-given-by:` items under it.

### Read tracking

Lines start unread, rendered with a stronger colour. They flip to read in three ways:

1. **Walking with `Space`** auto-scrolls at `--read-rate` and marks each line read as it passes.
2. **Dwell** — lines visible without scroll for `(visible-lines / read-rate)` seconds flip automatically.
3. **Manual** — `u` toggles the current line back to unread.

On save, contiguous read spans coalesce into range-marker events on the surrounding `> ` quoted body and emit as paired `* Read-by: Name <email>; begin` and `* Read-by: …; end` items anchored to the first and last covered patch lines. The `*` bullet distinguishes range markers from the `-` bullet used by every other reviewer event. `* Skipped-by: …; begin` / `; end` works the same way for ranges the reviewer explicitly skipped.

### "Comment from the bottom"

A reviewer who has just finished reading a section is past its last `> ` line (the EOF marker), not back at the top where a section-anchored event lives. The TUI accepts a `Commented-by:` / `Question-asked-by:` / `Reacted-by:` event submitted from past the EOF marker and inserts it at the **top** of the section. On disk the result is byte-identical to writing at the top — the bottom-of-section input is purely a UX shortcut.

### Sidebar UI details

**Sidebar Remark numbering.** Multiple `## Remark` subsections render as "Remark 1", "Remark 2", … in the sidebar for navigation. The on-disk heading stays bare `## Remark`; the numbers are positional, not stored.

**Open-question lane.** A separate sidebar entry lists every `- Question-asked-by:` with no `- Answer-given-by:` under it, so questions don't get lost in long reviews. Surfaces the derived clarification-required state.

**Resolved-issue display.** `## Issue` subsections that carry a `- Resolved-by:` line render collapsed/dimmed in the sidebar. Removing the line re-opens the issue in the live view.

**Duplicate-issue flag.** Two `## Issue` subsections with the same title get a warning marker in the sidebar; the writer doesn't enforce uniqueness, but the TUI surfaces dupes so reviewers can dedupe.

**`# Review` peek pane.** When the cursor is on the `# Review` heading, the right pane lists the meta lines and any unknown keys verbatim so the reviewer can sanity-check what was recorded.

## Persistence

**Notes ref.** Default `refs/notes/reviews` (the local draft layer, keyed by reviewed commit SHA). While a review is being written the note is the working copy — reads prefer it over any on-disk mirror; the submitted, shared form is the in-tree file per the format spec's *Storage*. The "find the last review" question is answered by walking commits backwards from HEAD for the most recent `[Review]` merge, not by inspecting the notes ref directly.

**File mirror (`-o`).** Optional. The mirror is rewritten on every save; reads still come from the note. Useful for diffing two reviews on disk or for tooling that doesn't speak git notes.

**Save semantics.** Full rewrite, not append-only. Every mutation (event added, range coalesced, verdict cycled, …) re-renders the in-memory session and writes to the notes ref (plus the file mirror if set). Auto-save debounces at two seconds; `s` saves immediately. Writes go through go-git's notes machinery.

**Auto-import on first open.** If the notes ref already has a non-`.review` body (kernel-style sign-offs, CI bot output, freeform notes), the TUI imports it into the new `.review` as a `## Note $ git notes --ref=… show …` subsection under `# Review`. Kernel-style trailers stay grep-able in the imported body so the planned `review-gate` hook keeps recognising sign-offs after the conversion.

## Notes-ref interop

The `refs/notes/reviews` ref is shared territory, not gitflower-exclusive. Any note body on it is a recorded review action in git. `.review`-format bodies (first line is `dot-review-File-Version:`) are what gitflower reads and writes; other bodies — freeform sign-offs, kernel-style trailers (`Reviewed-By:`, `Acked-By:`, `Signed-off-by:`), CI-bot output, anything — coexist on the ref untouched.

The `.review` parser ignores notes that don't begin with `dot-review-File-Version:`. The writer never overwrites them on save.

### Planned `review-gate` workflow

The `review-gate` branch-protection workflow blocks the mainline push unless every merge onto the integration branch has a submitted in-tree `.review` covering that merge commit and meeting the required conditions — **approval**: at least one `- Approved-by: …` from an eligible approver and no standing `- Rejected-by:` from one; **review**: at least one `- Reviewed-by: …` with no unresolved findings. Which conditions are required is per-branch configuration (either or both); resolution is validated over further merges into the integration branch. The verdict events are kernel-trailer-shaped, so trailer-greppers read them natively; kernel trailers in commit messages stay recognised as a compatibility sign-off signal. The gate reads review commits, never notes — drafts gate nothing.

## References

- [`dot-review-format.md`](./dot-review-format.md) — the on-disk file-format spec this tool reads and writes.
- The in-tree-review pattern (`patterns/approaches/in-tree-review.md`).

## Considerations

### "Comment from the bottom" rationale

The natural moment to leave a wrap-up comment is right after finishing reading a section, not before opening it. The "bottom inserts at top" shortcut lets the TUI accommodate that without introducing a second cursor concept (one for line-anchored events, one for section-anchored ones).

### Non-`.review` notes interop philosophy

Keeping the format opt-in: teams already using `git notes` for review records get the future `review-gate` hook for free, and teams that want the full `.review` machinery get richer state on top of the same notes ref. The hook itself is a future feature — this spec only declares that the notes ref is shared territory.

### Scaffolding subcommands deliberately not split out

An earlier sketch had `gitflower review begin` / `diff` / `commit` / `commits` / `files` / `edit` as separately invocable scaffolding sub-commands so scripts could compose a `.review` piecewise. The current tool collapses all of this into the top-level invocation: the scaffold runs implicitly on first open, mutations happen through the TUI, and the on-disk format itself is the integration surface for any other tool that wants to read or extend a `.review`. The decomposed sub-commands can be added later if scripted use proves out; for now, fewer commands is fewer commands to learn.

### Implementation lag

The current Go implementation (`apps/gitflower/review/`, `apps/gitflower/tui/`) was written against an earlier draft of the format spec and does not yet match this document. Notable drift: events emit as `### Comment (From: …)` H3 headings instead of `- Commented-by: …` list items; section and per-file headings lack the `$ git …` reproduction recipe; the header block is missing; range markers emit as paired `### ReadStart` / `### ReadEnd` H3s instead of `* Read-by: …; begin` / `; end` list items; the default notes-ref constant is `refs/notes/review` (singular) instead of `refs/notes/reviews`. The spec here describes the *target* behaviour; rewriting Parse and Render to match is tracked separately.

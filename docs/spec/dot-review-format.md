---
#SPDX-FileCopyrightText: 2026 Markus Katharina Brechtel <markus.katharina.brechtel@thengo.net>
#SPDX-License-Identifier: EUPL-1.2
---

# `.review` *(dot-review)* — File format for git based code reviews!

A single-file format for one code review. Loosley based on Markdown, with a fixed chapter structure: H1 = section (commit/diff/tree), H2 = sub-section (content/diff), list items = reviewer events. Patch / file content is `> `-quoted verbatim from git so the review reads like an annotated diff.

This file specifies the on-disk format. The reference reader/writer is gitfßlower; its commands, TUI, and notes-ref integration are documented separately in [`./gitflower-review.md`](./gitflower-review.md).

## Goal

**Zero implicit scope.** Everything the review covers lives in the file; readers and tools never guess from external context.

**Readable.** If you just read the file you understand what's going on. Suitable for long-term preservation and for LLMs reading the review without specialist tooling.

**Self-describing git references.** Section headings inline an `@ <git command>` recipe with literal commit, tree, and blob OIDs, so the review names the exact objects it covers — independent of any refs that may later move.

**Optional timestamps**, off by default for privacy reasons. Reviewer attribution is `Name <email>`; events grow a trailing ` @<RFC3339>` slot when the writer opts in.

## Header

Every `.review` file starts with a header block of `Key: value` trailer lines, one per line, terminated by `---` on its own line:

```
dot-review-File-Version: 0
dot-review-Intro: This file uses the .review format — a patch-quoting markdown-ish file format with a fixed chapter structure. Every heading is a review section, every `> ` line is verbatim git content,  every list item (`-` or `*`) is a reviewer reaction.
dot-review-Docs-Link: https://cute-devops.patterns.how/apps/gitflower/docs/spec/dot-review-format
---
# Review
…
```

**`dot-review-File-Version:`** is the only required key — an integer, currently `0` — and **must be the very first line of the file**. Readers probe this exact first-line shape to recognise a `.review`; a file that doesn't begin with `dot-review-File-Version:` is not a `.review`. Version 0 is unstable: breaking changes may land at any time, and v0 readers/writers are not guaranteed to round-trip across spec revisions. The first stable release bumps to `1`.

**`dot-review-Intro:` and `dot-review-Docs-Link:`** are always emitted by the writer so a reader who's never seen a `.review` file has an immediate pointer to documentation. The Intro is a one-paragraph description of the format; the Docs-Link points at the full spec.

**Implementation-specific keys** are prefixed `X-<app>-` (e.g. `X-gitflower-…:` for gitflower-only state), mirroring the mail-header convention for non-standard extensions. Unknown header keys are preserved per the generic rule below.

Information in header keys is generally not shown to the user when viewing the file.

The closing `---` must be on its own line, followed by the line where the body starts with `# Review`.

## Generic body format rules

The `.review` format is strictly line oriented where the characters at the beginning of the lines determin the purpose of everything that is in that line. Line-order matters and establishes reference and hierachy by indentation.

While it is possible to edit a `.review` file locally, a server side gate might ensure edits as append-only insertions in order to merge multiple actions by multiple reviewers nicely.

Unknown lines in the body should be displayed to the user in the relevant section at the relevant position as-is. Also the parser doesn't fail on them. This preserves backwards-compatibility for functionality that are just added.

**Indentation marks containment.** One space indent marks content that belongs directly to a `## Subsection`. Two space indent marks content that belongs to the preceding reviewer-action list item. In both cases the block runs as long as the indented lines continue and ends as soon as the next line-block begins (another event, another heading, a `> ` quoted line, …). Unindented column-0 lines belong to the section/subsection structure itself.

Reviewer actions are list items with the shape `[<indent-spaces>]<bullet> <Keyword>-by: Name <email>[ @<RFC3339>][; <args>]`, optionally followed by a body indented two spaces below. The keyword is a kebab-cased past-tense verb (`Read-by:`, `Commented-by:`, `Verdict-reached-by:`, …) mirroring git's trailer convention (`Reviewed-By:`, `Signed-off-by:`). The bullet splits range markers (`*` for `Read-by:` / `Skipped-by:`) from everything else (`-`). The optional ` @<RFC3339>` slot carries an event timestamp when the author is opted in; the optional `; <args>` slot carries kind-specific parameters (an emoji, a verdict state, `begin` / `end`, …). Per-event semantics and multiplicity rules live under *Reviewer events*. Unknown `-by:` keys are preserved verbatim and displayed in place, same as any other unknown line.

**Paths in `.review` content are JSON-encoded strings** (RFC 8259). Anywhere a path appears as content — section heading titles, tree-listing body entries, anywhere else — wrap it in double quotes and escape special characters per JSON string rules: `\"`, `\\`, `\n`, `\t`, control-character `\u00xx` escapes. Stays parseable even for paths containing spaces, quotes, or control characters. Recipe-side arguments (after `@`) are the exception: they follow git/shell quoting rules since the recipe is meant to be pasted into a shell.

When adding new functionality to the format make sure that someone who knows how to read markdown can understand whats going on even without consulting the format specification.

## Top-level structure

A `.review` file scopes to **a single git object** — a blob, a tree, a commit, or a merge commit — identified by its SHA. Each file contains exactly two top-level sections: `# Review` (reviewer-authored: verdict, meta, comments, issues, remarks) followed by one object section whose shape is fixed by the object's kind. Both are mandatory; the object section's heading carries an `@ <git command>` recipe that reproduces the quoted body verbatim.

**The part after `@` in every section heading is a literal, copy-paste-runnable git command** that reproduces what's quoted below it. Title on the left, reproduction command on the right.

**`# Review`** holds the reviewer-authored content: meta lines, verdict-reached-by lines, and `## Note` / `## Remark` / `## Issue` subsections. Unique and mandatory.

The object section is one of:

**`# Blob <sha> @ git cat-file blob <sha>`** — content of a single file blob, line-numbered. Reviewers anchor events to specific lines.

**`# Tree <sha> @ git ls-tree <sha>`** — listing of a tree object (one `> ` line per entry). Reviewers anchor events to entries or comment on tree-level concerns.

**`# Commit <sha> @ git show <sha>`** — a non-merge commit: headers + message + per-file diff. Per-file `## File "<path>"` subsections embed the per-blob review of the touched blob inline (see *Cross-references*) so the commit review is self-contained.

**`# Merge-Commit <sha> @ git show -m <sha>`** — a merge commit with **N explicit `## Diff from parent <N> @ git show -m -<N> <sha>` subsections, one per parent, including empty ones**. Each parent subsection carries the same per-file structure as a `# Commit`. The presence of all N subsections — even empties — makes the merge's structural shape reviewable.

Each `.review` covers exactly one object. Multi-artefact reviews (a feature branch's diff, a tree-browsing session) compose at storage time: each artefact gets its own `.review` note, keyed by its SHA in `refs/notes/reviews`. The unifying principle is **every review anchors to a git artefact addressed by its SHA** — no review action lives outside that lattice.

## `# Review` section

Holds the structured shapes the parser recognises below — meta lines, verdict-reached-by lines, and `## Note` / `## Remark` / `## Issue` subsections. No unindented free prose.

### Meta lines

Meta lines start with `- ` and follow a `key: value` shape:

```
# Review
- SPDX-FileCopyrightText: 2026 Markus <markus@example.org>
- SPDX-License-Identifier: EUPL-1.2
- Review-Head-Commit: 2d2442633399f38197249ae9f30b001e0943564a
- Review-Branch: experiments/stack-review
- Created-By: Mirian <mirian@example.org>
```

`Review-Head-Commit` is what HEAD was when the review file was created — the *point in time* of the review, not a commit being reviewed.

**SPDX license / copyright lines** live here as meta lines. The `.review` is its own copyrightable artefact — reviewers may want to license their prose separately from the code under review — and reviewers naturally edit `# Review` content. REUSE-style scanners pick the tags up unchanged through the leading `- ` (verified against REUSE 5.0.2 / spec v3.3).

### Verdict-reached-by lines

`- Verdict-reached-by: <Name> <<email>>; <state>` followed by an optional double-space-indented body:

```
- Verdict-reached-by: Markus <markus@example.org>; RequestedChanges
  Needs a test before merge.

  Multi-paragraph summary works the same as comments — indent the body
  by two spaces so it nests under the list item.
```

At most one verdict per (Name, email) — submitting again replaces in place.

`<state>` is one of:

- `Open` — initial / "no verdict yet, still reading"
- `ClarificationRequired` — "I'd give a verdict but I have unanswered questions blocking that". Distinct from `RequestedChanges`: the author hasn't been asked to do anything yet, they've been asked to *explain*. Naturally paired with one or more open `- Question-asked-by:` events elsewhere in the file.
- `RequestedChanges` — needs work before merge
- `Approved` — good to merge
- `Denied` — reject; this work should not land

PascalCase, like every other keyword. Unknown states are preserved verbatim and treated as `Open` for any sort / filter.

### Note subsections

Quote the body of an arbitrary **git note** inline. Any note from any ref the reviewer wants to pull in: a freeform note that already sat on `refs/notes/reviews`, linter output stored on `refs/notes/lint`, a CI bot's `refs/notes/ci-results`, an audit trail on `refs/notes/commits`, whatever the workflow uses.

Shape: `## Note @ <git command>` where the recipe fetches the note. Body uses the *Object body* shape (see *Body shapes* below) — quoting line-by-line lets a reviewer pin a comment to a specific line of the note.

```
## Note @ git notes --ref=refs/notes/go-lint show 2d2442633399
> 1: greet.go:14:2: warning: shadow declaration of 'err'
> 2: greet.go:27:5: warning: unused variable 'tmp'
> 3: server.go:88:1: warning: function exceeds cyclomatic threshold
- Commented-by: Markus <markus@example.org>
  The cyclomatic warning on line 3 is intentional — the handler
  needs to dispatch on six request kinds. Suppressed in
  `lintignore`.
- Reacted-by: Alice <alice@example.com>; 👍
```

The recipe is the source-of-truth pointer; a Note body is never rewritten — the lines came verbatim from `git notes show`. Notes don't need resolving. Multiple `## Note` subsections per review are fine.

### Remark subsections

`## Remark` H2 items hold free-form reviewer commentary that *doesn't need resolving* — the unstructured counterpart to Issues. Use one for each "thing I want to say but isn't a tracked work item": a short summary, pointers to related reviews, design context, anything that's reference rather than ask.

Shape: H2 heading (no title, no `@ <recipe>` — Remarks are pure reviewer output), then one-space-indented paragraphs, then one or more `- Remarked-by: Name <email>` signature lines. Reviewer events (`- Commented-by:`, `- Reacted-by:`, `- Question-asked-by:`, `- Answer-given-by:`) can appear inside, same as in any other section.

```
## Remark
 First time we're touching the legacy auth path in this branch.
 Worth flagging because the surrounding code has the "here be
 dragons" comment from the 2021 incident.
- Remarked-by: Markus <markus@example.org>
- Reacted-by: Alice <alice@example.com>; 👍

## Remark
 Tested manually with the staging account; CI covers the happy
 path, edge cases are in #ops-followup.
- Remarked-by: Markus <markus@example.org>
```

Signatures (`- Remarked-by: Name <email>`) carry no body — they record who made the remark. First signature is the creator; subsequent ones are co-signers who endorse the remark. At most one signature per (author, remark) — re-signing is a no-op.

Multiple `## Remark` subsections per review are fine — each its own item, in the order the reviewer added them. The on-disk heading stays bare `## Remark`; any numbering ("Remark 1", "Remark 2", …) is derived from position by the reader, not stored.

No resolve workflow — remarks are reference, not work. If a remark turns into actionable work, promote it to an `## Issue` and remove it from here.

### Issue subsections

`## Issue <title>` H2 items hold free-form issues about the change as a whole — code-style nits that span files, naming conventions, follow-up work that should land but not block this MR, anything that isn't tied to a specific line, file, commit, or diff.

Shape: H2 heading with title, one-space-indented description block, then one or more `- Issued-by: Name <email>` **signature lines**, then any reviewer events (comments, reactions, questions, answers).

```
## Issue name uses snake_case but project uses camelCase
 Several added identifiers (`parse_lines`, `total_count`) break
 the existing convention. Worth a sweep before merge.

 Multiple description paragraphs work — each line stays at one
 space of indent so it parses as the issue's body, not as a
 new top-level paragraph that would close the section.
- Issued-by: Markus <markus@example.org>
- Issued-by: Alice <alice@example.com>

- Commented-by: Bob <bob@example.com>
  Agreed — rename across the board, not just the new code.

- Reacted-by: Carol <carol@example.com>; 👍
```

Signatures (`- Issued-by: Name <email>`) carry no body — they're the issue's owners. The first signature is the creator; subsequent ones are co-signers who've made the issue their own (often when they hit the same problem reading further). At most one signature per (author, issue) — re-signing is a no-op.

Un-signing means deleting your own signature line; the issue stays as long as at least one signature remains. An issue with zero signatures is orphan.

**Resolving an issue**: add a `- Resolved-by: Name <email>` line inside the issue's body. Resolved is a marker event — no body, no parameter, just attribution — and one of them anywhere inside the issue closes it.

```
## Issue name uses snake_case but project uses camelCase
 Several added identifiers break the existing convention.
- Issued-by: Markus <markus@example.org>

- Commented-by: Alice <alice@example.com>
  Pushed the rename in commit abc1234.

- Resolved-by: Markus <markus@example.org>
```

At most one `- Resolved-by:` per (author, issue) — re-resolving is a no-op. Any signer can resolve; resolving by someone who hasn't signed is fine too (e.g. the author of the fix closes a reviewer's issue). To re-open, delete the `- Resolved-by:` line — there's no explicit "unresolve" event.

No `@ <recipe>` on the heading: issues are pure reviewer output, nothing to reproduce from git.

Multiple `## Issue` subsections under `# Review` are fine — each its own item. The title is freeform; uniqueness is not enforced.

## Git-Content body shapes

Three generic `> `-quoted body shapes for git output. Every section / subsection that quotes git content (`# Blob` body, `# Commit` per-file subsections, `# Merge-Commit` per-parent per-file subsections, `## Note` subsections, embedded per-blob review subsections) uses one of these.

### Object body

The full contents of a single git object (a blob, typically), every line emitted as `> <N>: <line>`:

```
> 1: package greet
> 2:
> 3: import "fmt"
```

### Diff body

A two-blob comparison, line-numbered before the diff sign so a reader can recover the position even from a truncated hunk:

```
> @@ -1,4 +1,5 @@
> 1 1: alpha
> 2: -beta
> 2: +BETA
> 3: +inserted
> 3 4: gamma
> 4 5: delta
```

The gutter mirrors git's `@@ -<old> +<new> @@` convention: old (left) before new (right), `-` before `+` for changed lines:

- `> <old>: -<text>` — deleted line, `<old>` is the old-side number
- `> <new>: +<text>` — added line, `<new>` is the new-side number
- `> <old> <new>: <text>` — context line, old number first, new number second, matching `@@ -<old> +<new> @@` left-to-right.


### Deletion body

A file that's gone in the new tree, presented end-to-end as if it were a diff that deletes every old-side line:

```
> 1: -package greet
> 2: -
> 3: -import "fmt"
```

Reads more obviously as "this file is gone" than a plain content listing would.

## `# Blob <sha> @ git cat-file blob <sha>` section

A per-blob review. Heading carries the blob SHA and the recipe that reproduces the file content. Body is the *Object body* shape — every line of the blob as `> <N>: <line>`. The blob may be referenced by any number of paths across the repo's history; the per-blob review captures commentary on the content itself, independent of path.

```
# Blob 1a2b3c4d @ git cat-file blob 1a2b3c4d
> 1: package greet
> 2:
> 3: func Hello(name string) string {
> 4:     return "Hello, " + name
> 5: }
```

The `# Review` paired with a `# Blob` typically holds line-level commentary (events anchored to specific `> N:` lines) plus an overall blob-level verdict if the workflow uses verdicts at blob granularity.

## `# Tree <sha> @ git ls-tree <sha>` section

A per-tree review. Heading carries the tree SHA and the `git ls-tree` recipe. Body is the ls-tree output, one entry per `> ` line, **paths JSON-encoded**:

```
# Tree b7c8d9e0 @ git ls-tree b7c8d9e0
> 100644 blob a1b2c3d4    "README.md"
> 100644 blob d4e5f6a7    "Makefile"
> 040000 tree e5f6a7b8    "src"
> 040000 tree f0a1b2c3    "docs"
```

Per-tree reviews comment on the directory's shape itself (missing file? wrong permissions? unexpected subtree?) rather than on any specific file's content — those live in the per-blob reviews of the listed blob SHAs, fetched separately by their own notes.

## `# Commit <sha> @ git show <sha>` section

A per-commit review of a non-merge commit. Heading reproduces the commit's full picture (headers + message + diff). Body has two parts:

1. A quoted block with the commit's headers and message.
2. One `## File "<path>" …` subsection per file touched by the commit, choosing the lifecycle-appropriate heading and body shape.

```
# Commit dd56c2ea01a7 @ git show dd56c2ea01a7
> From: Author <author@example.org>
> Date: Wed, 17 May 2026 10:00:00 +0000
> Subject: Add feature B
> Message:
> > First paragraph of the commit message.
> >
> > Second paragraph after a blank line.

## File "b.txt" created @ git show a1b2c3d
> 1: feature B
> 2: initial implementation
> 3: line 3
```

Line shapes inside the header/message quoted block:

- `> From: <Name> <<email>>` — author header (one space after `>`).
- `> Subject: <subject>` — single-line subject.
- `> Date: <RFC2822>` and any other commit headers — one space after `>`.
- `> Message:` — header line introducing the commit message body.
- `> > <message line>` — message body lines as a **nested blockquote**. 

Per-file subsection heading shapes by lifecycle:

| Lifecycle | H2 heading | Body |
|---|---|---|
| Modified | `## File "<path>" modified @ git diff <oldblob>..<newblob>` | *Diff body* |
| Created | `## File "<path>" created @ git show <newblob>` | *Object body* |
| Deleted | `## File "<path>" deleted @ git show <oldblob>` | *Deletion body* |
| Moved (pure rename) | `## File "<oldpath>" moved to "<newpath>"` | empty — nothing to reproduce |
| Moved + modified | `## File "<oldpath>" modified and moved to "<newpath>" @ git diff <oldblob>..<newblob>` | *Diff body* |

### Cross-references: embedded per-blob review

After each per-file subsection, the commit review embeds the corresponding **per-blob review** as a peer H2 subsection — keeping the commit review self-contained even though the per-blob commentary lives in its own note:

```
## File "b.txt" created @ git show a1b2c3d
> 1: feature B
> 2: initial implementation
> 3: line 3

## Blob "b.txt" review @ git notes --ref=reviews show a1b2c3d
> dot-review-File-Version: 0
> dot-review-Intro: …
> dot-review-Docs-Link: …
> ---
> # Review
> - Verdict-reached-by: Markus <markus@example.org>; Approved
>
> # Blob a1b2c3d @ git cat-file blob a1b2c3d
> 1: feature B
> 2: initial implementation
> 3: line 3
>
>   - Commented-by: Alice <alice@example.com>
>     Looks clean.
```

The body is the per-blob `.review` note quoted verbatim using the *Object body* shape — every line `> `-prefixed. The reader of the commit review thus sees both the line-level commentary on the blob (from its per-blob review) and the diff context (from the per-file diff subsection) without fetching a second note.

The recipe (`@ git notes --ref=reviews show <newblob>`) is the source of truth; whether the embedded body is freshly fetched at render time or snapshotted at write time is a tool choice. The reader can always re-run the recipe to get the latest.

For the modified lifecycle, the *new* blob's review is embedded; the old blob's review can be referenced separately if relevant.

## `# Merge-Commit <sha> @ git show -m <sha>` section

A per-merge-commit review. Heading uses `git show -m <sha>` — the merge-aware show that emits one diff per parent. Body holds the commit's headers and message in the same quoted shape as `# Commit`, followed by **N `## Diff from parent <N> @ git show -m -<N> <sha>` subsections, one per parent in order, including empty ones**. Each parent subsection carries per-file `## File "<path>" …` subsections in the same lifecycle family as a regular commit review.

```
# Merge-Commit 51c2c712 @ git show -m 51c2c712
> From: Merger <merger@example.org>
> Date: Mon, 18 May 2026 09:16:35 +0200
> Subject: [Merge-Request] feature/abc
> Message:
> > Merge branch 'feature/abc' into trunk
> >
> > Adds two greeting lines to README.md.
> >
> > Merge-Request: feature/abc

## Diff from parent 1 @ git show -m -1 51c2c712

### File "README.md" modified @ git diff d784110:README.md..51c2c712:README.md
> @@ -1 +1,3 @@
> 1 1: # Demo project
> 2: +Hello from feature.
> 3: +Hello again.

## Diff from parent 2 @ git show -m -2 51c2c712

(empty — the merge added nothing relative to the second parent)
```

The empty-diff-from-parent-N subsection still appears as a reviewable section — its emptiness is a structural fact about the merge and reviewers can comment on it ("good, no surprising merger additions"). For conflict-resolved merges both (or all) parent-diff subsections carry content; the merge-only changes show up in the parent subsections that have non-empty diffs.

Per-file subsections under a parent-diff use H3 (`### File …`) since H2 is already taken by the parent-diff itself. Body shapes follow the same lifecycle family as in `# Commit`.

Merge-commits are conventionally the integration anchor for an MR-style workflow (subject prefixed `[Merge-Request]`, optional `Merge-Request:` trailer). The review of the merge commit is the review of the MR; per-feature-commit reviews live in their own `# Commit` notes and dedup naturally.

## Reviewer events

Every reviewer action is a markdown-ish list item. Two different bullets so
`grep` can pick one lane without the other:

| Bullet | Shape | Used for |
|---|---|---|
| `*` | `* <Keyword>-by: Name <email>[ @<RFC3339>][; <args>]` | Range markers (no body) — `Read-by:` / `Skipped-by:`. |
| `-` | `- <Keyword>-by: Name <email>[ @<RFC3339>][; <args>]` | Everything else: `Commented-by:`, `Question-asked-by:`, `Answer-given-by:`, `Reacted-by:`, `Flagged-by:`, `Verdict-reached-by:`, `Issued-by:`, `Remarked-by:`, `Resolved-by:`. Optional body indented two spaces below. |

The body, when present, is **indented two spaces** so it nests under
the list item. That indentation is what lets a comment contain its own
markdown headings, lists, even nested blockquotes (`>`), without
colliding with the section structure or with the patch-quote `> ` lines.

All keyword names are **kebab-cased past-tense verbs** ending in `-by:` (`Read-by:`, `Commented-by:`, `Verdict-reached-by:`, …). They mirror git's trailer convention (`Reviewed-By:`, `Signed-off-by:`).

Full event shape: `<Keyword>-by: Name <email@example.org>[ @<RFC3339>][; <args>]`. The optional ` @<RFC3339>` slot carries an event timestamp when the writer is opted in; the optional `; <args>` slot carries kind-specific parameters (the emoji for `Reacted-by:`, the state for `Verdict-reached-by:`, `begin` / `end` for `Read-by:` and `Skipped-by:`).

### Range markers (read / skip)

```
* Read-by: Markus <markus@example.org>; begin
* Read-by: Markus <markus@example.org>; end
* Skipped-by: Markus <markus@example.org>; begin
* Skipped-by: Markus <markus@example.org>; end
```

**Read/Skip markers cover only the `> ` quoted content** — the
file content / diff / commit body the reviewer is actually reading.
Reviewer events (comments, questions, reactions, answers) are *not*
"read" or "skipped"; they're the reviewer's own writing, not the
artefact under review. A `Read-by: …; begin` / `Read-by: …; end` pair brackets a range of `> ` lines; reviewer events that happen to sit inside that range are along for the ride but neither extend nor close it.

Pairing is by alternation: walking the events of one (reviewer, section) in file order, every `; begin` opens a range and the next `; end` from the same reviewer closes it. Multiple disjoint pairs are fine — you might read the top of a file, scroll past a chunk you don't care about, then read the bottom; that's two `Read-by:` pairs.

**Redundancy rule** depends on whether timestamps are on.

*Without timestamps:* two of the same kind in a row from the same reviewer without the opposite between them carry no new information. `; begin` then another `; begin` (no `; end` between) is a writer bug — the first begin is still open, the second says nothing past it. Same for two `; end` in a row. Strict alternation: `begin, end, begin, end, …`.

*With timestamps:* two of the same kind from the same reviewer at different timestamps are fine — each carries new information (the moving end-of-read position over time). Re-marking `; end` later in the file at a later timestamp records "I read further". Still not allowed: two of the same kind at the same anchor with the same timestamp from the same reviewer — no transition, no new info, just noise.

When a section is fully read, the minimal form is just `* Read-by: …; begin` at its first quoted line and `* Read-by: …; end` at its last. As the reviewer reads more (or splits reading across sessions), the writer either moves the existing `; end` forward (no-timestamps mode) or appends a fresh `; end` at the new position (with-timestamps mode).

Same rules apply to `Skipped-by: …; begin` / `Skipped-by: …; end`.

**Timestamps are optional**, off by default. With timestamps enabled, the ` @<RFC3339>` slot comes between the email and the `;`: `* Read-by: Markus <markus@example.org> @2026-05-17T19:00:00Z; end`.

### Comments

```
- Commented-by: Markus <markus@example.org>
  First paragraph of the comment. The first line is the comment's
  one-line summary — readers often show it inline next to the
  anchored line.
  
  A blank line (two spaces, then nothing) starts a new paragraph. The
  whole body is indented two spaces so any markdown the reviewer
  writes — including nested lists, code blocks, even
  
  > blockquotes
  
  — round-trips with no escaping.
```

The encoded form of the blank-line separator is `  \n  \n` (two trailing
spaces on the blank line plus the indentation of the next line) so the
indentation level stays consistent.

### Questions

Same shape as comments except the bullet says `Question-asked-by:`. A question event is "I'd like an answer" — distinct from a comment which is "here's what I think".

```
- Question-asked-by: Markus <markus@example.org>
  Why "revised"? Was there an earlier version that got squashed?
```

### Answers

Every `Question-asked-by:` deserves an answer. An `Answer-given-by:` is a **nested list item inside the question's body**, two extra spaces of indent (so four total). The blank line between question body and the nested `- Answer-given-by:` matters — without it the answer would parse as another inline list inside the question's prose rather than a child event:

```
- Question-asked-by: Markus <markus@example.org>
  Why "revised"? Was there an earlier version that got squashed?

  - Answer-given-by: Author <author@example.org>
    Yes — the first version landed `b.txt` only; the squash adds
    `b.test` in response to the question on the first round.
```

Anchoring: the Answer attaches to its parent Question (which in turn
is anchored to a line or section). Multiple Answers under one
Question are fine — they're just consecutive nested `- Answer-given-by:`
items.

Structurally, `Answer-given-by:` is a normal `-` event — same `Name <email>` attribution, same indented-body shape, same optional ` @<RFC3339>` timestamp — it just lives one indent level deeper than the `Question-asked-by:` it answers.

**A Question is *open* if it has no `- Answer-given-by:` under it.** Open questions are what the `ClarificationRequired` verdict state refers to. Adding any `- Answer-given-by:` (from any reviewer, not necessarily the one who'd block) closes the question. Re-opening means deleting the existing answer(s) and asking again — there is no explicit "unanswer" event.

### Reactions

```
- Reacted-by: Markus <markus@example.org>; 👍
- Reacted-by: Alice <alice@example.com>; 👎
- Reacted-by: Alice <alice@example.com>; 🎉
```

One emoji per reaction event. No body.

Multiplicity rule: **at most one of each emoji per (author,
anchor)**. The same author can stack different emojis at one anchor
(`👍` and `🎉`), and re-submitting the same emoji replaces in place
rather than appending a duplicate.

Reactions can also be **nested under a Commented-by, Question-asked-by, or Answer-given-by** — same `- Reacted-by: …; <emoji>` shape, indented two extra spaces so it sits as a child of the parent event:

```
- Commented-by: Alice <alice@example.com>
  Clean refactor.

  - Reacted-by: Markus <markus@example.org>; 👍
  - Reacted-by: Bob <bob@example.com>; 🎉
```

This lets reviewers acknowledge each other's input without writing
prose for it. The "once per emoji per author" rule applies at the
nested level too: Alice can stick 👍 and 🎉 on Bob's comment but
only one 👍.

### Flags

```
- Flagged-by: ScanBot <bot@example.org>; permissions
  File is world-writable (mode 0666); usually a packaging mistake.

- Flagged-by: ScanBot <bot@example.org>; long-line
  Line 142 is 14000 characters wide — likely minified or generated.

- Flagged-by: UnicodeScanner <ucbot@example.org>; suspicious-unicode
  Mixed bidirectional override characters detected (U+202E U+202D); possible homograph or Trojan-Source attack.
```

Automated annotations from bots and agents — file-permission anomalies, overlong lines, suspicious unicode, anything a scanner wants to surface to the reviewer. The `; <category>` slot carries a short kebab-cased label so readers can filter or summarise; the body explains the finding.

Bots use the same `Name <email>` attribution shape as humans, so flags interleave with human events naturally.

The format defines only the event shape; **what to flag, when to scan, and how to render the flags is out of scope for this spec** and lives with the scanner and the reading tool. New categories are added by picking a new `; <category>` string — readers preserve unknown categories verbatim per the unknown-line rule.

### Verdict-reached-by

Defined under `# Review` § *Verdict-reached-by lines*. Only valid there.

## Anchoring

Position decides anchor.

**Line anchor.** An event placed after one or more `> ` patch lines anchors to the immediately preceding `> ` line. Moving the event in the file moves the anchor by definition.

**Section anchor.** An event placed at the top of a section or subsection — before the first `> ` line — anchors to the whole section. Section anchoring works for every container shape: `# Review`, `# Blob`, `# Tree`, `# Commit`, `# Merge-Commit`, `## Note`, `## Remark`, `## Issue <title>`, the `## File …` lifecycle variants in `# Commit` and `# Merge-Commit`, the embedded `## Blob "<path>" review` subsections, and the per-parent `## Diff from parent <N>` subsections in `# Merge-Commit`. Use it for "what I think about this file/blob/commit/issue/note overall" rather than a specific line.

```
## File "greet.go" modified @ git diff a1b2c3d..e4f5a6b

- Reacted-by: Alice <alice@example.com>; 👍
- Commented-by: Alice <alice@example.com>
  Clean refactor — nothing line-specific to flag.

> @@ -3,4 +3,7 @@
> 3 3: func Hello(name string) string {
…
```

Multiple events at the same anchor are supported by listing them in sequence — the parser preserves order, so a thread of replies on one line is just consecutive `- Commented-by:` items, and a stack of file-level reactions is the same shape at the top of the section. Same-anchor ordering across reviewers follows the rule in *Multi-reviewer merge* — timestamps then reviewer email — so the merged result is stable regardless of which reviewer's ref was processed first.

## Section / heading boundary rules

H1 (`# `) closes any open section. H2 (`## `) closes any open H2 inside
the current H1. List items (`- ` / `* `) close any previously open list
item but stay inside the current H1/H2.

**Structural headings live only at column 0.** All user content
(comment bodies, issue descriptions, remark prose, answers) is
indented, so a user-typed `# Foo` lands as `  # Foo` on disk and
the parser doesn't see it as a section boundary (it matches `^# `
/ `^## ` only). Users can write any markdown headings in their
prose; no shift, no escape, no special casing.

The writer never emits a non-indented `# ` or `## ` inside a
user-content body.

## Storage

Default storage is a single git notes ref, `refs/notes/reviews`, with each note keyed by **any reviewed git object SHA** — commit, tree, or blob. The note body is a `.review` scoped to that object: `git notes --ref=reviews show <any-sha>` is the universal lookup, regardless of whether `<any-sha>` names a commit, a tree, or a blob. The same shape works at every layer: a per-blob review dedups across every commit that touches that blob content; a per-commit review dedups across every branch that contains the commit; a per-merge-commit review captures only what's new at the merge layer.

## Multi-reviewer merge

The format is **mergeable across reviewers without conflict resolution**, because two properties hold:

**The skeleton of every per-object review is deterministic from the object SHA.** Section headings, `@ <git command>` recipes, and the `> `-quoted bodies are all reproducible from `<sha>` alone — running the recipes gives byte-identical output. Two reviewers independently starting a review of the same object produce byte-identical skeletons.

**Reviewer events are append-only list items at fixed anchors.** A reviewer adds events; nothing mutates another reviewer's events. Merging two reviews of the same object is line-union over the deterministic skeleton.

Together these properties match what git's built-in **`git notes merge --strategy=cat_sort_uniq`** strategy is designed for: sort the lines of both note bodies, dedup, write the union back. The strategy was built for line-oriented append-only content; the `.review` format fits exactly.

Conventional layout for concurrent multi-reviewer work: each reviewer writes to their own ref (`refs/notes/reviews-<name>`) and a downstream consolidator runs `git notes merge --strategy=cat_sort_uniq refs/notes/reviews-<name>` per reviewer into the shared `refs/notes/reviews`. Per-reviewer refs avoid write races; the shared ref is the read surface.

**Event ordering at the same anchor.** When two events anchor to the same line, they sort by `@<RFC3339>` timestamp (if both have one) with reviewer email as the stable tiebreaker. Events without timestamps sort after timestamped events at the same anchor, then by reviewer email. This ordering rule is what makes the cat_sort_uniq merge produce a stable result regardless of which reviewer's ref the consolidator processes first.

What stays non-deterministic and may need merge attention:

- **Reviewer-added subsections** — extra `## Note` / `## Remark` / `## Issue` items under `# Review`. Merge = union by heading; duplicates collapse.
- **Issue collisions** — two reviewers raising `## Issue X` with the same title. Kept as duplicates (the TUI surfaces them — see *gitflower-review.md*) unless a tool merges titles by similarity.
- **Verdict-reached-by per (Name, email)** — "latest replaces" is the collision rule; cat_sort_uniq's dedup handles re-submissions naturally when timestamps are present, otherwise the consolidator picks the latest-emailed one.

# Considerations

Rationale, rejected paths, and open questions. Deletable as a whole once the spec settles.

## No `Reviewed-by`

**No kernel-style `Reviewed-by:` trailer.** Kernel `Reviewed-by:` means "I read this patch and sign off"; `Verdict-reached-by: …; Approved` is a state in a review session's verdict machine. Different workflow, different semantics — keep them separate. Tools that need a kernel-style sign-off can recognise `Verdict-reached-by: …; Approved` directly.

## Attaching reviews to history

In the per-object model the question mostly dissolves: a review is *already* attached to its object by the notes-ref keying. A commit's review travels with the commit; a merge-commit's review travels with the merge. Trunk fast-forwarding to an MR's merge commit picks up the merge commit's review at the same time. No separate "review-landed" merge is needed — the merge commit IS its own review attachment.

What remains conventional rather than format-specified: the **MR marker** in the merge commit's message (`[Merge-Request]` subject prefix or `Merge-Request:` trailer) so tools recognise integration commits awaiting review. The marker is workflow, not format — but the format-side guarantee is that the merge commit's `.review` note is found at the merge commit's SHA, full stop.

## On-tree `.review` file

A reviewer may want to commit a `.review` into a tree alongside the code — for archival, for tooling that doesn't speak git notes, or to ship a review as part of a release. Path convention: `reviews/<object-kind>-<short-sha>.review`, e.g. `reviews/commit-eb2d95b.review` or `reviews/blob-1a2b3c4.review`.

Open: whether tree inclusion is purely a per-reviewer convention, a workflow gate (e.g., "open issues must materialise before merge"), or carries any spec-level shape requirements.

## Per-reviewer notes refs

The *Multi-reviewer merge* section sketches `refs/notes/reviews-<name>` per reviewer with cat_sort_uniq consolidation into the shared `refs/notes/reviews`. Open questions: who runs the consolidator (each reviewer, a CI bot, a server hook?), what `<name>` should be (git config user.email? a chosen handle?), and whether reviewers should write directly to the shared ref when they're not concerned about conflicts.

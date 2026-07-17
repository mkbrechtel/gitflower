"""The .review format: parse/render round-trips and event semantics."""

import pytest

from gitflower.review import format as fmt

FULL = """\
dot-review-File-Version: 0
dot-review-Intro: patch-quoting markdown-ish format
dot-review-Docs-Link: https://example.org/spec
---
# Review
- Review-Head-Commit: 2d2442633399f38197249ae9f30b001e0943564a
- Review-Branch: work/feature/x
- Created-By: Mirian <mirian@example.org>
- Verdict-reached-by: Markus <markus@example.org>; RequestedChanges
  Needs a test before merge.

## Issue name uses snake_case but project uses camelCase
 Several added identifiers break the existing convention.

 Second paragraph of the description.
- Issued-by: Markus <markus@example.org>

- Commented-by: Alice <alice@example.com>
  Pushed the rename in commit abc1234.

- Resolved-by: Markus <markus@example.org>

## Note @ git notes --ref=refs/notes/go-lint show 2d2442633399
> 1: greet.go:14:2: warning: shadow declaration of 'err'
> 2: greet.go:27:5: warning: unused variable 'tmp'
- Commented-by: Markus <markus@example.org>
  Intentional, suppressed in lintignore.
# Diff 85d40ed9ce90..bd5b98df70c9 @ git diff 85d40ed9ce90..bd5b98df70c9

## File "a.txt" modified @ git diff 85c30401ce28..3cc64f73e4bc
- Reacted-by: Alice <alice@example.com>; 👍
> @@ -1,3 +1,4 @@
> 1 1: alpha
* Read-by: Markus <markus@example.org>; begin
> 2: -beta
> 2: +BETA
- Question-asked-by: Markus <markus@example.org>
  Why uppercase?
  
  - Answer-given-by: Alice <alice@example.com>
    The new spelling is intentional.
    
    - Reacted-by: Markus <markus@example.org>; 🎉
> 3 3: gamma
* Read-by: Markus <markus@example.org>; end
some unknown line the parser must keep
"""


def test_full_round_trip():
    review = fmt.parse(FULL)
    assert fmt.render(review) == FULL


def test_probe():
    assert fmt.is_dot_review(FULL)
    assert not fmt.is_dot_review("# Review\n")


def test_parse_rejects_non_review():
    with pytest.raises(fmt.FormatError):
        fmt.parse("# Review\n")
    with pytest.raises(fmt.FormatError):
        fmt.parse("dot-review-File-Version: 0\nno terminator\n")


def test_structure():
    review = fmt.parse(FULL)
    assert review.meta("Review-Branch") == "work/feature/x"
    titles = [section.title for section in review.sections]
    assert titles == ["Review", "Diff 85d40ed9ce90..bd5b98df70c9"]
    subsections = review.review_section.sections()
    assert [s.title for s in subsections] == [
        "Issue name uses snake_case but project uses camelCase",
        "Note",
    ]
    file_section = review.sections[1].sections()[0]
    assert file_section.recipe == "git diff 85c30401ce28..3cc64f73e4bc"


def test_nested_events():
    review = fmt.parse(FULL)
    file_section = review.sections[1].sections()[0]
    question = [e for e in file_section.events() if e.keyword == "Question-asked"][0]
    assert question.body == ["Why uppercase?"]
    answer = question.children[0]
    assert answer.keyword == "Answer-given"
    assert answer.children[0].args == "🎉"


def test_stripped_blank_keeps_answer_nested():
    """Editors strip trailing whitespace; the answer must stay a child."""
    text = FULL.replace("  \n  - Answer-given-by:", "\n  - Answer-given-by:")
    review = fmt.parse(text)
    file_section = review.sections[1].sections()[0]
    question = [e for e in file_section.events() if e.keyword == "Question-asked"][0]
    assert question.children[0].keyword == "Answer-given"


def test_verdict_replaces_in_place():
    review = fmt.parse(FULL)
    assert fmt.verdict_of(review, "markus@example.org") == "RequestedChanges"
    fmt.set_verdict(review, "Markus", "markus@example.org", "Approved")
    assert fmt.verdict_of(review, "markus@example.org") == "Approved"
    verdicts = [
        e for e in review.review_section.events() if e.keyword == "Verdict-reached"
    ]
    assert len(verdicts) == 1


def test_reaction_multiplicity():
    review = fmt.parse(FULL)
    file_section = review.sections[1].sections()[0]
    heading_anchor = -1  # section anchor: before the first quote
    fmt.add_reaction(file_section.items, heading_anchor, "Alice", "alice@example.com", "👍")
    likes = [
        e for e in file_section.events()
        if e.keyword == "Reacted" and e.email == "alice@example.com" and e.args == "👍"
    ]
    assert len(likes) == 1  # re-submitting the same emoji replaces in place
    fmt.add_reaction(file_section.items, heading_anchor, "Alice", "alice@example.com", "🎉")
    reactions = [e for e in file_section.events() if e.email == "alice@example.com"]
    assert len(reactions) == 2  # different emoji stacks


def test_unknown_event_keyword_preserved():
    text = FULL.replace("Commented-by: Alice", "Frobnicated-by: Alice")
    review = fmt.parse(text)
    assert fmt.render(review) == text


def test_range_markers_use_star_bullet():
    review = fmt.parse(FULL)
    markers = [e for e in review.all_events() if e.keyword == "Read"]
    assert [m.args for m in markers] == ["begin", "end"]
    assert all(m.head_line().lstrip().startswith("* ") for m in markers)


def test_timestamp_slot():
    line = "- Commented-by: M <m@e.org> @2026-05-17T19:00:00Z; x\n"
    text = FULL.replace("some unknown line the parser must keep\n", line)
    review = fmt.parse(text)
    event = [e for e in review.all_events() if e.timestamp][0]
    assert event.timestamp == "2026-05-17T19:00:00Z"
    assert event.args == "x"
    assert fmt.render(review) == text

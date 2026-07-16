"""Go path/filepath.Match test vectors, ported.

The table mirrors Go's filepath/match_test.go so the matcher provably keeps
Go semantics — most importantly that `*` never crosses `/`.
"""

import pytest

from gitflower.matcher import BadPattern, match

GO_MATCH_TESTS = [
    # (pattern, name, expected)
    ("abc", "abc", True),
    ("*", "abc", True),
    ("*c", "abc", True),
    ("a*", "a", True),
    ("a*", "abc", True),
    ("a*", "ab/c", False),
    ("a*/b", "abc/b", True),
    ("a*/b", "a/c/b", False),
    ("a*b*c*d*e*/f", "axbxcxdxe/f", True),
    ("a*b*c*d*e*/f", "axbxcxdxexxx/f", True),
    ("a*b*c*d*e*/f", "axbxcxdxe/xxx/f", False),
    ("a*b*c*d*e*/f", "axbxcxdxexxx/fff", False),
    ("a*b?c*x", "abxbbxdbxebxczzx", True),
    ("a*b?c*x", "abxbbxdbxebxczzy", False),
    ("ab[c]", "abc", True),
    ("ab[b-d]", "abc", True),
    ("ab[e-g]", "abc", False),
    ("ab[^c]", "abc", False),
    ("ab[^b-d]", "abc", False),
    ("ab[^e-g]", "abc", True),
    ("a\\*b", "a*b", True),
    ("a\\*b", "ab", False),
    ("a?b", "a☺b", True),
    ("a[^a]b", "a☺b", True),
    ("a???b", "a☺b", False),
    ("a[^a][^a][^a]b", "a☺b", False),
    ("[a-ζ]*", "α", True),
    ("*[a-ζ]", "A", False),
    ("a?b", "a/b", False),
    ("a*b", "a/b", False),
    ("[\\]a]", "]", True),
    ("[\\-]", "-", True),
    ("[x\\-]", "x", True),
    ("[x\\-]", "-", True),
    ("[x\\-]", "z", False),
    ("[\\-x]", "x", True),
    ("[\\-x]", "-", True),
    ("[\\-x]", "a", False),
    ("*x", "xxx", True),
    ("", "", True),
    ("", "a", False),
]

GO_BAD_PATTERNS = [
    ("[]a]", "]"),
    ("[-]", "-"),
    ("[x-]", "x"),
    ("[x-]", "-"),
    ("[x-]", "z"),
    ("[-x]", "x"),
    ("[-x]", "-"),
    ("[-x]", "a"),
    ("\\", "a"),
    ("[a-b-c]", "a"),
    ("[", "a"),
    ("[^", "a"),
    ("[^bc", "a"),
    ("a[", "a"),
    ("a[", "ab"),
    ("a[", "x"),
    ("a/b[", "x"),
]


@pytest.mark.parametrize("pattern,name,expected", GO_MATCH_TESTS)
def test_match(pattern, name, expected):
    assert match(pattern, name) is expected


@pytest.mark.parametrize("pattern,name", GO_BAD_PATTERNS)
def test_bad_pattern(pattern, name):
    with pytest.raises(BadPattern):
        match(pattern, name)


def test_branch_router_patterns():
    """The patterns gitflower's default config relies on."""
    assert match("main", "main")
    assert not match("main", "maintenance")
    assert match("issues/*", "issues/42")
    assert not match("issues/*", "issues/42/subtask")
    assert not match("issues/*", "issues")
    assert match("releases/v*", "releases/v1.0.0")
    assert not match("releases/v*", "releases/1.0.0")
    assert match("work/*/*", "work/feature/python-rewrite")

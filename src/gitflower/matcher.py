"""Branch-pattern matching with Go `path/filepath.Match` semantics.

The branch router's patterns come from the Go original, where `*` matches any
sequence of characters EXCEPT `/` — so `issues/*` matches `issues/foo` but not
`issues/foo/bar`. Python's fnmatch lets `*` cross `/`, which would silently
widen every rule; this is a faithful port of the Go matcher instead.

Grammar:
    pattern: { term }
    term:    '*'          matches any sequence of non-/ characters
             '?'          matches any single non-/ character
             '[' [ '^' ] { character-range } ']'   character class
             c            matches character c (c != '*', '?', '\\\\', '[')
             '\\\\' c       matches character c

A malformed pattern raises BadPattern. The router treats that as a rejection
(fail closed), never as a silent non-match.
"""

SEPARATOR = "/"


class BadPattern(ValueError):
    """The pattern is syntactically malformed (Go's ErrBadPattern)."""


def match(pattern: str, name: str) -> bool:
    """True if `name` matches `pattern` in full (not a prefix)."""
    while pattern:
        star, chunk, pattern = _scan_chunk(pattern)
        if star and chunk == "":
            # Trailing * matches the rest unless it contains a separator.
            return SEPARATOR not in name

        # Look for a match at the current position.
        rest, ok = _match_chunk(chunk, name)
        if ok and (rest == "" or pattern):
            name = rest
            continue

        if star:
            # Look for a match skipping i+1 characters; cannot skip /.
            i = 0
            while i < len(name) and name[i] != SEPARATOR:
                rest, ok = _match_chunk(chunk, name[i + 1 :])
                if ok:
                    # If this is the last chunk it must exhaust the name.
                    if pattern == "" and rest != "":
                        i += 1
                        continue
                    name = rest
                    break
                i += 1
            else:
                # Validate the remainder of the pattern before failing.
                _validate_rest(pattern)
                return False
            continue

        _validate_rest(pattern)
        return False
    return name == ""


def _validate_rest(pattern: str) -> None:
    while pattern:
        _, chunk, pattern = _scan_chunk(pattern)
        _match_chunk(chunk, "")


def _scan_chunk(pattern: str) -> tuple[bool, str, str]:
    """Strip leading stars, then scan up to (not including) the next star.
    Returns (saw_star, chunk, rest)."""
    star = False
    while pattern.startswith("*"):
        pattern = pattern[1:]
        star = True
    in_range = False
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\":
            # Skip the escaped character (may be absent — caught later).
            if i + 1 < len(pattern):
                i += 1
        elif c == "[":
            in_range = True
        elif c == "]":
            in_range = False
        elif c == "*" and not in_range:
            break
        i += 1
    return star, pattern[:i], pattern[i:]


def _match_chunk(chunk: str, s: str) -> tuple[str, bool]:
    """Match chunk against the beginning of s. Returns (rest-of-s, matched).

    Like the Go original, the whole chunk is syntax-checked even after the
    match has already failed, so malformed patterns raise regardless of input.
    """
    failed = False
    while chunk:
        if not failed and s == "":
            failed = True
        c = chunk[0]
        if c == "[":
            r = ""
            if not failed:
                r, s = s[0], s[1:]
            chunk = chunk[1:]
            negated = chunk.startswith("^")
            if negated:
                chunk = chunk[1:]
            matched = False
            nrange = 0
            while True:
                if chunk.startswith("]") and nrange > 0:
                    chunk = chunk[1:]
                    break
                lo, chunk = _get_esc(chunk)
                hi = lo
                if chunk.startswith("-"):
                    hi, chunk = _get_esc(chunk[1:])
                if lo <= r <= hi and r != "":
                    matched = True
                nrange += 1
            if matched == negated:
                failed = True
        elif c == "?":
            if not failed:
                if s[0] == SEPARATOR:
                    failed = True
                else:
                    s = s[1:]
            chunk = chunk[1:]
        elif c == "\\":
            chunk = chunk[1:]
            if chunk == "":
                raise BadPattern("pattern ends with an unescaped backslash")
            if not failed:
                if chunk[0] != s[0]:
                    failed = True
                else:
                    s = s[1:]
            chunk = chunk[1:]
        else:
            if not failed:
                if c != s[0]:
                    failed = True
                else:
                    s = s[1:]
            chunk = chunk[1:]
    if failed:
        return "", False
    return s, True


def _get_esc(chunk: str) -> tuple[str, str]:
    """One character (possibly escaped) out of a character class."""
    if chunk == "" or chunk[0] in ("-", "]"):
        raise BadPattern(f"malformed character class near {chunk!r}")
    if chunk[0] == "\\":
        chunk = chunk[1:]
        if chunk == "":
            raise BadPattern("pattern ends with an unescaped backslash")
    r, chunk = chunk[0], chunk[1:]
    if chunk == "":
        raise BadPattern("unterminated character class")
    return r, chunk

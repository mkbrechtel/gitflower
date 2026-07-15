"""Repository and organization-folder naming rules.

Ported from the Go original's git/validation.go, error strings preserved
verbatim (the e2e tests pin them). One deliberate fix over the Go code:
`validate_repo_path` rejects empty, '.' and '..' components instead of
skipping them, so a hostile path can never validate.
"""

import re

SLUG_RE = re.compile(r"^[a-z0-9-.]+$")


class SlugError(ValueError):
    pass


def validate_slug(name: str) -> None:
    """A single path component: lowercase slug, no dot tricks."""
    if name in (".", ".."):
        raise SlugError(f"invalid name '{name}': cannot use special directory names")
    if name.startswith("."):
        raise SlugError(f"invalid name '{name}': cannot start with a dot")
    if ".." in name:
        raise SlugError(f"invalid name '{name}': cannot contain '..'")
    if not SLUG_RE.match(name):
        raise SlugError(
            f"invalid name '{name}': must contain only lowercase letters, numbers, hyphens, and dots"
        )


def validate_repo_name(name: str) -> None:
    validate_slug(name)
    if not name.endswith(".git"):
        raise SlugError(f"repository name '{name}' must end with .git")


def validate_org_folder(name: str) -> None:
    validate_slug(name)
    if name.endswith(".git"):
        raise SlugError(f"organization folder '{name}' must not end with .git")


def validate_repo_path(path: str) -> str:
    """A relative repo path like 'org/team/app.git'. Returns it normalized."""
    if path.startswith("/"):
        raise SlugError(f"invalid path '{path}': must be relative")
    parts = path.strip("/").split("/")
    if not parts or parts == [""]:
        raise SlugError("invalid path: empty")
    for part in parts[:-1]:
        if part == "":
            raise SlugError(f"invalid path '{path}': empty component")
        validate_org_folder(part)
    if parts[-1] == "":
        raise SlugError(f"invalid path '{path}': empty component")
    validate_repo_name(parts[-1])
    return "/".join(parts)


def is_repository(name: str) -> bool:
    return name.endswith(".git")

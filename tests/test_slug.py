"""Naming rules — error strings pinned to the Go originals verbatim."""

import pytest

from gitflower.slug import (
    SlugError,
    is_repository,
    validate_org_folder,
    validate_repo_name,
    validate_repo_path,
    validate_slug,
)


@pytest.mark.parametrize("name", ["repo", "my-repo", "repo2", "a", "my.repo", "0start"])
def test_valid_slugs(name):
    validate_slug(name)


@pytest.mark.parametrize(
    "name,message",
    [
        (".", "cannot use special directory names"),
        ("..", "cannot use special directory names"),
        (".hidden", "cannot start with a dot"),
        ("a..b", "cannot contain '..'"),
        ("UPPER", "must contain only lowercase letters, numbers, hyphens, and dots"),
        ("under_score", "must contain only lowercase letters, numbers, hyphens, and dots"),
        ("with space", "must contain only lowercase letters, numbers, hyphens, and dots"),
        ("", "must contain only lowercase letters, numbers, hyphens, and dots"),
    ],
)
def test_invalid_slugs(name, message):
    with pytest.raises(SlugError, match=message):
        validate_slug(name)


def test_repo_name_needs_git_suffix():
    validate_repo_name("project.git")
    with pytest.raises(SlugError, match=r"repository name 'project' must end with .git"):
        validate_repo_name("project")


def test_org_folder_must_not_end_git():
    validate_org_folder("myorg")
    with pytest.raises(SlugError, match=r"organization folder 'x.git' must not end with .git"):
        validate_org_folder("x.git")


@pytest.mark.parametrize(
    "path,normalized",
    [
        ("project.git", "project.git"),
        ("org/project.git", "org/project.git"),
        ("org/team/app.git", "org/team/app.git"),
    ],
)
def test_valid_repo_paths(path, normalized):
    assert validate_repo_path(path) == normalized


@pytest.mark.parametrize(
    "path",
    [
        "/abs/project.git",
        "../escape.git",
        "org/../escape.git",
        "test..repo.git",
        "UPPERCASE.git",
        "test_underscore.git",
        "test project.git",
        "org.git/project.git",  # org folder may not end .git
        "org//project.git",
        "",
    ],
)
def test_invalid_repo_paths(path):
    with pytest.raises(SlugError):
        validate_repo_path(path)


def test_is_repository():
    assert is_repository("x.git")
    assert not is_repository("x")

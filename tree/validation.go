package tree

import (
	"fmt"
	"path/filepath"
	"regexp"
	"strings"
)

var (
	slugRegex = regexp.MustCompile(`^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$`)
	repoRegex = regexp.MustCompile(`^[a-z0-9][a-z0-9-]*\.git$`)
)

func ValidateSlug(name string) error {
	if name == "" {
		return fmt.Errorf("name cannot be empty")
	}

	if len(name) > 100 {
		return fmt.Errorf("name too long (max 100 characters)")
	}

	if !slugRegex.MatchString(name) && !repoRegex.MatchString(name) {
		return fmt.Errorf("invalid name: must contain only lowercase letters, numbers, and hyphens (cannot start/end with hyphen)")
	}

	return nil
}

func IsRepository(name string) bool {
	return strings.HasSuffix(name, ".git")
}

func ValidateOrgFolder(name string) error {
	if strings.HasSuffix(name, ".git") {
		return nil
	}

	if err := ValidateSlug(name); err != nil {
		return fmt.Errorf("organization folder: %w", err)
	}

	return nil
}

func ValidatePath(path string) error {
	if path == "" {
		return fmt.Errorf("path cannot be empty")
	}

	if filepath.IsAbs(path) {
		return fmt.Errorf("path must be relative")
	}

	if strings.Contains(path, "..") {
		return fmt.Errorf("path cannot contain '..'")
	}

	parts := strings.Split(path, string(filepath.Separator))

	for i, part := range parts {
		if part == "" {
			continue
		}

		isLast := i == len(parts)-1

		if isLast && strings.HasSuffix(part, ".git") {
			if err := ValidateSlug(strings.TrimSuffix(part, ".git")); err != nil {
				return fmt.Errorf("repository name: %w", err)
			}
		} else {
			if err := ValidateSlug(part); err != nil {
				return fmt.Errorf("path component '%s': %w", part, err)
			}
		}
	}

	return nil
}

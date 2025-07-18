package git

import (
	"fmt"
	"path/filepath"
	"regexp"
	"strings"
)

var (
	slugRegex = regexp.MustCompile(`^[a-z0-9-.]+$`)
)

// ValidateSlug checks if a name follows the slug format [a-z0-9-.]
func ValidateSlug(name string) error {
	// Reject special directory names
	if name == "." || name == ".." {
		return fmt.Errorf("invalid name '%s': cannot use special directory names", name)
	}
	
	// Reject names starting with dot
	if strings.HasPrefix(name, ".") {
		return fmt.Errorf("invalid name '%s': cannot start with a dot", name)
	}
	
	// Reject names containing double dots
	if strings.Contains(name, "..") {
		return fmt.Errorf("invalid name '%s': cannot contain '..'", name)
	}
	
	if !slugRegex.MatchString(name) {
		return fmt.Errorf("invalid name '%s': must contain only lowercase letters, numbers, hyphens, and dots", name)
	}
	
	return nil
}

// ValidateRepoName checks if a repository name is valid (slug format and ends with .git)
func ValidateRepoName(name string) error {
	if err := ValidateSlug(name); err != nil {
		return err
	}
	if !strings.HasSuffix(name, ".git") {
		return fmt.Errorf("repository name '%s' must end with .git", name)
	}
	return nil
}

// ValidateOrgFolder checks if an organization folder name is valid (slug format and doesn't end with .git)
func ValidateOrgFolder(name string) error {
	if err := ValidateSlug(name); err != nil {
		return err
	}
	if strings.HasSuffix(name, ".git") {
		return fmt.Errorf("organization folder '%s' must not end with .git", name)
	}
	return nil
}

// ValidatePath validates a full repository path
func ValidatePath(path string) error {
	parts := strings.Split(filepath.Clean(path), string(filepath.Separator))
	
	for i, part := range parts {
		if part == "" || part == "." || part == ".." {
			continue
		}
		
		// Last part should be a repo name
		if i == len(parts)-1 {
			if err := ValidateRepoName(part); err != nil {
				return err
			}
		} else {
			// Other parts should be org folders
			if err := ValidateOrgFolder(part); err != nil {
				return err
			}
		}
	}
	
	return nil
}

// IsRepository checks if a directory name indicates it's a repository
func IsRepository(name string) bool {
	return strings.HasSuffix(name, ".git")
}
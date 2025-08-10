package git

import (
	"os"
	"path/filepath"
	"time"

	gogit "github.com/go-git/go-git/v5"
	"github.com/go-git/go-git/v5/plumbing"
	"github.com/go-git/go-git/v5/plumbing/storer"
)

// Repository represents a Git repository with metadata
type Repository struct {
	Path         string    `json:"path"`
	Name         string    `json:"name"`
	RelativePath string    `json:"relativePath"`
	Size         int64     `json:"size"`
	LastUpdate   time.Time `json:"lastUpdate"`
	BranchCount  int       `json:"branchCount"`
	MRCount      int       `json:"mrCount"`
	IsValid      bool      `json:"isValid"`
	Error        string    `json:"error,omitempty"`
}

// IsValidRepository checks if a path is a valid git repository
func IsValidRepository(path string) bool {
	// Check if it's a bare repository
	if _, err := os.Stat(filepath.Join(path, "HEAD")); err == nil {
		if _, err := os.Stat(filepath.Join(path, "objects")); err == nil {
			if _, err := os.Stat(filepath.Join(path, "refs")); err == nil {
				return true
			}
		}
	}

	// Check if it's a normal repository with .git directory
	if _, err := os.Stat(filepath.Join(path, ".git")); err == nil {
		return true
	}

	return false
}

// Open opens a git repository at the given path
func Open(path string) (*gogit.Repository, error) {
	return gogit.PlainOpen(path)
}

// Branches returns an iterator for all branches in the repository
func (r *Repository) Branches() (storer.ReferenceIter, error) {
	repo, err := Open(r.Path)
	if err != nil {
		return nil, err
	}
	return repo.Branches()
}

// Head returns the HEAD reference of the repository
func (r *Repository) Head() (*plumbing.Reference, error) {
	repo, err := Open(r.Path)
	if err != nil {
		return nil, err
	}
	return repo.Head()
}

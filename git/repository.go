package git

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/go-git/go-git/v6"
	"github.com/go-git/go-git/v6/plumbing"
	"github.com/go-git/go-git/v6/storage/filesystem"

	"gitflower/cfg"
)

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

type Scanner struct {
	reposDir string
	warnings []string
}

func NewScanner() *Scanner {
	return &Scanner{
		reposDir: cfg.ReposDirectory(),
		warnings: make([]string, 0),
	}
}

func (s *Scanner) Scan() ([]*Repository, []string, error) {
	repos := make([]*Repository, 0)
	s.warnings = make([]string, 0)

	absReposDir, err := filepath.Abs(s.reposDir)
	if err != nil {
		return nil, nil, fmt.Errorf("resolving repos directory: %w", err)
	}

	if _, err := os.Stat(absReposDir); err != nil {
		if os.IsNotExist(err) {
			return repos, s.warnings, nil // Empty directory, no repos
		}
		return nil, nil, fmt.Errorf("accessing repos directory: %w", err)
	}

	err = filepath.Walk(absReposDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			s.warnings = append(s.warnings, fmt.Sprintf("Error accessing %s: %v", path, err))
			return nil
		}

		if !info.IsDir() {
			return nil
		}

		relPath, err := filepath.Rel(absReposDir, path)
		if err != nil {
			return err
		}

		// Skip the root directory
		if relPath == "." {
			return nil
		}

		name := info.Name()

		// Validate directory name
		if err := ValidateSlug(name); err != nil {
			s.warnings = append(s.warnings, fmt.Sprintf("Invalid directory name: %s", path))
			return nil
		}

		// Check if it's a repository
		if IsRepository(name) {
			repo := s.scanRepository(path, relPath)
			repos = append(repos, repo)
			return filepath.SkipDir // Don't descend into .git directories
		}

		// It's an organization folder, validate it
		if err := ValidateOrgFolder(name); err != nil {
			s.warnings = append(s.warnings, fmt.Sprintf("Invalid organization folder: %s", path))
		}

		return nil
	})

	if err != nil {
		return nil, nil, fmt.Errorf("scanning repositories: %w", err)
	}

	return repos, s.warnings, nil
}

func (s *Scanner) scanRepository(absPath, relPath string) *Repository {
	repo := &Repository{
		Path:         absPath,
		Name:         filepath.Base(absPath),
		RelativePath: relPath,
		IsValid:      true,
	}

	// Open the repository
	gitRepo, err := git.PlainOpen(absPath)
	if err != nil {
		repo.IsValid = false
		repo.Error = fmt.Sprintf("not a valid git repository: %v", err)
		return repo
	}

	// Get repository size
	repo.Size = s.calculateRepoSize(absPath)

	// Get last update time
	if lastUpdate, err := s.getLastUpdateTime(gitRepo); err == nil {
		repo.LastUpdate = lastUpdate
	}

	// Count branches
	if branchCount, err := s.countBranches(gitRepo); err == nil {
		repo.BranchCount = branchCount
	}

	// Count merge requests
	if mrCount, err := s.countMergeRequests(gitRepo); err == nil {
		repo.MRCount = mrCount
	}

	return repo
}

func (s *Scanner) calculateRepoSize(path string) int64 {
	var size int64
	filepath.Walk(path, func(_ string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() {
			size += info.Size()
		}
		return nil
	})
	return size
}

func (s *Scanner) getLastUpdateTime(repo *git.Repository) (time.Time, error) {
	iter, err := repo.Log(&git.LogOptions{
		Order: git.LogOrderCommitterTime,
	})
	if err != nil {
		return time.Time{}, err
	}
	defer iter.Close()

	commit, err := iter.Next()
	if err != nil {
		return time.Time{}, err
	}

	return commit.Committer.When, nil
}

func (s *Scanner) countBranches(repo *git.Repository) (int, error) {
	iter, err := repo.Branches()
	if err != nil {
		return 0, err
	}
	defer iter.Close()

	count := 0
	iter.ForEach(func(ref *plumbing.Reference) error {
		count++
		return nil
	})

	return count, nil
}

func (s *Scanner) countMergeRequests(repo *git.Repository) (int, error) {
	storer := repo.Storer
	fsStorer, ok := storer.(*filesystem.Storage)
	if !ok {
		return 0, nil
	}

	iter, err := fsStorer.IterReferences()
	if err != nil {
		return 0, err
	}
	defer iter.Close()

	count := 0
	iter.ForEach(func(ref *plumbing.Reference) error {
		if strings.HasPrefix(ref.Name().String(), "refs/gitflower/merge-requests/") {
			count++
		}
		return nil
	})

	return count, nil
}

// CreateRepository creates a new bare repository
func CreateRepository(path string) error {
	// Validate the full path
	if err := ValidatePath(path); err != nil {
		return err
	}

	reposDir := cfg.ReposDirectory()
	fullPath := filepath.Join(reposDir, path)

	// Check if repository already exists
	if _, err := os.Stat(fullPath); err == nil {
		return fmt.Errorf("repository %s already exists", path)
	}

	// Create parent directories if needed
	parentDir := filepath.Dir(fullPath)
	if err := os.MkdirAll(parentDir, 0755); err != nil {
		return fmt.Errorf("creating parent directories: %w", err)
	}

	// Create the repository directory
	if err := os.MkdirAll(fullPath, 0755); err != nil {
		return fmt.Errorf("creating repository directory: %w", err)
	}

	// Initialize as bare repository
	_, err := git.PlainInit(fullPath, true)
	if err != nil {
		os.RemoveAll(fullPath) // Clean up on failure
		return fmt.Errorf("initializing repository: %w", err)
	}

	return nil
}
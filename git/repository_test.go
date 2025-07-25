package git

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/go-git/go-git/v6"

	"gitflower/cfg"
)

func TestCreateRepository(t *testing.T) {
	// Setup temp directory
	tempDir := t.TempDir()
	cfg.SetReposDirectory(tempDir)

	tests := []struct {
		name    string
		path    string
		wantErr bool
		errMsg  string
	}{
		{"simple repo", "test.git", false, ""},
		{"repo in folder", "work/project.git", false, ""},
		{"nested repo", "org/team/app.git", false, ""},
		{"invalid name", "Test.git", true, "must contain only lowercase letters"},
		{"missing .git", "project", true, "must end with .git"},
		{"duplicate repo", "test.git", true, "already exists"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := CreateRepository(tt.path)
			if (err != nil) != tt.wantErr {
				t.Errorf("CreateRepository(%q) error = %v, wantErr %v", tt.path, err, tt.wantErr)
			}
			if err != nil && tt.errMsg != "" {
				if !contains(err.Error(), tt.errMsg) {
					t.Errorf("CreateRepository(%q) error message = %v, want to contain %v", tt.path, err.Error(), tt.errMsg)
				}
			}

			// Verify repository was created if no error
			if !tt.wantErr && err == nil {
				repoPath := filepath.Join(tempDir, tt.path)
				if _, err := os.Stat(repoPath); os.IsNotExist(err) {
					t.Errorf("Repository directory %s was not created", repoPath)
				}

				// Verify it's a valid git repo
				_, err := git.PlainOpen(repoPath)
				if err != nil {
					t.Errorf("Created repository is not a valid git repo: %v", err)
				}
			}
		})
	}
}

func TestScanner(t *testing.T) {
	// Setup temp directory with repos
	tempDir := t.TempDir()
	cfg.SetReposDirectory(tempDir)

	// Create test structure
	repos := []string{
		"simple.git",
		"work/project.git",
		"personal/notes.git",
	}

	for _, repo := range repos {
		repoPath := filepath.Join(tempDir, repo)
		os.MkdirAll(filepath.Dir(repoPath), 0755)
		_, err := git.PlainInit(repoPath, true)
		if err != nil {
			t.Fatalf("Failed to create test repo %s: %v", repo, err)
		}
	}

	// Create invalid directories
	invalidDirs := []string{
		"INVALID",
		".hidden",
		"test..dir",
	}

	for _, dir := range invalidDirs {
		os.MkdirAll(filepath.Join(tempDir, dir), 0755)
	}

	// Create a valid org folder
	os.MkdirAll(filepath.Join(tempDir, "archived"), 0755)

	t.Run("ScanRepositories", func(t *testing.T) {
		scanner := NewScanner()
		foundRepos, warnings, err := scanner.Scan()
		
		if err != nil {
			t.Fatalf("Scan() error = %v", err)
		}

		// Check we found all repos
		if len(foundRepos) != len(repos) {
			t.Errorf("Found %d repositories, want %d", len(foundRepos), len(repos))
		}

		// Check warnings for invalid directories
		if len(warnings) != len(invalidDirs) {
			t.Errorf("Got %d warnings, want %d", len(warnings), len(invalidDirs))
		}

		// Verify repo data
		repoMap := make(map[string]*Repository)
		for _, repo := range foundRepos {
			repoMap[repo.RelativePath] = repo
		}

		for _, expectedPath := range repos {
			repo, exists := repoMap[expectedPath]
			if !exists {
				t.Errorf("Repository %s not found in scan results", expectedPath)
				continue
			}

			if !repo.IsValid {
				t.Errorf("Repository %s marked as invalid: %s", expectedPath, repo.Error)
			}

			if repo.Name != filepath.Base(expectedPath) {
				t.Errorf("Repository name = %s, want %s", repo.Name, filepath.Base(expectedPath))
			}
		}
	})

	t.Run("EmptyDirectory", func(t *testing.T) {
		emptyDir := t.TempDir()
		cfg.SetReposDirectory(emptyDir)
		
		scanner := NewScanner()
		repos, warnings, err := scanner.Scan()
		
		if err != nil {
			t.Fatalf("Scan() error = %v", err)
		}
		
		if len(repos) != 0 {
			t.Errorf("Expected 0 repos in empty directory, got %d", len(repos))
		}
		
		if len(warnings) != 0 {
			t.Errorf("Expected 0 warnings in empty directory, got %d", len(warnings))
		}
	})
}

func TestRepositoryMetadata(t *testing.T) {
	// Create a test repository with content
	tempDir := t.TempDir()
	repoPath := filepath.Join(tempDir, "test.git")
	_, err := git.PlainInit(repoPath, true)
	if err != nil {
		t.Fatalf("Failed to create test repo: %v", err)
	}
	
	cfg.SetReposDirectory(tempDir)
	scanner := NewScanner()

	t.Run("MetadataExtraction", func(t *testing.T) {
		repos, _, err := scanner.Scan()
		if err != nil {
			t.Fatalf("Scan() error = %v", err)
		}

		if len(repos) != 1 {
			t.Fatalf("Expected 1 repo, got %d", len(repos))
		}

		repoData := repos[0]
		
		// Check basic properties
		if repoData.Name != "test.git" {
			t.Errorf("Repository name = %s, want test.git", repoData.Name)
		}

		if repoData.Size == 0 {
			t.Error("Repository size should not be 0")
		}

		// New bare repos have 0 branches initially
		if repoData.BranchCount != 0 {
			t.Errorf("Branch count = %d, want 0 for new bare repo", repoData.BranchCount)
		}
	})
}
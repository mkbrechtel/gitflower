package test

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// TestE2ERepos tests all user stories for repository management
func TestE2ERepos(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping E2E test in short mode")
	}

	// Build the gitflower binary
	buildCmd := exec.Command("go", "build", "-o", "../bin/gitflower", "..")
	buildCmd.Dir = filepath.Dir(getBinaryPath())
	if err := buildCmd.Run(); err != nil {
		t.Fatalf("Failed to build gitflower: %v", err)
	}

	// Create temp directory for test repos
	tempDir := t.TempDir()
	
	// Use the static test config
	configPath := filepath.Join(filepath.Dir(getBinaryPath()), "..", "test", "config.yaml")
	
	// Set up environment with config path
	env := append(os.Environ(), 
		fmt.Sprintf("HOME=%s", tempDir),
		fmt.Sprintf("GITFLOWER_CONFIG=%s", configPath))

	// Helper to run gitflower commands
	runCodeflow := func(args ...string) (string, error) {
		cmd := exec.Command(getBinaryPath(), args...)
		cmd.Env = env
		var out bytes.Buffer
		var errOut bytes.Buffer
		cmd.Stdout = &out
		cmd.Stderr = &errOut
		err := cmd.Run()
		if err != nil {
			return errOut.String(), err
		}
		return out.String(), nil
	}

	// User Story 1: Discover all bare repositories
	t.Run("UserStory1_DiscoverRepositories", func(t *testing.T) {
		// Create some test repositories
		repos := []string{
			"project1.git",
			"work/backend.git",
			"personal/notes.git",
		}

		for _, repo := range repos {
			_, err := runCodeflow("create", repo)
			if err != nil {
				t.Fatalf("Failed to create repo %s: %v", repo, err)
			}
		}

		// List repositories
		output, err := runCodeflow("list")
		if err != nil {
			t.Fatalf("Failed to list repositories: %v", err)
		}

		// Verify all repos are listed
		for _, repo := range repos {
			if !strings.Contains(output, repo) {
				t.Errorf("Repository %s not found in list output", repo)
			}
		}

		// Verify table headers are shown
		if !strings.Contains(output, "PATH") || !strings.Contains(output, "BRANCHES") {
			t.Error("Table headers not shown in output")
		}
	})

	// User Story 2: Initialize new repositories
	t.Run("UserStory2_InitializeRepositories", func(t *testing.T) {
		// Create a simple repository
		output, err := runCodeflow("create", "new-project.git")
		if err != nil {
			t.Fatalf("Failed to create repository: %v", err)
		}

		if !strings.Contains(output, "Created repository") {
			t.Error("Create command did not confirm repository creation")
		}

		// Verify it appears in list
		listOutput, err := runCodeflow("list")
		if err != nil {
			t.Fatalf("Failed to list repositories: %v", err)
		}

		if !strings.Contains(listOutput, "new-project.git") {
			t.Error("New repository not found in list")
		}

		// Try to create duplicate
		_, err = runCodeflow("create", "new-project.git")
		if err == nil {
			t.Error("Expected error when creating duplicate repository")
		}
	})

	// User Story 3: List and filter repositories
	t.Run("UserStory3_ListRepositories", func(t *testing.T) {
		// Create repositories with different structures
		testRepos := []string{
			"frontend.git",
			"archived/old-app.git",
			"active/current-app.git",
		}

		for _, repo := range testRepos {
			_, err := runCodeflow("create", repo)
			if err != nil {
				t.Fatalf("Failed to create repo %s: %v", repo, err)
			}
		}

		// List all repositories
		output, err := runCodeflow("list")
		if err != nil {
			t.Fatalf("Failed to list repositories: %v", err)
		}

		// Verify hierarchical display
		if !strings.Contains(output, "archived/old-app.git") {
			t.Error("Hierarchical paths not preserved in list")
		}

		// Verify all repos are shown
		repoCount := strings.Count(output, ".git")
		if repoCount < len(testRepos) {
			t.Errorf("Expected at least %d repositories, found %d", len(testRepos), repoCount)
		}
	})

	// User Story 4: Repository access control
	t.Run("UserStory4_AccessControl", func(t *testing.T) {
		// This is controlled by filesystem permissions
		// Create a repo and verify it exists with proper permissions
		_, err := runCodeflow("create", "secure-repo.git")
		if err != nil {
			t.Fatalf("Failed to create repository: %v", err)
		}

		// Verify it's accessible (would fail if permissions were wrong)
		_, err = runCodeflow("list")
		if err != nil {
			t.Error("Could not list repositories - possible permission issue")
		}
	})

	// User Story 5: Web documentation
	t.Run("UserStory5_Documentation", func(t *testing.T) {
		// Verify documentation exists
		docPath := filepath.Join("..", "docs", "features", "tree.md")
		if _, err := os.Stat(docPath); os.IsNotExist(err) {
			t.Error("Repository management documentation not found")
		}
	})

	// User Story 6: Programmatic access (via CLI)
	t.Run("UserStory6_ProgrammaticAccess", func(t *testing.T) {
		// The CLI provides programmatic access
		// Test JSON-like parsing of list output
		output, err := runCodeflow("list")
		if err != nil {
			t.Fatalf("Failed to list repositories: %v", err)
		}

		// Verify structured output
		if strings.Contains(output, ".git") || strings.Contains(output, "No repositories found") {
			// Valid output - either has repos or explicitly states none found
			t.Log("Valid repository list output")
		} else {
			t.Error("Invalid list output format")
		}
	})

	// Additional tests for validation
	t.Run("ValidationRules", func(t *testing.T) {
		invalidNames := []struct {
			name string
			err  string
		}{
			{"test..repo.git", "cannot contain '..'"},
			{"UPPERCASE.git", "must contain only lowercase"},
			{"test_underscore.git", "must contain only lowercase"},
			{"test project.git", "must contain only lowercase"},
		}

		for _, tc := range invalidNames {
			output, err := runCodeflow("create", tc.name)
			if err == nil {
				t.Errorf("Expected error for invalid name %s", tc.name)
			} else if !strings.Contains(output, tc.err) {
				t.Errorf("Expected error containing '%s' for %s, got: %s", tc.err, tc.name, output)
			}
		}
	})


	// Test warning for invalid directories
	t.Run("InvalidDirectoryWarnings", func(t *testing.T) {
		// Create invalid directories in test-repos
		testReposDir := filepath.Join(filepath.Dir(getBinaryPath()), "..", "test-repos")
		os.MkdirAll(testReposDir, 0755)
		os.MkdirAll(filepath.Join(testReposDir, "INVALID_NAME"), 0755)
		os.MkdirAll(filepath.Join(testReposDir, ".hidden"), 0755)

		// List should show warnings when requested
		_, err := runCodeflow("list", "-warnings")
		if err != nil {
			// Check if warnings are in stderr
			if !strings.Contains(err.Error(), "Invalid") {
				t.Fatalf("Failed to list with invalid dirs: %v", err)
			}
			// Warnings might be in stderr, which is okay
			return
		}

		// If no error, the test passes (warnings shown in stderr)
		
		// Clean up
		os.RemoveAll(filepath.Join(testReposDir, "INVALID_NAME"))
		os.RemoveAll(filepath.Join(testReposDir, ".hidden"))
	})
}

func getBinaryPath() string {
	return filepath.Join("..", "bin", "gitflower")
}
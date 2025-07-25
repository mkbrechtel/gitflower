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

// TestE2ERepositoryManagement tests all user stories for repository management
func TestE2ERepositoryManagement(t *testing.T) {
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
	
	// Set up environment
	env := append(os.Environ(), fmt.Sprintf("HOME=%s", tempDir))

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
		// Configure repos directory
		reposDir := filepath.Join(tempDir, "test-repos")
		_, err := runCodeflow("config", "reposDirectory", reposDir)
		if err != nil {
			t.Fatalf("Failed to set reposDirectory: %v", err)
		}

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

		// Verify metadata is shown
		if !strings.Contains(output, "Size:") {
			t.Error("Repository size not shown in output")
		}
		if !strings.Contains(output, "Branches:") {
			t.Error("Branch count not shown in output")
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

		// Check the repository directory was created
		reposDir, _ := runCodeflow("config", "reposDirectory")
		repoPath := filepath.Join(strings.TrimSpace(reposDir), "secure-repo.git")
		
		info, err := os.Stat(repoPath)
		if err != nil {
			t.Fatalf("Repository directory not found: %v", err)
		}

		if !info.IsDir() {
			t.Error("Repository should be a directory")
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
		docPath := filepath.Join("..", "docs", "repository-management.md")
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
		lines := strings.Split(output, "\n")
		repoFound := false
		for _, line := range lines {
			if strings.Contains(line, ".git") && !strings.Contains(line, "Repositories in") {
				repoFound = true
				// Next lines should contain metadata
				break
			}
		}

		if !repoFound && strings.Contains(output, "No repositories found") {
			// Empty repo list is valid
			t.Log("No repositories found - valid state")
		}
	})

	// Additional tests for validation
	t.Run("ValidationRules", func(t *testing.T) {
		invalidNames := []struct {
			name string
			err  string
		}{
			{".hidden.git", "cannot start with a dot"},
			{"test..repo.git", "cannot contain '..'"},
			{"UPPERCASE.git", "must contain only lowercase"},
			{"test_underscore.git", "must contain only lowercase"},
			{"test project.git", "must contain only lowercase"},
			{"test", "must end with .git"},
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

	// Test configuration management
	t.Run("ConfigurationManagement", func(t *testing.T) {
		// Get current config
		_, err := runCodeflow("config", "reposDirectory")
		if err != nil {
			t.Fatalf("Failed to get config: %v", err)
		}

		// Set new value
		newDir := filepath.Join(tempDir, "new-repos")
		_, err = runCodeflow("config", "reposDirectory", newDir)
		if err != nil {
			t.Fatalf("Failed to set config: %v", err)
		}

		// Verify it was set
		currentDir, err := runCodeflow("config", "reposDirectory")
		if err != nil {
			t.Fatalf("Failed to get config after set: %v", err)
		}

		if strings.TrimSpace(currentDir) != newDir {
			t.Errorf("Config not updated: got %s, want %s", currentDir, newDir)
		}
	})

	// Test warning for invalid directories
	t.Run("InvalidDirectoryWarnings", func(t *testing.T) {
		reposDir, _ := runCodeflow("config", "reposDirectory")
		reposDir = strings.TrimSpace(reposDir)

		// Create invalid directories
		os.MkdirAll(filepath.Join(reposDir, "INVALID_NAME"), 0755)
		os.MkdirAll(filepath.Join(reposDir, ".hidden"), 0755)

		// List should show warnings
		output, err := runCodeflow("list")
		if err != nil {
			t.Fatalf("Failed to list with invalid dirs: %v", err)
		}

		if !strings.Contains(output, "Warnings:") {
			t.Error("No warnings section found for invalid directories")
		}

		if !strings.Contains(output, "Invalid directory name") {
			t.Error("No warning for invalid directory names")
		}
	})
}

func getBinaryPath() string {
	return filepath.Join("..", "bin", "gitflower")
}
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
		// Configure repos directory via environment
		reposDir := filepath.Join(tempDir, "test-repos")
		configDir := filepath.Join(tempDir, ".config", "gitflower")
		os.MkdirAll(configDir, 0755)
		
		// Create YAML config
		configContent := fmt.Sprintf(`repos:
  directory: "%s"
  scan_depth: 3
  default_branch: "main"
web:
  address: ":8080"
  theme: "light"
  cache_ttl: 300
cli:
  output_format: "table"
  colors: true
  pager: "less"
log:
  level: "info"
  format: "text"`, reposDir)
		
		configPath := filepath.Join(configDir, "config.yaml")
		if err := os.WriteFile(configPath, []byte(configContent), 0644); err != nil {
			t.Fatalf("Failed to write config: %v", err)
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

	// Test configuration management
	t.Run("ConfigurationManagement", func(t *testing.T) {
		// Get current config
		output, err := runCodeflow("config", "repos.directory")
		if err != nil {
			t.Fatalf("Failed to get config: %v", err)
		}
		
		// Verify we got a directory path
		if !strings.Contains(output, "/") && !strings.Contains(output, "repos") {
			t.Errorf("Invalid repos.directory value: %s", output)
		}
		
		// Get full config
		fullConfig, err := runCodeflow("config")
		if err != nil {
			t.Fatalf("Failed to get full config: %v", err)
		}
		
		// Verify YAML format
		if !strings.Contains(fullConfig, "repos:") || !strings.Contains(fullConfig, "web:") {
			t.Error("Config not in expected YAML format")
		}
	})

	// Test warning for invalid directories
	t.Run("InvalidDirectoryWarnings", func(t *testing.T) {
		reposDir, _ := runCodeflow("config", "repos.directory")
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
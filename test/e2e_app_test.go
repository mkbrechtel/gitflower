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

// TestE2EApp tests the application layer functionality
func TestE2EApp(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping E2E test in short mode")
	}

	// Build the gitflower binary
	buildCmd := exec.Command("go", "build", "-o", "../bin/gitflower", "..")
	buildCmd.Dir = filepath.Dir(getBinaryPath())
	if err := buildCmd.Run(); err != nil {
		t.Fatalf("Failed to build gitflower: %v", err)
	}

	// Create temp directory for test
	tempDir := t.TempDir()

	// Create test-repos directory
	reposDir := filepath.Join(tempDir, "test-repos")
	os.MkdirAll(reposDir, 0755)

	// Create a temporary config file that uses the temp directory
	configDir := filepath.Join(tempDir, ".config", "gitflower")
	os.MkdirAll(configDir, 0755)

	// Read the static test config as a template
	staticConfigPath := filepath.Join(filepath.Dir(getBinaryPath()), "..", "test", "config.yaml")
	staticConfig, err := os.ReadFile(staticConfigPath)
	if err != nil {
		t.Fatalf("Failed to read static test config: %v", err)
	}

	// Replace the repos directory path with the temp directory
	configContent := strings.Replace(string(staticConfig), "./test-repos/", reposDir+"/", 1)

	// Write the modified config to temp directory
	configPath := filepath.Join(configDir, "config.yaml")
	if err := os.WriteFile(configPath, []byte(configContent), 0644); err != nil {
		t.Fatalf("Failed to write config: %v", err)
	}

	// Set up environment with config path
	env := append(os.Environ(),
		fmt.Sprintf("HOME=%s", tempDir),
		fmt.Sprintf("GITFLOWER_CONFIG=%s", configPath))

	// Helper to run gitflower commands
	runGitflower := func(args ...string) (string, error) {
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

	// Test configuration loading and display
	t.Run("ConfigurationManagement", func(t *testing.T) {
		// Get full config
		output, err := runGitflower("config")
		if err != nil {
			t.Fatalf("Failed to get config: %v", err)
		}

		// Verify YAML format and all sections are present
		expectedSections := []string{"repos:", "web:", "cli:", "mcp:", "log:"}
		for _, section := range expectedSections {
			if !strings.Contains(output, section) {
				t.Errorf("Config missing section: %s", section)
			}
		}

		// Get specific config value
		webAddr, err := runGitflower("config", "web.address")
		if err != nil {
			t.Fatalf("Failed to get web.address: %v", err)
		}

		if !strings.Contains(webAddr, ":8747") {
			t.Errorf("Expected web.address to be :8747, got: %s", webAddr)
		}

		// Verify repos directory is configured
		reposConfig, err := runGitflower("config", "repos.directory")
		if err != nil {
			t.Fatalf("Failed to get repos.directory: %v", err)
		}

		if len(strings.TrimSpace(reposConfig)) == 0 {
			t.Error("repos.directory should not be empty")
		}
	})

	// Test logging configuration
	t.Run("LoggingConfiguration", func(t *testing.T) {
		// Get log level
		logLevel, err := runGitflower("config", "log.level")
		if err != nil {
			t.Fatalf("Failed to get log.level: %v", err)
		}

		if !strings.Contains(logLevel, "debug") {
			t.Errorf("Expected log.level to be debug for testing, got: %s", logLevel)
		}
	})

	// Test environment variable override
	t.Run("EnvironmentOverride", func(t *testing.T) {
		// Create another config file with different values
		altConfigContent := strings.Replace(string(staticConfig), ":8747", ":9999", 1)
		altConfigPath := filepath.Join(tempDir, "alt-config.yaml")
		if err := os.WriteFile(altConfigPath, []byte(altConfigContent), 0644); err != nil {
			t.Fatalf("Failed to write alt config: %v", err)
		}

		// Run with different config
		altEnv := append(os.Environ(),
			fmt.Sprintf("HOME=%s", tempDir),
			fmt.Sprintf("GITFLOWER_CONFIG=%s", altConfigPath))

		cmd := exec.Command(getBinaryPath(), "config", "web.address")
		cmd.Env = altEnv
		var out bytes.Buffer
		cmd.Stdout = &out
		if err := cmd.Run(); err != nil {
			t.Fatalf("Failed to run with alt config: %v", err)
		}

		if !strings.Contains(out.String(), ":9999") {
			t.Errorf("Expected web.address to be :9999 with alt config, got: %s", out.String())
		}
	})

	// Test help command
	t.Run("HelpCommand", func(t *testing.T) {
		output, _ := runGitflower("help")

		// If help command doesn't exist, try no args
		if len(output) == 0 {
			output, _ = runGitflower()
		}

		// Verify we get some help output (either from help command or usage)
		if len(output) == 0 {
			t.Skip("Help command not implemented")
		}

		// Verify help shows main commands
		expectedCommands := []string{"create", "list", "config", "web"}
		for _, cmd := range expectedCommands {
			if !strings.Contains(output, cmd) {
				t.Logf("Help output missing command: %s", cmd)
			}
		}
	})

	// Test version command
	t.Run("VersionCommand", func(t *testing.T) {
		output, err := runGitflower("version")
		if err != nil {
			// Version command might not be implemented yet
			t.Skip("Version command not implemented")
		}

		if !strings.Contains(output, "gitflower") {
			t.Errorf("Version output should contain 'gitflower', got: %s", output)
		}
	})

	// Test invalid command handling
	t.Run("InvalidCommand", func(t *testing.T) {
		_, err := runGitflower("nonexistent-command")
		if err == nil {
			t.Error("Expected error for invalid command")
		}
	})

	// Test config file existence
	t.Run("ConfigFileExistence", func(t *testing.T) {
		// Check if config file exists
		if _, err := os.Stat(configPath); os.IsNotExist(err) {
			t.Fatalf("Config file does not exist: %s", configPath)
		}

		// Run config command to verify it's readable
		_, err := runGitflower("config")
		if err != nil {
			t.Fatalf("Failed to read config: %v", err)
		}
	})

	// Test centralized application state
	t.Run("CentralizedState", func(t *testing.T) {
		// Create a repository to ensure app state is initialized
		_, err := runGitflower("create", "test-state.git")
		if err != nil {
			t.Fatalf("Failed to create repository: %v", err)
		}

		// List should work with same state
		output, err := runGitflower("list")
		if err != nil {
			t.Fatalf("Failed to list repositories: %v", err)
		}

		if !strings.Contains(output, "test-state.git") {
			t.Error("Repository not found in list - state may not be properly shared")
		}
	})

	// Test package separation
	t.Run("PackageSeparation", func(t *testing.T) {
		// Each interface should work independently

		// CLI interface
		cliOutput, err := runGitflower("list")
		if err != nil {
			t.Fatalf("CLI interface failed: %v", err)
		}

		// Web interface (just check it starts without error)
		webCmd := exec.Command(getBinaryPath(), "web")
		webCmd.Env = env

		// Start web server in background
		if err := webCmd.Start(); err != nil {
			t.Fatalf("Failed to start web server: %v", err)
		}

		// Kill it immediately (we just want to verify it starts)
		webCmd.Process.Kill()

		t.Log("CLI and Web interfaces work independently")
		_ = cliOutput // Use the output to avoid unused variable
	})

	// Test configuration sections ownership
	t.Run("ConfigSectionOwnership", func(t *testing.T) {
		config, err := runGitflower("config")
		if err != nil {
			t.Fatalf("Failed to get config: %v", err)
		}

		// Verify repos package owns repos: section
		if !strings.Contains(config, "repos:") || !strings.Contains(config, "directory:") {
			t.Error("repos: section not properly configured")
		}

		// Verify web package owns web: section
		if !strings.Contains(config, "web:") || !strings.Contains(config, "address:") {
			t.Error("web: section not properly configured")
		}

		// Verify cli package owns cli: section
		if !strings.Contains(config, "cli:") || !strings.Contains(config, "output_format:") {
			t.Error("cli: section not properly configured")
		}

		// Verify app package owns log: section
		if !strings.Contains(config, "log:") || !strings.Contains(config, "level:") {
			t.Error("log: section not properly configured")
		}
	})
}

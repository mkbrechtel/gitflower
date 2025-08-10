package test

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestWebInterfaceE2E(t *testing.T) {
	// Skip if not in E2E mode
	if os.Getenv("E2E_TEST") != "1" {
		t.Skip("Skipping E2E test. Set E2E_TEST=1 to run.")
	}

	// Setup test environment
	tmpDir := t.TempDir()
	reposDir := filepath.Join(tmpDir, "repos")
	os.MkdirAll(reposDir, 0755)

	// Create test config
	configPath := filepath.Join(tmpDir, "config.yaml")
	configContent := fmt.Sprintf(`
repos:
  directory: "%s"
  scan_depth: 3
  default_branch: "main"
web:
  address: ":8748"
  theme: "light"
cli:
  output_format: "table"
  colors: true
log:
  level: "info"
`, reposDir)

	err := os.WriteFile(configPath, []byte(configContent), 0644)
	if err != nil {
		t.Fatalf("Failed to write config: %v", err)
	}

	// Build gitflower if needed
	gitflowerPath := "../bin/gitflower"
	if _, err := os.Stat(gitflowerPath); os.IsNotExist(err) {
		// Try from test directory
		gitflowerPath = "bin/gitflower"
		if _, err := os.Stat(gitflowerPath); os.IsNotExist(err) {
			t.Fatalf("gitflower binary not found. Please run ./build.sh first")
		}
	}

	// Create test repositories
	createTestRepo := func(name string) {
		cmd := exec.Command(gitflowerPath, "create", name)
		cmd.Env = append(os.Environ(), fmt.Sprintf("GITFLOWER_CONFIG=%s", configPath))
		if err := cmd.Run(); err != nil {
			t.Fatalf("Failed to create repo %s: %v", name, err)
		}
	}

	createTestRepo("test-repo.git")
	createTestRepo("another-repo.git")

	// Create org structure
	os.MkdirAll(filepath.Join(reposDir, "work"), 0755)
	createTestRepo("work/project.git")
	createTestRepo("work/backend.git")

	// Start web server
	cmd := exec.Command(gitflowerPath, "web")
	cmd.Env = append(os.Environ(), fmt.Sprintf("GITFLOWER_CONFIG=%s", configPath))

	if err := cmd.Start(); err != nil {
		t.Fatalf("Failed to start web server: %v", err)
	}
	defer cmd.Process.Kill()

	// Wait for server to start
	time.Sleep(2 * time.Second)

	baseURL := "http://localhost:8748"

	// Test helper
	testEndpoint := func(t *testing.T, name, path string, expectedStatus int, expectedContent []string) {
		t.Run(name, func(t *testing.T) {
			resp, err := http.Get(baseURL + path)
			if err != nil {
				t.Fatalf("Failed to GET %s: %v", path, err)
			}
			defer resp.Body.Close()

			if resp.StatusCode != expectedStatus {
				t.Errorf("Expected status %d, got %d for %s", expectedStatus, resp.StatusCode, path)
			}

			body, _ := io.ReadAll(resp.Body)
			bodyStr := string(body)

			for _, expected := range expectedContent {
				if !strings.Contains(bodyStr, expected) {
					t.Errorf("Expected content to contain '%s' in %s", expected, path)
				}
			}
		})
	}

	// Test cases
	t.Run("BasicPages", func(t *testing.T) {
		testEndpoint(t, "HomePage", "/", http.StatusOK, []string{"GitFlower", "Repository Browser"})
		testEndpoint(t, "RepoList", "/repos/", http.StatusOK, []string{"test-repo.git", "another-repo.git"})
		testEndpoint(t, "RepoDetail", "/repos/test-repo.git", http.StatusOK, []string{"test-repo.git", "Clone"})
		testEndpoint(t, "OrgFolder", "/repos/work/", http.StatusOK, []string{"project.git", "backend.git"})
		testEndpoint(t, "404Page", "/nonexistent", http.StatusNotFound, []string{"404", "Not Found"})
	})

	t.Run("StaticAssets", func(t *testing.T) {
		resp, err := http.Get(baseURL + "/static/css/output.css")
		if err != nil {
			t.Fatalf("Failed to get CSS: %v", err)
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			t.Errorf("Expected status 200 for CSS, got %d", resp.StatusCode)
		}

		// Check cache headers
		cacheControl := resp.Header.Get("Cache-Control")
		if !strings.Contains(cacheControl, "max-age") {
			t.Error("Static assets should have cache headers")
		}
	})

	t.Run("GitProtocol", func(t *testing.T) {
		resp, err := http.Get(baseURL + "/repos/test-repo.git/info/refs?service=git-upload-pack")
		if err != nil {
			t.Fatalf("Failed to get git refs: %v", err)
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			t.Errorf("Expected status 200 for git refs, got %d", resp.StatusCode)
		}

		contentType := resp.Header.Get("Content-Type")
		if !strings.Contains(contentType, "git-upload-pack-advertisement") {
			t.Errorf("Expected git content type, got %s", contentType)
		}
	})

	t.Run("Performance", func(t *testing.T) {
		// Create many repos for performance test
		for i := 0; i < 20; i++ {
			createTestRepo(fmt.Sprintf("perf-repo-%d.git", i))
		}

		start := time.Now()
		resp, err := http.Get(baseURL + "/repos/")
		if err != nil {
			t.Fatalf("Failed to get repo list: %v", err)
		}
		defer resp.Body.Close()

		duration := time.Since(start)
		if duration > 200*time.Millisecond {
			t.Errorf("Repository list took %v, expected < 200ms", duration)
		}
	})

	t.Run("Security", func(t *testing.T) {
		// Test path traversal
		resp, err := http.Get(baseURL + "/repos/../../../etc/passwd")
		if err != nil {
			t.Fatalf("Failed path traversal test: %v", err)
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusNotFound {
			t.Errorf("Path traversal should return 404, got %d", resp.StatusCode)
		}

		// Test that POST is not allowed (read-only)
		resp, err = http.Post(baseURL+"/repos/test.git", "text/plain", strings.NewReader("test"))
		if err != nil {
			t.Fatalf("Failed POST test: %v", err)
		}
		defer resp.Body.Close()

		if resp.StatusCode == http.StatusOK {
			t.Error("POST should not be allowed on read-only interface")
		}
	})
}

func TestWebInterfaceWithContent(t *testing.T) {
	// Skip if not in E2E mode
	if os.Getenv("E2E_TEST") != "1" {
		t.Skip("Skipping E2E test. Set E2E_TEST=1 to run.")
	}

	// Setup
	tmpDir := t.TempDir()
	reposDir := filepath.Join(tmpDir, "repos")
	os.MkdirAll(reposDir, 0755)

	configPath := filepath.Join(tmpDir, "config.yaml")
	configContent := fmt.Sprintf(`
repos:
  directory: "%s"
  scan_depth: 3
  default_branch: "main"
web:
  address: ":8749"
  theme: "light"
log:
  level: "info"
`, reposDir)

	err := os.WriteFile(configPath, []byte(configContent), 0644)
	if err != nil {
		t.Fatalf("Failed to write config: %v", err)
	}

	// Create a repo with actual content
	repoPath := filepath.Join(reposDir, "content-test.git")
	cmd := exec.Command("git", "init", "--bare", repoPath)
	if err := cmd.Run(); err != nil {
		t.Fatalf("Failed to init repo: %v", err)
	}

	// Create a temporary clone to add content
	cloneDir := filepath.Join(tmpDir, "clone")
	cmd = exec.Command("git", "clone", repoPath, cloneDir)
	if err := cmd.Run(); err != nil {
		t.Fatalf("Failed to clone repo: %v", err)
	}

	// Add some files
	readmePath := filepath.Join(cloneDir, "README.md")
	os.WriteFile(readmePath, []byte("# Test Repository\n\nThis is a test."), 0644)

	srcDir := filepath.Join(cloneDir, "src")
	os.MkdirAll(srcDir, 0755)
	os.WriteFile(filepath.Join(srcDir, "main.go"), []byte("package main\n\nfunc main() {}\n"), 0644)

	// Commit and push
	cmd = exec.Command("git", "-C", cloneDir, "add", ".")
	cmd.Run()
	cmd = exec.Command("git", "-C", cloneDir, "commit", "-m", "Initial commit")
	cmd.Env = append(os.Environ(), "GIT_AUTHOR_NAME=Test", "GIT_AUTHOR_EMAIL=test@example.com",
		"GIT_COMMITTER_NAME=Test", "GIT_COMMITTER_EMAIL=test@example.com")
	cmd.Run()
	cmd = exec.Command("git", "-C", cloneDir, "push", "origin", "main")
	cmd.Run()

	// Start web server
	gitflowerPath := "bin/gitflower"
	if _, err := os.Stat(gitflowerPath); os.IsNotExist(err) {
		t.Fatalf("gitflower binary not found. Please run ./build.sh first")
	}

	cmd = exec.Command(gitflowerPath, "web")
	cmd.Env = append(os.Environ(), fmt.Sprintf("GITFLOWER_CONFIG=%s", configPath))

	if err := cmd.Start(); err != nil {
		t.Fatalf("Failed to start web server: %v", err)
	}
	defer cmd.Process.Kill()

	time.Sleep(2 * time.Second)

	baseURL := "http://localhost:8749"

	t.Run("FileTree", func(t *testing.T) {
		resp, err := http.Get(baseURL + "/repos/content-test.git/tree/main/")
		if err != nil {
			t.Fatalf("Failed to get file tree: %v", err)
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			t.Errorf("Expected status 200 for file tree, got %d", resp.StatusCode)
		}

		body, _ := io.ReadAll(resp.Body)
		bodyStr := string(body)

		if !strings.Contains(bodyStr, "README.md") {
			t.Error("File tree should show README.md")
		}
		if !strings.Contains(bodyStr, "src") {
			t.Error("File tree should show src directory")
		}
	})

	t.Run("FileContent", func(t *testing.T) {
		resp, err := http.Get(baseURL + "/repos/content-test.git/tree/main/README.md")
		if err != nil {
			t.Fatalf("Failed to get file content: %v", err)
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			t.Errorf("Expected status 200 for file content, got %d", resp.StatusCode)
		}

		body, _ := io.ReadAll(resp.Body)
		bodyStr := string(body)

		if !strings.Contains(bodyStr, "Test Repository") {
			t.Error("File content should show README content")
		}
	})

	t.Run("CommitView", func(t *testing.T) {
		// Get the commit SHA first
		resp, err := http.Get(baseURL + "/repos/content-test.git")
		if err != nil {
			t.Fatalf("Failed to get repo detail: %v", err)
		}
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()

		// Extract commit SHA from the page (would need proper parsing)
		// For now, just check that the repo detail page works
		if !strings.Contains(string(body), "Initial commit") {
			t.Error("Should show commit message on repo detail page")
		}
	})
}

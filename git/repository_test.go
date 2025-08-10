package git

import (
	"os"
	"path/filepath"
	"testing"

	"gitflower/tree"
	"github.com/go-git/go-git/v6"
)

func TestCreateRepository(t *testing.T) {
	// Setup temp directory
	tempDir := t.TempDir()

	tests := []struct {
		name    string
		path    string
		wantErr bool
		errMsg  string
	}{
		{"Valid repo", "test.git", false, ""},
		{"Repo in org", "myorg/project.git", false, ""},
		{"Nested repo", "org/team/app.git", false, ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := tree.CreateRepository(tempDir, tt.path)
			if (err != nil) != tt.wantErr {
				t.Errorf("CreateRepository(%q) error = %v, wantErr %v", tt.path, err, tt.wantErr)
			}
			if err != nil && tt.errMsg != "" {
				if err.Error() != tt.errMsg {
					t.Errorf("CreateRepository(%q) error message = %v, want to contain %v", tt.path, err.Error(), tt.errMsg)
				}
			}

			// Verify the repository was created
			if err == nil {
				fullPath := filepath.Join(tempDir, tt.path)
				if _, err := os.Stat(fullPath); os.IsNotExist(err) {
					t.Errorf("Repository directory not created at %s", fullPath)
				}

				// Verify it's a valid bare repository
				repo, err := git.PlainOpen(fullPath)
				if err != nil {
					t.Errorf("Failed to open repository: %v", err)
				}

				// Check if it's bare
				cfg, _ := repo.Config()
				if !cfg.Core.IsBare {
					t.Errorf("Repository is not bare")
				}
			}
		})
	}
}

package cfg

import (
	"os"
	"path/filepath"
	"testing"
)

func TestConfig(t *testing.T) {
	// Use temp directory for testing
	tempDir := t.TempDir()
	originalPath := configPath
	configPath = filepath.Join(tempDir, "config.json")
	defer func() { configPath = originalPath }()

	// Reset current config
	current = nil

	t.Run("LoadDefaultConfig", func(t *testing.T) {
		err := Load()
		if err != nil {
			t.Fatalf("Load() error = %v", err)
		}

		if got := ReposDirectory(); got != "./repos/" {
			t.Errorf("ReposDirectory() = %v, want %v", got, "./repos/")
		}
	})

	t.Run("SetAndSaveConfig", func(t *testing.T) {
		SetReposDirectory("/custom/repos")
		
		if got := ReposDirectory(); got != "/custom/repos" {
			t.Errorf("ReposDirectory() after set = %v, want %v", got, "/custom/repos")
		}

		err := Save()
		if err != nil {
			t.Fatalf("Save() error = %v", err)
		}

		// Verify file was created
		if _, err := os.Stat(configPath); os.IsNotExist(err) {
			t.Error("Config file was not created")
		}
	})

	t.Run("LoadSavedConfig", func(t *testing.T) {
		// Reset and reload
		current = nil
		err := Load()
		if err != nil {
			t.Fatalf("Load() error = %v", err)
		}

		if got := ReposDirectory(); got != "/custom/repos" {
			t.Errorf("ReposDirectory() after reload = %v, want %v", got, "/custom/repos")
		}
	})

	t.Run("GetSetMethods", func(t *testing.T) {
		// Test Get
		val, err := Get("reposDirectory")
		if err != nil {
			t.Fatalf("Get() error = %v", err)
		}
		if val != "/custom/repos" {
			t.Errorf("Get('reposDirectory') = %v, want %v", val, "/custom/repos")
		}

		// Test unknown key
		_, err = Get("unknown")
		if err == nil {
			t.Error("Get('unknown') expected error, got nil")
		}

		// Test Set
		err = Set("reposDirectory", "/new/path")
		if err != nil {
			t.Fatalf("Set() error = %v", err)
		}
		if got := ReposDirectory(); got != "/new/path" {
			t.Errorf("ReposDirectory() after Set = %v, want %v", got, "/new/path")
		}

		// Test Set unknown key
		err = Set("unknown", "value")
		if err == nil {
			t.Error("Set('unknown') expected error, got nil")
		}
	})
}
package git

import (
	"testing"
)

func TestValidateSlug(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		wantErr bool
		errMsg  string
	}{
		// Valid cases
		{"valid simple name", "test", false, ""},
		{"valid with hyphen", "test-project", false, ""},
		{"valid with dot", "test.project", false, ""},
		{"valid with numbers", "test123", false, ""},
		{"valid complex", "my-project-v1.2.3", false, ""},

		// Invalid cases
		{"dot only", ".", true, "cannot use special directory names"},
		{"double dot", "..", true, "cannot use special directory names"},
		{"starts with dot", ".hidden", true, "cannot start with a dot"},
		{"contains double dots", "test..project", true, "cannot contain '..'"},
		{"uppercase letters", "TestProject", true, "must contain only lowercase letters"},
		{"underscore", "test_project", true, "must contain only lowercase letters"},
		{"space", "test project", true, "must contain only lowercase letters"},
		{"special chars", "test@project", true, "must contain only lowercase letters"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := ValidateSlug(tt.input)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateSlug(%q) error = %v, wantErr %v", tt.input, err, tt.wantErr)
			}
			if err != nil && tt.errMsg != "" && err.Error() != tt.errMsg {
				if !contains(err.Error(), tt.errMsg) {
					t.Errorf("ValidateSlug(%q) error message = %v, want to contain %v", tt.input, err.Error(), tt.errMsg)
				}
			}
		})
	}
}

func TestValidateRepoName(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		wantErr bool
		errMsg  string
	}{
		// Valid cases
		{"valid repo name", "my-project.git", false, ""},
		{"valid with dots", "my.project.git", false, ""},
		{"valid with numbers", "project-123.git", false, ""},

		// Invalid cases
		{"missing .git", "my-project", true, "must end with .git"},
		{"invalid slug", "My-Project.git", true, "must contain only lowercase letters"},
		{"starts with dot", ".hidden.git", true, "cannot start with a dot"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := ValidateRepoName(tt.input)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateRepoName(%q) error = %v, wantErr %v", tt.input, err, tt.wantErr)
			}
			if err != nil && tt.errMsg != "" {
				if !contains(err.Error(), tt.errMsg) {
					t.Errorf("ValidateRepoName(%q) error message = %v, want to contain %v", tt.input, err.Error(), tt.errMsg)
				}
			}
		})
	}
}

func TestValidateOrgFolder(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		wantErr bool
		errMsg  string
	}{
		// Valid cases
		{"valid folder", "work", false, ""},
		{"valid with hyphen", "my-projects", false, ""},
		{"valid with dot", "archived.old", false, ""},

		// Invalid cases
		{"ends with .git", "work.git", true, "must not end with .git"},
		{"invalid slug", "Work", true, "must contain only lowercase letters"},
		{"starts with dot", ".hidden", true, "cannot start with a dot"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := ValidateOrgFolder(tt.input)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateOrgFolder(%q) error = %v, wantErr %v", tt.input, err, tt.wantErr)
			}
			if err != nil && tt.errMsg != "" {
				if !contains(err.Error(), tt.errMsg) {
					t.Errorf("ValidateOrgFolder(%q) error message = %v, want to contain %v", tt.input, err.Error(), tt.errMsg)
				}
			}
		})
	}
}

func TestValidatePath(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		wantErr bool
		errMsg  string
	}{
		// Valid cases
		{"simple repo", "project.git", false, ""},
		{"repo in folder", "work/project.git", false, ""},
		{"nested repo", "work/backend/api.git", false, ""},

		// Invalid cases
		{"folder without repo", "work/project", true, "must end with .git"},
		{"invalid folder name", "Work/project.git", true, "must contain only lowercase letters"},
		{"invalid repo name", "work/Project.git", true, "must contain only lowercase letters"},
		{"org folder ends with .git", "work.git/project.git", true, "must not end with .git"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := ValidatePath(tt.input)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidatePath(%q) error = %v, wantErr %v", tt.input, err, tt.wantErr)
			}
			if err != nil && tt.errMsg != "" {
				if !contains(err.Error(), tt.errMsg) {
					t.Errorf("ValidatePath(%q) error message = %v, want to contain %v", tt.input, err.Error(), tt.errMsg)
				}
			}
		})
	}
}

func TestIsRepository(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected bool
	}{
		{"repo name", "project.git", true},
		{"folder name", "work", false},
		{"file with .git", "readme.github", false},
		{"ends with .git", "my-repo.git", true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := IsRepository(tt.input); got != tt.expected {
				t.Errorf("IsRepository(%q) = %v, want %v", tt.input, got, tt.expected)
			}
		})
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && s[:len(substr)] == substr ||
		len(s) >= len(substr) && s[len(s)-len(substr):] == substr ||
		len(s) > len(substr) && findSubstring(s, substr)
}

func findSubstring(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

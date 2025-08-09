package git

import (
	"time"
)

// Repository represents a Git repository with metadata
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
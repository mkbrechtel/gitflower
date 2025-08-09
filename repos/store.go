package repos

import (
	"fmt"
	"log/slog"
	"path/filepath"
	"time"

	"gitflower/app"
)

type Store struct {
	config  *app.ReposConfig
	logger  *slog.Logger
	scanner *Scanner
}

func NewStore(config *app.ReposConfig, logger *slog.Logger) *Store {
	return &Store{
		config:  config,
		logger:  logger,
		scanner: NewScanner(config.Directory, logger),
	}
}

func (s *Store) Scan() ([]*app.Repository, []string, error) {
	s.logger.Info("Scanning repositories", "directory", s.config.Directory)
	repos, warnings, err := s.scanner.Scan()
	if err != nil {
		return nil, nil, fmt.Errorf("scanning repositories: %w", err)
	}
	
	result := make([]*app.Repository, len(repos))
	for i, r := range repos {
		result[i] = &app.Repository{
			Path:         r.Path,
			Name:         r.Name,
			RelativePath: r.RelativePath,
			Size:         r.Size,
			LastUpdate:   r.LastUpdate.Format(time.RFC3339),
			BranchCount:  r.BranchCount,
			MRCount:      r.MRCount,
			IsValid:      r.IsValid,
			Error:        r.Error,
		}
	}
	
	return result, warnings, nil
}

func (s *Store) Get(path string) (*app.Repository, error) {
	fullPath := filepath.Join(s.config.Directory, path)
	repo := s.scanner.scanRepository(fullPath, path)
	
	return &app.Repository{
		Path:         repo.Path,
		Name:         repo.Name,
		RelativePath: repo.RelativePath,
		Size:         repo.Size,
		LastUpdate:   repo.LastUpdate.Format(time.RFC3339),
		BranchCount:  repo.BranchCount,
		MRCount:      repo.MRCount,
		IsValid:      repo.IsValid,
		Error:        repo.Error,
	}, nil
}

func (s *Store) Create(path string) error {
	return CreateRepository(s.config.Directory, path)
}

func (s *Store) List() ([]*app.Repository, error) {
	repos, _, err := s.Scan()
	return repos, err
}
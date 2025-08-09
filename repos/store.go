package repos

import (
	"fmt"
	"log/slog"
	"path/filepath"
)

type Store struct {
	config  Config
	logger  *slog.Logger
	scanner *Scanner
}

func NewStore(config Config, logger *slog.Logger) (*Store, error) {
	return &Store{
		config:  config,
		logger:  logger,
		scanner: NewScanner(config.Directory, logger),
	}, nil
}

func (s *Store) Scan() ([]*Repository, []string, error) {
	s.logger.Info("Scanning repositories", "directory", s.config.Directory)
	repos, warnings, err := s.scanner.Scan()
	if err != nil {
		return nil, nil, fmt.Errorf("scanning repositories: %w", err)
	}
	
	return repos, warnings, nil
}

func (s *Store) Get(path string) (*Repository, error) {
	fullPath := filepath.Join(s.config.Directory, path)
	repo := s.scanner.scanRepository(fullPath, path)
	return repo, nil
}

func (s *Store) Create(path string) error {
	return CreateRepository(s.config.Directory, path)
}

func (s *Store) List() ([]*Repository, error) {
	repos, _, err := s.Scan()
	return repos, err
}
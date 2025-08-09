package app

import (
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"sync"
)

type Application struct {
	config     *Config
	configPath string
	logger     *slog.Logger
	mu         sync.RWMutex
	
	repoStore  RepositoryStore
}

type RepositoryStore interface {
	Scan() ([]*Repository, []string, error)
	Get(path string) (*Repository, error)
	Create(path string) error
	List() ([]*Repository, error)
}

func New(configPath string) (*Application, error) {
	if configPath == "" {
		homeDir, err := os.UserHomeDir()
		if err != nil {
			return nil, fmt.Errorf("getting home directory: %w", err)
		}
		configPath = filepath.Join(homeDir, ".config", "gitflower", "config.yaml")
	}
	
	app := &Application{
		configPath: configPath,
	}
	
	if err := app.loadConfig(); err != nil {
		return nil, fmt.Errorf("loading config: %w", err)
	}
	
	app.setupLogger()
	
	return app, nil
}

func (a *Application) loadConfig() error {
	config, err := LoadConfig(a.configPath)
	if err != nil {
		if os.IsNotExist(err) {
			config = DefaultConfig()
			// Note: logger not yet initialized, will log after setup
		} else {
			return err
		}
	}
	
	a.mu.Lock()
	a.config = config
	a.mu.Unlock()
	
	return nil
}

func (a *Application) setupLogger() {
	a.mu.RLock()
	logConfig := a.config.Log
	a.mu.RUnlock()
	
	var level slog.Level
	switch logConfig.Level {
	case "debug":
		level = slog.LevelDebug
	case "info":
		level = slog.LevelInfo
	case "warn":
		level = slog.LevelWarn
	case "error":
		level = slog.LevelError
	default:
		level = slog.LevelInfo
	}
	
	opts := &slog.HandlerOptions{
		Level: level,
	}
	
	var handler slog.Handler
	if logConfig.Format == "json" {
		handler = slog.NewJSONHandler(os.Stderr, opts)
	} else {
		handler = slog.NewTextHandler(os.Stderr, opts)
	}
	
	a.logger = slog.New(handler)
	slog.SetDefault(a.logger)
}

func (a *Application) Config() *Config {
	a.mu.RLock()
	defer a.mu.RUnlock()
	return a.config
}

func (a *Application) Logger() *slog.Logger {
	return a.logger
}

func (a *Application) RepoStore() RepositoryStore {
	return a.repoStore
}

func (a *Application) SetRepoStore(store RepositoryStore) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.repoStore = store
}

func (a *Application) SaveConfig() error {
	a.mu.RLock()
	config := a.config
	a.mu.RUnlock()
	
	return SaveConfig(a.configPath, config)
}

type Repository struct {
	Path         string    `yaml:"path"`
	Name         string    `yaml:"name"`
	RelativePath string    `yaml:"relativePath"`
	Size         int64     `yaml:"size"`
	LastUpdate   string    `yaml:"lastUpdate"`
	BranchCount  int       `yaml:"branchCount"`
	MRCount      int       `yaml:"mrCount"`
	IsValid      bool      `yaml:"isValid"`
	Error        string    `yaml:"error,omitempty"`
}
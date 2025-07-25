package cfg

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

type Config struct {
	ReposDirectory string `json:"reposDirectory"`
}

var (
	mu         sync.RWMutex
	configPath string
	current    *Config
)

func init() {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		configPath = ".gitflower/config.json"
	} else {
		configPath = filepath.Join(homeDir, ".config", "gitflower", "config.json")
	}
}

func Load() error {
	mu.Lock()
	defer mu.Unlock()

	current = &Config{
		ReposDirectory: "./repos/", // default
	}

	data, err := os.ReadFile(configPath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return fmt.Errorf("reading config: %w", err)
	}

	if err := json.Unmarshal(data, current); err != nil {
		return fmt.Errorf("parsing config: %w", err)
	}

	return nil
}

func Save() error {
	mu.Lock()
	defer mu.Unlock()

	if current == nil {
		return fmt.Errorf("no config loaded")
	}

	dir := filepath.Dir(configPath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("creating config directory: %w", err)
	}

	data, err := json.MarshalIndent(current, "", "  ")
	if err != nil {
		return fmt.Errorf("marshaling config: %w", err)
	}

	if err := os.WriteFile(configPath, data, 0644); err != nil {
		return fmt.Errorf("writing config: %w", err)
	}

	return nil
}

func ReposDirectory() string {
	mu.RLock()
	defer mu.RUnlock()

	if current == nil || current.ReposDirectory == "" {
		return "./repos/"
	}
	return current.ReposDirectory
}

func SetReposDirectory(dir string) {
	mu.Lock()
	defer mu.Unlock()

	if current == nil {
		current = &Config{}
	}
	current.ReposDirectory = dir
}

func Get(key string) (string, error) {
	mu.RLock()
	defer mu.RUnlock()

	if current == nil {
		if err := Load(); err != nil {
			return "", err
		}
	}

	switch key {
	case "reposDirectory":
		return ReposDirectory(), nil
	default:
		return "", fmt.Errorf("unknown config key: %s", key)
	}
}

func Set(key, value string) error {
	if current == nil {
		if err := Load(); err != nil {
			return err
		}
	}

	switch key {
	case "reposDirectory":
		SetReposDirectory(value)
	default:
		return fmt.Errorf("unknown config key: %s", key)
	}

	return Save()
}
package app

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"gitflower/repos"
	"gitflower/web"

	"gopkg.in/yaml.v3"
)

type globalConfig struct {
	Repos repos.Config `yaml:"repos"`
	Web   web.Config   `yaml:"web"`
}

// load parses global flags and reads the config file
func load(args []string) (*globalConfig, []string, error) {
	// Create a new flag set for global flags
	fs := flag.NewFlagSet("gitflower", flag.ContinueOnError)

	var configPath string
	var reposDir string

	// Define global flags
	fs.StringVar(&configPath, "c", "", "Config file path")
	fs.StringVar(&reposDir, "r", "", "Repositories directory")

	// Parse only known flags
	if err := fs.Parse(args[1:]); err != nil {
		return nil, nil, fmt.Errorf("parsing flags: %w", err)
	}

	// Get config path from flag or environment
	if configPath == "" {
		configPath = os.Getenv("GITFLOWER_CONFIG")
	}
	if configPath == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return nil, nil, fmt.Errorf("getting home directory: %w", err)
		}
		configPath = filepath.Join(home, ".config", "gitflower", "config.yaml")
	}

	// Load default config
	config := &globalConfig{
		Repos: repos.Config{
			Directory:     "./repos/",
			ScanDepth:     3,
			DefaultBranch: "main",
		},
		Web: web.Config{
			Address: ":8747",
		},
	}

	// Read config file if it exists
	if data, err := os.ReadFile(configPath); err == nil {
		if err := yaml.Unmarshal(data, config); err != nil {
			return nil, nil, fmt.Errorf("parsing config file: %w", err)
		}
	}

	// Override with environment variable
	if envReposDir := os.Getenv("GITFLOWER_REPOS"); envReposDir != "" {
		config.Repos.Directory = envReposDir
	}

	// Override with flag values (flags have highest priority)
	if reposDir != "" {
		config.Repos.Directory = reposDir
	}

	// Return config and remaining args
	return config, fs.Args(), nil
}

// configCmd displays configuration values
func configCmd(config *globalConfig, args []string) error {
	fs := flag.NewFlagSet("config", flag.ExitOnError)
	fs.Parse(args)

	// For now, just print the config
	fmt.Printf("Repositories directory: %s\n", config.Repos.Directory)
	fmt.Printf("Scan depth: %d\n", config.Repos.ScanDepth)
	fmt.Printf("Default branch: %s\n", config.Repos.DefaultBranch)
	fmt.Printf("Web address: %s\n", config.Web.Address)

	return nil
}

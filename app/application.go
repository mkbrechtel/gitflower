package app

import (
	"fmt"
	"log/slog"
	"os"
	"path/filepath"

	"gitflower/repos"
	"gopkg.in/yaml.v3"
)

type Application struct {
	Config *Config
	Store  *repos.Store
	Logger *slog.Logger
}

func New(configPath string) (*Application, error) {
	config, err := LoadConfig(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to load config: %w", err)
	}

	logLevel := slog.LevelInfo
	switch config.Log.Level {
	case "debug":
		logLevel = slog.LevelDebug
	case "warn":
		logLevel = slog.LevelWarn
	case "error":
		logLevel = slog.LevelError
	}

	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{
		Level: logLevel,
	}))

	store, err := repos.NewStore(config.Repos, logger)
	if err != nil {
		return nil, fmt.Errorf("failed to create repository store: %w", err)
	}

	return &Application{
		Config: config,
		Store:  store,
		Logger: logger,
	}, nil
}

type Config struct {
	Repos repos.Config       `yaml:"repos"`
	Web   WebConfig          `yaml:"web"`
	CLI   CLIConfig          `yaml:"cli"`
	MCP   MCPConfig          `yaml:"mcp"`
	Log   LogConfig          `yaml:"log"`
}

type WebConfig struct {
	Address string `yaml:"address"`
	Theme   string `yaml:"theme"`
	Caching bool   `yaml:"caching"`
}

type CLIConfig struct {
	OutputFormat string `yaml:"output_format"`
	Colors       bool   `yaml:"colors"`
	Pager        bool   `yaml:"pager"`
}

type MCPConfig struct {
	StdioMode bool `yaml:"stdio_mode"`
}

type LogConfig struct {
	Level string `yaml:"level"`
}

func LoadConfig(path string) (*Config, error) {
	if path == "" {
		path = defaultConfigPath()
	}

	config := &Config{
		Repos: repos.Config{
			Directory:     "./repos/",
			ScanDepth:     3,
			DefaultBranch: "main",
		},
		Web: WebConfig{
			Address: ":8747",
			Theme:   "light",
			Caching: true,
		},
		CLI: CLIConfig{
			OutputFormat: "table",
			Colors:       true,
			Pager:        false,
		},
		MCP: MCPConfig{
			StdioMode: true,
		},
		Log: LogConfig{
			Level: "info",
		},
	}

	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return config, nil
		}
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}

	if err := yaml.Unmarshal(data, config); err != nil {
		return nil, fmt.Errorf("failed to parse config: %w", err)
	}

	return config, nil
}

func defaultConfigPath() string {
	if configDir := os.Getenv("GITFLOWER_CONFIG"); configDir != "" {
		return configDir
	}

	homeDir, err := os.UserHomeDir()
	if err != nil {
		return "config.yaml"
	}

	return filepath.Join(homeDir, ".config", "gitflower", "config.yaml")
}
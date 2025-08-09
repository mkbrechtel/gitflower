package app

import (
	"fmt"
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

type Config struct {
	Repos ReposConfig `yaml:"repos"`
	Web   WebConfig   `yaml:"web"`
	CLI   CLIConfig   `yaml:"cli"`
	MCP   MCPConfig   `yaml:"mcp"`
	Log   LogConfig   `yaml:"log"`
}

type ReposConfig struct {
	Directory     string `yaml:"directory"`
	ScanDepth     int    `yaml:"scan_depth"`
	DefaultBranch string `yaml:"default_branch"`
}

type WebConfig struct {
	Address  string `yaml:"address"`
	Theme    string `yaml:"theme"`
	CacheTTL int    `yaml:"cache_ttl"`
}

type CLIConfig struct {
	OutputFormat string `yaml:"output_format"`
	Colors       bool   `yaml:"colors"`
	Pager        string `yaml:"pager"`
}

type MCPConfig struct {
	StdioMode bool `yaml:"stdio_mode"`
}

type LogConfig struct {
	Level  string `yaml:"level"`
	Format string `yaml:"format"`
}

func DefaultConfig() *Config {
	return &Config{
		Repos: ReposConfig{
			Directory:     "./repos/",
			ScanDepth:     3,
			DefaultBranch: "main",
		},
		Web: WebConfig{
			Address:  ":8080",
			Theme:    "light",
			CacheTTL: 300,
		},
		CLI: CLIConfig{
			OutputFormat: "table",
			Colors:       true,
			Pager:        "less",
		},
		MCP: MCPConfig{
			StdioMode: true,
		},
		Log: LogConfig{
			Level:  "info",
			Format: "text",
		},
	}
}

func LoadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	
	config := DefaultConfig()
	if err := yaml.Unmarshal(data, config); err != nil {
		return nil, fmt.Errorf("parsing config: %w", err)
	}
	
	if err := config.Validate(); err != nil {
		return nil, fmt.Errorf("validating config: %w", err)
	}
	
	return config, nil
}

func SaveConfig(path string, config *Config) error {
	if err := config.Validate(); err != nil {
		return fmt.Errorf("validating config: %w", err)
	}
	
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("creating config directory: %w", err)
	}
	
	data, err := yaml.Marshal(config)
	if err != nil {
		return fmt.Errorf("marshaling config: %w", err)
	}
	
	if err := os.WriteFile(path, data, 0644); err != nil {
		return fmt.Errorf("writing config: %w", err)
	}
	
	return nil
}

func (c *Config) Validate() error {
	if err := c.Repos.Validate(); err != nil {
		return fmt.Errorf("repos config: %w", err)
	}
	
	if err := c.Web.Validate(); err != nil {
		return fmt.Errorf("web config: %w", err)
	}
	
	if err := c.CLI.Validate(); err != nil {
		return fmt.Errorf("cli config: %w", err)
	}
	
	if err := c.Log.Validate(); err != nil {
		return fmt.Errorf("log config: %w", err)
	}
	
	return nil
}

func (r *ReposConfig) Validate() error {
	if r.Directory == "" {
		return fmt.Errorf("directory cannot be empty")
	}
	
	if r.ScanDepth < 1 {
		return fmt.Errorf("scan_depth must be at least 1")
	}
	
	if r.DefaultBranch == "" {
		return fmt.Errorf("default_branch cannot be empty")
	}
	
	return nil
}

func (w *WebConfig) Validate() error {
	if w.Address == "" {
		return fmt.Errorf("address cannot be empty")
	}
	
	if w.Theme != "light" && w.Theme != "dark" {
		return fmt.Errorf("theme must be 'light' or 'dark'")
	}
	
	if w.CacheTTL < 0 {
		return fmt.Errorf("cache_ttl cannot be negative")
	}
	
	return nil
}

func (c *CLIConfig) Validate() error {
	validFormats := map[string]bool{
		"table": true,
		"json":  true,
		"yaml":  true,
		"plain": true,
	}
	
	if !validFormats[c.OutputFormat] {
		return fmt.Errorf("invalid output_format: %s", c.OutputFormat)
	}
	
	return nil
}

func (l *LogConfig) Validate() error {
	validLevels := map[string]bool{
		"debug": true,
		"info":  true,
		"warn":  true,
		"error": true,
	}
	
	if !validLevels[l.Level] {
		return fmt.Errorf("invalid log level: %s", l.Level)
	}
	
	if l.Format != "text" && l.Format != "json" {
		return fmt.Errorf("format must be 'text' or 'json'")
	}
	
	return nil
}
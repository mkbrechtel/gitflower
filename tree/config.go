package tree

type Config struct {
	Directory     string `yaml:"directory"`
	ScanDepth     int    `yaml:"scan_depth"`
	DefaultBranch string `yaml:"default_branch"`
}
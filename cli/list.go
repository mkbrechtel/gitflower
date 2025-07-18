package cli

import (
	"flag"
	"fmt"
	"time"

	"codeflow/cfg"
	"codeflow/git"
)

func init() {
	Register(&Command{
		Name:        "list",
		Description: "List all repositories",
		Run:         executeList,
	})
}

func executeList(args []string) error {
	fs := flag.NewFlagSet("list", flag.ExitOnError)
	fs.Usage = func() {
		fmt.Println("Usage: codeflow list")
		fmt.Println("\nList all repositories in the configured repos directory.")
	}

	if err := fs.Parse(args); err != nil {
		return err
	}

	// Load configuration
	if err := cfg.Load(); err != nil {
		return fmt.Errorf("loading config: %w", err)
	}

	// Scan for repositories
	scanner := git.NewScanner()
	repos, warnings, err := scanner.Scan()
	if err != nil {
		return fmt.Errorf("scanning repositories: %w", err)
	}

	// Display warnings first
	if len(warnings) > 0 {
		fmt.Println("Warnings:")
		for _, warning := range warnings {
			fmt.Printf("  ⚠️  %s\n", warning)
		}
		fmt.Println()
	}

	// Display repositories
	if len(repos) == 0 {
		fmt.Printf("No repositories found in %s\n", cfg.ReposDirectory())
		return nil
	}

	fmt.Printf("Repositories in %s:\n\n", cfg.ReposDirectory())
	
	for _, repo := range repos {
		fmt.Printf("%s\n", repo.RelativePath)
		
		if repo.IsValid {
			fmt.Printf("  Size: %s\n", formatSize(repo.Size))
			if !repo.LastUpdate.IsZero() {
				fmt.Printf("  Last update: %s\n", formatTime(repo.LastUpdate))
			}
			fmt.Printf("  Branches: %d\n", repo.BranchCount)
			if repo.MRCount > 0 {
				fmt.Printf("  Merge requests: %d\n", repo.MRCount)
			}
		} else {
			fmt.Printf("  ❌ %s\n", repo.Error)
		}
		
		fmt.Println()
	}

	return nil
}

func formatSize(bytes int64) string {
	const unit = 1024
	if bytes < unit {
		return fmt.Sprintf("%d B", bytes)
	}
	div, exp := int64(unit), 0
	for n := bytes / unit; n >= unit; n /= unit {
		div *= unit
		exp++
	}
	return fmt.Sprintf("%.1f %cB", float64(bytes)/float64(div), "KMGTPE"[exp])
}

func formatTime(t time.Time) string {
	duration := time.Since(t)
	
	if duration < time.Minute {
		return "just now"
	} else if duration < time.Hour {
		mins := int(duration.Minutes())
		if mins == 1 {
			return "1 minute ago"
		}
		return fmt.Sprintf("%d minutes ago", mins)
	} else if duration < 24*time.Hour {
		hours := int(duration.Hours())
		if hours == 1 {
			return "1 hour ago"
		}
		return fmt.Sprintf("%d hours ago", hours)
	} else if duration < 30*24*time.Hour {
		days := int(duration.Hours() / 24)
		if days == 1 {
			return "1 day ago"
		}
		return fmt.Sprintf("%d days ago", days)
	}
	
	return t.Format("2006-01-02")
}
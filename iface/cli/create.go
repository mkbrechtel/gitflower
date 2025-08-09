package cli

import (
	"flag"
	"fmt"
	"strings"
)

func executeCreate(cli *CLI, args []string) error {
	fs := flag.NewFlagSet("create", flag.ExitOnError)
	fs.Usage = func() {
		fmt.Fprintf(fs.Output(), "Usage: gitflower create <repository-path>\n")
		fmt.Fprintf(fs.Output(), "\nCreates a new bare Git repository.\n")
		fmt.Fprintf(fs.Output(), "\nExamples:\n")
		fmt.Fprintf(fs.Output(), "  gitflower create myproject.git\n")
		fmt.Fprintf(fs.Output(), "  gitflower create myorg/myproject.git\n")
	}
	
	if err := fs.Parse(args); err != nil {
		return err
	}
	
	if fs.NArg() != 1 {
		fs.Usage()
		return fmt.Errorf("exactly one repository path required")
	}
	
	repoPath := fs.Arg(0)
	
	if !strings.HasSuffix(repoPath, ".git") {
		repoPath += ".git"
	}
	
	store := cli.app.Store
	if store == nil {
		return fmt.Errorf("repository store not initialized")
	}
	
	if err := store.Create(repoPath); err != nil {
		return fmt.Errorf("creating repository: %w", err)
	}
	
	fmt.Printf("Created repository: %s\n", repoPath)
	
	config := cli.app.Config
	fullPath := fmt.Sprintf("%s/%s", strings.TrimSuffix(config.Repos.Directory, "/"), repoPath)
	fmt.Printf("\nTo push to this repository:\n")
	fmt.Printf("  git remote add origin %s\n", fullPath)
	fmt.Printf("  git push -u origin %s\n", config.Repos.DefaultBranch)
	
	return nil
}
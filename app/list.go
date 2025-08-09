package app

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"text/tabwriter"
	"time"

	"gitflower/tree"
	"gopkg.in/yaml.v3"
)

func list(store *tree.Store, args []string) error {
	fs := flag.NewFlagSet("list", flag.ExitOnError)
	format := fs.String("format", "table", "Output format (table, json, yaml)")
	showWarnings := fs.Bool("warnings", false, "Show scan warnings")
	
	fs.Usage = func() {
		fmt.Fprintf(fs.Output(), "Usage: gitflower list [options]\n")
		fmt.Fprintf(fs.Output(), "\nOptions:\n")
		fs.PrintDefaults()
	}
	
	if err := fs.Parse(args); err != nil {
		return err
	}
	if store == nil {
		return fmt.Errorf("repository store not initialized")
	}
	
	repositories, warnings, err := store.Scan()
	if err != nil {
		return fmt.Errorf("scanning repositories: %w", err)
	}
	
	if *showWarnings && len(warnings) > 0 {
		fmt.Fprintf(os.Stderr, "Warnings:\n")
		for _, warning := range warnings {
			fmt.Fprintf(os.Stderr, "  - %s\n", warning)
		}
		fmt.Fprintln(os.Stderr)
	}
	
	switch *format {
	case "json":
		return outputJSON(repositories)
	case "yaml":
		return outputYAML(repositories)
	default:
		return outputTable(repositories)
	}
}

func outputTable(repositories interface{}) error {
	w := tabwriter.NewWriter(os.Stdout, 0, 0, 2, ' ', 0)
	defer w.Flush()
	
	fmt.Fprintln(w, "PATH\tBRANCHES\tMR\tSIZE\tLAST UPDATE\tSTATUS")
	fmt.Fprintln(w, "----\t--------\t--\t----\t-----------\t------")
	
	repoList, ok := repositories.([]*tree.Repository)
	if !ok {
		return fmt.Errorf("unexpected repos type")
	}
	
	if len(repoList) == 0 {
		fmt.Fprintln(w, "No repositories found")
		return nil
	}
	
	for _, repo := range repoList {
		status := "OK"
		if !repo.IsValid {
			status = "ERROR"
			if repo.Error != "" {
				status = "ERROR: " + repo.Error
			}
		}
		
		fmt.Fprintf(w, "%s\t%d\t%d\t%.2f MB\t%s\t%s\n",
			repo.RelativePath,
			repo.BranchCount,
			repo.MRCount,
			float64(repo.Size)/(1024*1024),
			repo.LastUpdate.Format(time.RFC3339),
			status,
		)
	}
	
	return nil
}

func outputJSON(repos interface{}) error {
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	return encoder.Encode(repos)
}

func outputYAML(repos interface{}) error {
	encoder := yaml.NewEncoder(os.Stdout)
	defer encoder.Close()
	return encoder.Encode(repos)
}
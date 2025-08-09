package cli

import (
	"flag"
	"fmt"
	"strings"

	"gopkg.in/yaml.v3"
)

func executeConfig(cli *CLI, args []string) error {
	fs := flag.NewFlagSet("config", flag.ExitOnError)
	fs.Usage = func() {
		fmt.Fprintf(fs.Output(), "Usage: gitflower config [key] [value]\n")
		fmt.Fprintf(fs.Output(), "\nExamples:\n")
		fmt.Fprintf(fs.Output(), "  gitflower config                    # Show all configuration\n")
		fmt.Fprintf(fs.Output(), "  gitflower config repos.directory     # Get specific value\n")
		fmt.Fprintf(fs.Output(), "  gitflower config repos.directory ./repos  # Set value\n")
	}
	
	if err := fs.Parse(args); err != nil {
		return err
	}
	
	remainingArgs := fs.Args()
	
	if len(remainingArgs) == 0 {
		config := cli.app.Config
		data, err := yaml.Marshal(config)
		if err != nil {
			return fmt.Errorf("marshaling config: %w", err)
		}
		fmt.Print(string(data))
		return nil
	}
	
	key := remainingArgs[0]
	
	if len(remainingArgs) == 1 {
		value, err := getConfigValue(cli.app.Config, key)
		if err != nil {
			return err
		}
		fmt.Println(value)
		return nil
	}
	
	value := remainingArgs[1]
	if err := setConfigValue(cli.app.Config, key, value); err != nil {
		return err
	}
	
	return fmt.Errorf("config save not yet implemented")
}

func getConfigValue(config interface{}, key string) (string, error) {
	parts := strings.Split(key, ".")
	
	data, err := yaml.Marshal(config)
	if err != nil {
		return "", err
	}
	
	var m map[string]interface{}
	if err := yaml.Unmarshal(data, &m); err != nil {
		return "", err
	}
	
	var current interface{} = m
	for _, part := range parts {
		switch v := current.(type) {
		case map[string]interface{}:
			var ok bool
			current, ok = v[part]
			if !ok {
				return "", fmt.Errorf("key not found: %s", key)
			}
		default:
			return "", fmt.Errorf("invalid key path: %s", key)
		}
	}
	
	return fmt.Sprintf("%v", current), nil
}

func setConfigValue(config interface{}, key string, value string) error {
	parts := strings.Split(key, ".")
	
	switch parts[0] {
	case "repos":
		if len(parts) != 2 {
			return fmt.Errorf("invalid repos key: %s", key)
		}
		return fmt.Errorf("config modification not yet fully implemented")
		
	case "web":
		if len(parts) != 2 {
			return fmt.Errorf("invalid web key: %s", key)
		}
		return fmt.Errorf("config modification not yet fully implemented")
		
	case "cli":
		if len(parts) != 2 {
			return fmt.Errorf("invalid cli key: %s", key)
		}
		return fmt.Errorf("config modification not yet fully implemented")
		
	case "log":
		if len(parts) != 2 {
			return fmt.Errorf("invalid log key: %s", key)
		}
		return fmt.Errorf("config modification not yet fully implemented")
		
	default:
		return fmt.Errorf("unknown config section: %s", parts[0])
	}
}
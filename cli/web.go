package cli

import (
	"flag"
	"log"

	"gitflower/web"
)

func init() {
	Register(&Command{
		Name:        "web",
		Description: "Start the GitFlower web server",
		Run:         runWeb,
	})
}

func runWeb(args []string) error {
	fs := flag.NewFlagSet("web", flag.ExitOnError)
	addr := fs.String("addr", ":8080", "HTTP server address")
	
	if err := fs.Parse(args); err != nil {
		return err
	}

	server, err := web.NewServer()
	if err != nil {
		return err
	}

	log.Printf("Starting GitFlower web server on %s", *addr)
	return server.Start(*addr)
}
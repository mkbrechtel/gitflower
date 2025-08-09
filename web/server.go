package web

import (
	"embed"
	"fmt"
	"html/template"
	"log"
	"net/http"
	"time"

	"gitflower/tree"
)

//go:embed templates/*
var templateFS embed.FS

//go:embed static/*
var staticFS embed.FS

type Server struct {
	store     *tree.Store
	templates *template.Template
}

// Run starts the web server with the given store and configuration
func Run(store *tree.Store, config Config) error {
	templates, err := template.ParseFS(templateFS, "templates/*.html")
	if err != nil {
		return fmt.Errorf("parsing templates: %w", err)
	}

	server := &Server{
		store:     store,
		templates: templates,
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/", server.HandleIndex)
	mux.Handle("/static/", http.FileServer(http.FS(staticFS)))

	httpServer := &http.Server{
		Addr:         config.Address,
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	log.Printf("Starting server on %s", config.Address)
	return httpServer.ListenAndServe()
}

func (s *Server) HandleIndex(w http.ResponseWriter, r *http.Request) {
	store := s.store
	
	var repositories []*tree.Repository
	var scanErrors []string
	
	if store != nil {
		repoList, warnings, err := store.Scan()
		if err != nil {
			log.Printf("Error scanning repositories: %v", err)
			scanErrors = append(scanErrors, err.Error())
		} else {
			repositories = repoList
			scanErrors = warnings
		}
	}
	
	data := struct {
		Time        string
		Repos       []*tree.Repository
		ScanErrors  []string
	}{
		Time:       time.Now().Format("2006-01-02 15:04:05"),
		Repos:      repositories,
		ScanErrors: scanErrors,
	}

	err := s.templates.ExecuteTemplate(w, "index.html", data)
	if err != nil {
		log.Printf("Error rendering template: %v", err)
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
	}
}
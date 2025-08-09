package web

import (
	"embed"
	"html/template"
	"log"
	"net/http"
	"time"

	"gitflower/app"
)

//go:embed templates/*
var templateFS embed.FS

//go:embed static/*
var staticFS embed.FS

type Server struct {
	app       *app.Application
	templates *template.Template
}

func NewServer(application *app.Application) (*Server, error) {
	templates, err := template.ParseFS(templateFS, "templates/*.html")
	if err != nil {
		return nil, err
	}

	return &Server{
		app:       application,
		templates: templates,
	}, nil
}

func (s *Server) HandleIndex(w http.ResponseWriter, r *http.Request) {
	store := s.app.RepoStore()
	
	var repos interface{}
	var scanErrors []string
	
	if store != nil {
		repoList, warnings, err := store.Scan()
		if err != nil {
			log.Printf("Error scanning repositories: %v", err)
			scanErrors = append(scanErrors, err.Error())
		} else {
			repos = repoList
			scanErrors = warnings
		}
	}
	
	data := struct {
		Time        string
		Repos       interface{}
		ScanErrors  []string
		Config      *app.Config
	}{
		Time:       time.Now().Format("2006-01-02 15:04:05"),
		Repos:      repos,
		ScanErrors: scanErrors,
		Config:     s.app.Config(),
	}

	err := s.templates.ExecuteTemplate(w, "index.html", data)
	if err != nil {
		log.Printf("Error rendering template: %v", err)
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
	}
}

func (s *Server) Start(addr string) error {
	mux := http.NewServeMux()
	
	mux.Handle("/static/", http.FileServer(http.FS(staticFS)))
	mux.HandleFunc("/", s.HandleIndex)

	s.app.Logger().Info("GitFlower web server started", "address", addr)
	return http.ListenAndServe(addr, mux)
}
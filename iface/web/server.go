package web

import (
	"embed"
	"html/template"
	"log"
	"net/http"
	"time"

	"gitflower/app"
	"gitflower/repos"
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
	store := s.app.Store
	
	var repositories []*repos.Repository
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
		Repos       []*repos.Repository
		ScanErrors  []string
		Config      *app.Config
	}{
		Time:       time.Now().Format("2006-01-02 15:04:05"),
		Repos:      repositories,
		ScanErrors: scanErrors,
		Config:     s.app.Config,
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

	s.app.Logger.Info("GitFlower web server started", "address", addr)
	return http.ListenAndServe(addr, mux)
}
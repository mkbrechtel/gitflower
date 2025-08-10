package web

import (
	"embed"
	"fmt"
	"html/template"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"gitflower/git"
	"gitflower/tree"
	gogit "github.com/go-git/go-git/v5"
	"github.com/go-git/go-git/v5/plumbing"
	"github.com/go-git/go-git/v5/plumbing/object"
)

//go:embed templates/*
var templateFS embed.FS

//go:embed static/*
var staticFS embed.FS

type Server struct {
	store     *tree.Store
	templates *template.Template
	config    Config
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
		config:    config,
	}

	mux := http.NewServeMux()

	// Apply middleware
	handler := loggingMiddleware(mux)

	// Static files
	mux.Handle("/static/", cacheMiddleware(http.FileServer(http.FS(staticFS))))

	// Main routes
	mux.HandleFunc("/", server.HandleIndex)
	mux.HandleFunc("/repos/", server.HandleRepos)
	mux.HandleFunc("/docs/", server.HandleDocs)

	httpServer := &http.Server{
		Addr:         config.Address,
		Handler:      handler,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	log.Printf("Starting server on %s", config.Address)
	return httpServer.ListenAndServe()
}

func (s *Server) HandleIndex(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		s.Handle404(w, r)
		return
	}

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
		Time       string
		Repos      []*tree.Repository
		ScanErrors []string
	}{
		Time:       time.Now().Format("2006-01-02 15:04:05"),
		Repos:      repositories,
		ScanErrors: scanErrors,
	}

	err := s.templates.ExecuteTemplate(w, "index.html", data)
	if err != nil {
		log.Printf("Error rendering template: %v", err)
		s.Handle500(w, r, err)
	}
}

// HandleRepos handles all repository-related routes
func (s *Server) HandleRepos(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimPrefix(r.URL.Path, "/repos/")

	if path == "" {
		// Repository list
		s.handleRepoList(w, r)
		return
	}

	// Check for Git HTTP protocol operations
	if strings.HasSuffix(path, "/info/refs") {
		s.handleGitInfoRefs(w, r, path)
		return
	}
	if strings.HasSuffix(path, "/git-upload-pack") {
		s.handleGitUploadPack(w, r, path)
		return
	}

	// Parse repository path and subpath
	parts := strings.SplitN(path, "/", 2)
	repoName := parts[0]

	if !strings.HasSuffix(repoName, ".git") {
		// Organization folder view
		s.handleOrgFolder(w, r, path)
		return
	}

	// Repository view
	if len(parts) == 1 {
		// Repository detail page
		s.handleRepoDetail(w, r, repoName)
		return
	}

	// Parse sub-route within repository
	subPath := parts[1]
	subParts := strings.SplitN(subPath, "/", 2)
	action := subParts[0]

	switch action {
	case "tree":
		// File browser: /repos/my-project.git/tree/{ref}/{path}
		if len(subParts) > 1 {
			s.handleFileTree(w, r, repoName, subParts[1])
		} else {
			s.handleFileTree(w, r, repoName, "")
		}
	case "commit":
		// Commit viewing: /repos/my-project.git/commit/{sha}
		if len(subParts) > 1 {
			s.handleCommit(w, r, repoName, subParts[1])
		} else {
			s.Handle404(w, r)
		}
	default:
		s.Handle404(w, r)
	}
}

// HandleDocs handles documentation routes
func (s *Server) HandleDocs(w http.ResponseWriter, r *http.Request) {
	page := strings.TrimPrefix(r.URL.Path, "/docs/")
	if page == "" {
		page = "index"
	}

	// For now, serve a simple documentation page
	data := struct {
		Page string
	}{
		Page: page,
	}

	err := s.templates.ExecuteTemplate(w, "docs.html", data)
	if err != nil {
		log.Printf("Error rendering docs template: %v", err)
		s.Handle404(w, r)
	}
}

func (s *Server) handleRepoList(w http.ResponseWriter, r *http.Request) {
	repos, warnings, err := s.store.Scan()
	if err != nil {
		log.Printf("Error scanning repositories: %v", err)
		s.Handle500(w, r, err)
		return
	}

	data := struct {
		Repos      []*tree.Repository
		ScanErrors []string
	}{
		Repos:      repos,
		ScanErrors: warnings,
	}

	err = s.templates.ExecuteTemplate(w, "repo-list.html", data)
	if err != nil {
		log.Printf("Error rendering repo list template: %v", err)
		s.Handle500(w, r, err)
	}
}

func (s *Server) handleOrgFolder(w http.ResponseWriter, r *http.Request, orgPath string) {
	// List repositories within organization folder
	repos, warnings, err := s.store.Scan()
	if err != nil {
		log.Printf("Error scanning repositories: %v", err)
		s.Handle500(w, r, err)
		return
	}

	// Filter repos by organization path
	var filteredRepos []*tree.Repository
	for _, repo := range repos {
		if strings.HasPrefix(repo.Path, orgPath+"/") {
			filteredRepos = append(filteredRepos, repo)
		}
	}

	data := struct {
		OrgPath    string
		Repos      []*tree.Repository
		ScanErrors []string
	}{
		OrgPath:    orgPath,
		Repos:      filteredRepos,
		ScanErrors: warnings,
	}

	err = s.templates.ExecuteTemplate(w, "org-folder.html", data)
	if err != nil {
		log.Printf("Error rendering org folder template: %v", err)
		s.Handle500(w, r, err)
	}
}

func (s *Server) handleRepoDetail(w http.ResponseWriter, r *http.Request, repoName string) {
	repoPath := filepath.Join(s.store.Directory, repoName)

	// Validate repository exists
	if !git.IsValidRepository(repoPath) {
		s.Handle404(w, r)
		return
	}

	repo, err := git.Open(repoPath)
	if err != nil {
		log.Printf("Error opening repository %s: %v", repoName, err)
		s.Handle500(w, r, err)
		return
	}

	// Get repository info
	head, err := repo.Head()
	if err != nil {
		head = nil // Repository might be empty
	}

	branches, err := repo.Branches()
	if err != nil {
		log.Printf("Error getting branches: %v", err)
	}

	var branchNames []string
	if branches != nil {
		branches.ForEach(func(ref *plumbing.Reference) error {
			branchNames = append(branchNames, ref.Name().Short())
			return nil
		})
	}

	// Get recent commits
	var commits []*object.Commit
	if head != nil {
		commitIter, err := repo.Log(&gogit.LogOptions{
			From: head.Hash(),
		})
		if err == nil {
			count := 0
			commitIter.ForEach(func(c *object.Commit) error {
				if count < 10 {
					commits = append(commits, c)
					count++
				}
				return nil
			})
		}
	}

	data := struct {
		RepoName string
		Head     *plumbing.Reference
		Branches []string
		Commits  []*object.Commit
	}{
		RepoName: repoName,
		Head:     head,
		Branches: branchNames,
		Commits:  commits,
	}

	err = s.templates.ExecuteTemplate(w, "repo-detail.html", data)
	if err != nil {
		log.Printf("Error rendering repo detail template: %v", err)
		s.Handle500(w, r, err)
	}
}

func (s *Server) handleFileTree(w http.ResponseWriter, r *http.Request, repoName string, subPath string) {
	repoPath := filepath.Join(s.store.Directory, repoName)

	if !git.IsValidRepository(repoPath) {
		s.Handle404(w, r)
		return
	}

	repo, err := git.Open(repoPath)
	if err != nil {
		log.Printf("Error opening repository %s: %v", repoName, err)
		s.Handle500(w, r, err)
		return
	}

	// Parse ref and path
	parts := strings.SplitN(subPath, "/", 2)
	ref := "HEAD"
	filePath := ""

	if len(parts) > 0 && parts[0] != "" {
		ref = parts[0]
	}
	if len(parts) > 1 {
		filePath = parts[1]
	}

	// Resolve ref to commit
	hash, err := repo.ResolveRevision(plumbing.Revision(ref))
	if err != nil {
		log.Printf("Error resolving ref %s: %v", ref, err)
		s.Handle404(w, r)
		return
	}

	commit, err := repo.CommitObject(*hash)
	if err != nil {
		log.Printf("Error getting commit: %v", err)
		s.Handle500(w, r, err)
		return
	}

	tree, err := commit.Tree()
	if err != nil {
		log.Printf("Error getting tree: %v", err)
		s.Handle500(w, r, err)
		return
	}

	// Navigate to the requested path
	if filePath != "" {
		entry, err := tree.FindEntry(filePath)
		if err != nil {
			s.Handle404(w, r)
			return
		}

		if entry.Mode.IsFile() {
			// Display file contents
			file, err := tree.File(filePath)
			if err != nil {
				s.Handle500(w, r, err)
				return
			}

			content, err := file.Contents()
			if err != nil {
				s.Handle500(w, r, err)
				return
			}

			data := struct {
				RepoName string
				Ref      string
				Path     string
				Content  string
				IsBinary bool
			}{
				RepoName: repoName,
				Ref:      ref,
				Path:     filePath,
				Content:  content,
				IsBinary: isBinary(file),
			}

			err = s.templates.ExecuteTemplate(w, "file-view.html", data)
			if err != nil {
				log.Printf("Error rendering file view template: %v", err)
				s.Handle500(w, r, err)
			}
			return
		}

		// Navigate to subdirectory
		tree, err = tree.Tree(filePath)
		if err != nil {
			s.Handle404(w, r)
			return
		}
	}

	// Display directory contents
	var entries []object.TreeEntry
	for _, entry := range tree.Entries {
		entries = append(entries, entry)
	}

	data := struct {
		RepoName string
		Ref      string
		Path     string
		Entries  []object.TreeEntry
	}{
		RepoName: repoName,
		Ref:      ref,
		Path:     filePath,
		Entries:  entries,
	}

	err = s.templates.ExecuteTemplate(w, "tree-view.html", data)
	if err != nil {
		log.Printf("Error rendering tree view template: %v", err)
		s.Handle500(w, r, err)
	}
}

func (s *Server) handleCommit(w http.ResponseWriter, r *http.Request, repoName string, sha string) {
	repoPath := filepath.Join(s.store.Directory, repoName)

	if !git.IsValidRepository(repoPath) {
		s.Handle404(w, r)
		return
	}

	repo, err := git.Open(repoPath)
	if err != nil {
		log.Printf("Error opening repository %s: %v", repoName, err)
		s.Handle500(w, r, err)
		return
	}

	hash := plumbing.NewHash(sha)
	commit, err := repo.CommitObject(hash)
	if err != nil {
		log.Printf("Error getting commit %s: %v", sha, err)
		s.Handle404(w, r)
		return
	}

	// Get parent commit for diff
	var parent *object.Commit
	if len(commit.ParentHashes) > 0 {
		parent, _ = repo.CommitObject(commit.ParentHashes[0])
	}

	// Get patch
	var patch string
	if parent != nil {
		patchObj, err := parent.Patch(commit)
		if err == nil {
			patch = patchObj.String()
		}
	}

	data := struct {
		RepoName string
		Commit   *object.Commit
		Patch    string
	}{
		RepoName: repoName,
		Commit:   commit,
		Patch:    patch,
	}

	err = s.templates.ExecuteTemplate(w, "commit-view.html", data)
	if err != nil {
		log.Printf("Error rendering commit view template: %v", err)
		s.Handle500(w, r, err)
	}
}

// Git HTTP protocol handlers
func (s *Server) handleGitInfoRefs(w http.ResponseWriter, r *http.Request, path string) {
	repoName := strings.TrimSuffix(path, "/info/refs")
	repoPath := filepath.Join(s.store.Directory, repoName)

	if !git.IsValidRepository(repoPath) {
		s.Handle404(w, r)
		return
	}

	service := r.URL.Query().Get("service")
	if service != "git-upload-pack" {
		// Dumb HTTP protocol
		infoRefsPath := filepath.Join(repoPath, "info", "refs")
		data, err := os.ReadFile(infoRefsPath)
		if err != nil {
			s.Handle404(w, r)
			return
		}
		w.Header().Set("Content-Type", "text/plain")
		w.Write(data)
		return
	}

	// Smart HTTP protocol
	w.Header().Set("Content-Type", fmt.Sprintf("application/x-%s-advertisement", service))
	w.WriteHeader(http.StatusOK)

	// Write service header
	pkt := fmt.Sprintf("# service=%s\n", service)
	fmt.Fprintf(w, "%04x%s", len(pkt)+4, pkt)
	w.Write([]byte("0000"))

	// For now, use simple reference listing
	repo, err := gogit.PlainOpen(repoPath)
	if err != nil {
		log.Printf("Error opening repository: %v", err)
		return
	}

	// List references
	refs, err := repo.References()
	if err != nil {
		log.Printf("Error getting references: %v", err)
		return
	}

	// Output references in pkt-line format
	refs.ForEach(func(ref *plumbing.Reference) error {
		line := fmt.Sprintf("%s %s\n", ref.Hash().String(), ref.Name())
		fmt.Fprintf(w, "%04x%s", len(line)+4, line)
		return nil
	})
	w.Write([]byte("0000"))
}

func (s *Server) handleGitUploadPack(w http.ResponseWriter, r *http.Request, path string) {
	repoName := strings.TrimSuffix(path, "/git-upload-pack")
	repoPath := filepath.Join(s.store.Directory, repoName)

	if !git.IsValidRepository(repoPath) {
		s.Handle404(w, r)
		return
	}

	// For now, return a simple error message
	// Full Git HTTP protocol implementation would require more complex handling
	w.Header().Set("Content-Type", "text/plain")
	w.WriteHeader(http.StatusNotImplemented)
	w.Write([]byte("Git HTTP protocol not fully implemented. Please use SSH for cloning."))
}

// Error handlers
func (s *Server) Handle404(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusNotFound)
	data := struct {
		Path string
	}{
		Path: r.URL.Path,
	}

	err := s.templates.ExecuteTemplate(w, "404.html", data)
	if err != nil {
		log.Printf("Error rendering 404 template: %v", err)
		http.Error(w, "404 - Page Not Found", http.StatusNotFound)
	}
}

func (s *Server) Handle500(w http.ResponseWriter, r *http.Request, err error) {
	w.WriteHeader(http.StatusInternalServerError)
	data := struct {
		Error string
	}{
		Error: err.Error(),
	}

	tmplErr := s.templates.ExecuteTemplate(w, "500.html", data)
	if tmplErr != nil {
		log.Printf("Error rendering 500 template: %v", tmplErr)
		http.Error(w, "500 - Internal Server Error", http.StatusInternalServerError)
	}
}

// Middleware
func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()

		// Create a response writer wrapper to capture status code
		wrapped := &responseWriter{
			ResponseWriter: w,
			statusCode:     http.StatusOK,
		}

		next.ServeHTTP(wrapped, r)

		duration := time.Since(start)
		log.Printf("%s %s %s - %d (%v)", r.RemoteAddr, r.Method, r.URL.Path, wrapped.statusCode, duration)
	})
}

func cacheMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Set cache headers for static assets
		if strings.HasPrefix(r.URL.Path, "/static/") {
			w.Header().Set("Cache-Control", "public, max-age=3600")
		}
		next.ServeHTTP(w, r)
	})
}

// responseWriter wraps http.ResponseWriter to capture status code
type responseWriter struct {
	http.ResponseWriter
	statusCode int
}

func (rw *responseWriter) WriteHeader(code int) {
	rw.statusCode = code
	rw.ResponseWriter.WriteHeader(code)
}

// isBinary checks if a file is binary
func isBinary(file *object.File) bool {
	bin, _ := file.IsBinary()
	return bin
}

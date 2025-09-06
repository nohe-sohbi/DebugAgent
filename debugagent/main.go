package main

import (
	"debugagent/config"
	"debugagent/logging"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"

	"github.com/sirupsen/logrus"
)

// AnalyzeRequest defines the structure for the API request.
type AnalyzeRequest struct {
	ProjectPath string `json:"project_path"`
	Question    string `json:"question"`
}

// AnalyzeResponse defines the structure for the API response.
type AnalyzeResponse struct {
	Answer string `json:"answer"`
}

func analyzeHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Only POST method is allowed", http.StatusMethodNotAllowed)
		return
	}

	// Parse the multipart form data
	err := r.ParseMultipartForm(32 << 20) // 32MB max memory
	if err != nil {
		http.Error(w, "Error parsing multipart form", http.StatusBadRequest)
		return
	}

	// Get the question from the form data
	question := r.FormValue("question")
	if question == "" {
		http.Error(w, "Missing 'question' field", http.StatusBadRequest)
		return
	}

	// Create a temporary directory to store the uploaded files
	tempDir, err := os.MkdirTemp("", "uploaded-project-")
	if err != nil {
		http.Error(w, "Error creating temporary directory", http.StatusInternalServerError)
		return
	}
	defer os.RemoveAll(tempDir)

	// Get the files from the form data
	files := r.MultipartForm.File["files"]
	if len(files) == 0 {
		http.Error(w, "No files uploaded", http.StatusBadRequest)
		return
	}

	for _, fileHeader := range files {
		// Open the uploaded file
		file, err := fileHeader.Open()
		if err != nil {
			http.Error(w, "Error opening uploaded file", http.StatusInternalServerError)
			return
		}
		defer file.Close()

		// Create the file in the temporary directory
		destPath := filepath.Join(tempDir, fileHeader.Filename)
		destFile, err := os.Create(destPath)
		if err != nil {
			http.Error(w, "Error creating file in temporary directory", http.StatusInternalServerError)
			return
		}
		defer destFile.Close()

		// Copy the file content
		if _, err := io.Copy(destFile, file); err != nil {
			http.Error(w, "Error copying file content", http.StatusInternalServerError)
			return
		}
	}

	// --- Create and Run Analysis Engine ---
	req := AnalyzeRequest{
		ProjectPath: tempDir,
		Question:    question,
	}

	engine, err := NewAnalysisEngine(req)
	if err != nil {
		http.Error(w, fmt.Sprintf("Error initializing analysis engine: %v", err), http.StatusInternalServerError)
		return
	}

	finalAnswer, err := engine.RunAnalysis()
	if err != nil {
		http.Error(w, fmt.Sprintf("Error during analysis: %v", err), http.StatusInternalServerError)
		return
	}

	// --- Send Response ---
	resp := AnalyzeResponse{
		Answer: finalAnswer,
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

func healthCheckHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func main() {
	if err := config.LoadConfig(); err != nil {
		logrus.Fatalf("Error loading configuration: %v", err)
	}

	logging.InitLogger()

	http.HandleFunc("/analyze", analyzeHandler)
	http.HandleFunc("/health", healthCheckHandler)

	// Serve the frontend
	fs := http.FileServer(http.Dir("./static"))
	http.Handle("/", fs)

	port := fmt.Sprintf(":%d", config.AppConfig.Server.Port)
	logrus.Infof("Starting server on port %s...", port)
	if err := http.ListenAndServe(port, nil); err != nil {
		logrus.Fatalf("Failed to start server: %v", err)
	}
}

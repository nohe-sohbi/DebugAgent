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

// AnalyzeResponse defines the structure for the API response.
type AnalyzeResponse struct {
	Answer string `json:"answer"`
}

// ProgressEvent defines the structure for streaming progress events
type ProgressEvent struct {
	Type      string `json:"type"`      // "progress", "step", "result", "error"
	Step      string `json:"step"`      // Current step description
	Message   string `json:"message"`   // Progress message
	Iteration int    `json:"iteration"` // Current iteration number
	Total     int    `json:"total"`     // Total iterations
	Data      string `json:"data"`      // Additional data (final answer, etc.)
}

// CORS middleware to handle cross-origin requests
func corsMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// Set CORS headers
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With, Cache-Control")
		w.Header().Set("Access-Control-Max-Age", "86400")

		// Handle preflight OPTIONS request
		if r.Method == "OPTIONS" {
			w.WriteHeader(http.StatusOK)
			return
		}

		// Call the next handler
		next(w, r)
	}
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
		// The client side sends relative paths, so we need to create the directory structure
		destPath := filepath.Join(tempDir, fileHeader.Filename)
		if err := os.MkdirAll(filepath.Dir(destPath), os.ModePerm); err != nil {
			http.Error(w, "Error creating directory structure", http.StatusInternalServerError)
			return
		}

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
	// The AnalyzeRequest struct is defined in engine.go, so we use it here
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

func analyzeStreamHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Only POST method is allowed", http.StatusMethodNotAllowed)
		return
	}

	// Set headers for Server-Sent Events
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no") // Disable nginx buffering

	// Parse the multipart form data
	err := r.ParseMultipartForm(32 << 20) // 32MB max memory
	if err != nil {
		sendSSEError(w, "Error parsing multipart form")
		return
	}

	// Get the question from the form data
	question := r.FormValue("question")
	if question == "" {
		sendSSEError(w, "Missing 'question' field")
		return
	}

	// Create a temporary directory to store the uploaded files
	tempDir, err := os.MkdirTemp("", "uploaded-project-")
	if err != nil {
		sendSSEError(w, "Error creating temporary directory")
		return
	}
	defer os.RemoveAll(tempDir)

	// Get the files from the form data
	files := r.MultipartForm.File["files"]
	if len(files) == 0 {
		sendSSEError(w, "No files uploaded")
		return
	}

	// Send initial progress
	sendSSEEvent(w, ProgressEvent{
		Type:    "progress",
		Step:    "upload",
		Message: fmt.Sprintf("Processing %d uploaded files...", len(files)),
	})

	// Process uploaded files
	for _, fileHeader := range files {
		// Open the uploaded file
		file, err := fileHeader.Open()
		if err != nil {
			sendSSEError(w, "Error opening uploaded file")
			return
		}
		defer file.Close()

		// Create the file in the temporary directory
		destPath := filepath.Join(tempDir, fileHeader.Filename)
		if err := os.MkdirAll(filepath.Dir(destPath), os.ModePerm); err != nil {
			sendSSEError(w, "Error creating directory structure")
			return
		}

		destFile, err := os.Create(destPath)
		if err != nil {
			sendSSEError(w, "Error creating file in temporary directory")
			return
		}
		defer destFile.Close()

		// Copy the file content
		if _, err := io.Copy(destFile, file); err != nil {
			sendSSEError(w, "Error copying file content")
			return
		}
	}

	// Send progress update
	sendSSEEvent(w, ProgressEvent{
		Type:    "progress",
		Step:    "init",
		Message: "Initializing analysis engine...",
	})

	// Create and run streaming analysis
	req := AnalyzeRequest{
		ProjectPath: tempDir,
		Question:    question,
	}

	engine, err := NewStreamingAnalysisEngine(req)
	if err != nil {
		sendSSEError(w, fmt.Sprintf("Error initializing analysis engine: %v", err))
		return
	}

	// Run the streaming analysis
	engine.RunStreamingAnalysis(w)
}

// SSE helper functions
func sendSSEEvent(w http.ResponseWriter, event ProgressEvent) {
	data, _ := json.Marshal(event)
	fmt.Fprintf(w, "data: %s\n\n", data)
	if f, ok := w.(http.Flusher); ok {
		f.Flush()
	}
}

func sendSSEError(w http.ResponseWriter, message string) {
	sendSSEEvent(w, ProgressEvent{
		Type:    "error",
		Message: message,
	})
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

	http.HandleFunc("/analyze", corsMiddleware(analyzeHandler))
	http.HandleFunc("/analyze-stream", corsMiddleware(analyzeStreamHandler))
	http.HandleFunc("/health", corsMiddleware(healthCheckHandler))

	// Serve the frontend
	fs := http.FileServer(http.Dir("./static"))
	http.Handle("/", fs)

	port := fmt.Sprintf(":%d", config.AppConfig.Server.Port)
	logrus.Infof("Starting server on port %s...", port)
	if err := http.ListenAndServe(port, nil); err != nil {
		logrus.Fatalf("Failed to start server: %v", err)
	}
}

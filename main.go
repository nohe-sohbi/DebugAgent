package main

import (
	"debugagent/config"
	"debugagent/logging"
	"encoding/json"
	"fmt"
	"net/http"
	"os"

	"github.com/sirupsen/logrus"
)


// AnalyzeRequest définit la structure pour la requête de l'API.
type AnalyzeRequest struct {
	ProjectPath string `json:"project_path"`
	Question    string `json:"question"`
}

// AnalyzeResponse définit la structure pour la réponse de l'API.
type AnalyzeResponse struct {
	Answer string `json:"answer"`
}


func analyzeHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Only POST method is allowed", http.StatusMethodNotAllowed)
		return
	}

	var req AnalyzeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Error decoding JSON request", http.StatusBadRequest)
		return
	}

	// --- Project Path Validation ---
	projInfo, err := os.Stat(req.ProjectPath)
	if os.IsNotExist(err) || !projInfo.IsDir() {
		http.Error(w, fmt.Sprintf("Project path '%s' is not a valid directory.", req.ProjectPath), http.StatusBadRequest)
		return
	}

	// --- Create and Run Analysis Engine ---
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

func main() {
	if err := config.LoadConfig(); err != nil {
		logrus.Fatalf("Error loading configuration: %v", err)
	}

	logging.InitLogger()

	http.HandleFunc("/analyze", analyzeHandler)

	port := fmt.Sprintf(":%d", config.AppConfig.Server.Port)
	logrus.Infof("Starting server on port %s...", port)
	if err := http.ListenAndServe(port, nil); err != nil {
		logrus.Fatalf("Failed to start server: %v", err)
	}
}

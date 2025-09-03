package main

import (
	"debugagent/config"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func setupKnowledgeBase(t *testing.T) *KnowledgeBase {
	// Create a temporary directory for the project path
	projectPath, err := os.MkdirTemp("", "testproject")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	t.Cleanup(func() { os.RemoveAll(projectPath) })

	// Minimal config for testing
	config.AppConfig = &config.Config{
		Analysis: config.AnalysisConfig{
			MaxPromptLength: 8000,
		},
	}

	return NewKnowledgeBase(projectPath)
}

func TestAddFileContent(t *testing.T) {
	kb := setupKnowledgeBase(t)
	absFilePath := filepath.Join(kb.ProjectPath, "test.txt")
	content := "Hello, World!"

	kb.AddFileContent(absFilePath, content)

	relPath, _ := kb.getRelativePath(absFilePath)
	if got, ok := kb.FileContents[relPath]; !ok || got != content {
		t.Errorf("AddFileContent() failed, expected '%s', got '%s'", content, got)
	}
}

func TestGetContextSummary(t *testing.T) {
	kb := setupKnowledgeBase(t)
	kb.SetProjectType("Go Backend")
	kb.AddFileContent(filepath.Join(kb.ProjectPath, "main.go"), "package main\n\nfunc main() {}")
	kb.AddNote("This is a test note.")
	kb.AddHistory("Initial analysis complete.")

	summary := kb.getContextSummary("What is the entry point?", 1000)

	if !strings.Contains(summary, "Problème utilisateur: \"What is the entry point?\"") {
		t.Error("getContextSummary() did not include the user problem")
	}
	if !strings.Contains(summary, "Type: Go Backend") {
		t.Error("getContextSummary() did not include the project type")
	}
	if !strings.Contains(summary, "- `main.go`: package main  func main() {}...") {
		t.Error("getContextSummary() did not include the file content")
	}
	if !strings.Contains(summary, "- This is a test note.") {
		t.Error("getContextSummary() did not include the analysis note")
	}
	if !strings.Contains(summary, "- Initial analysis complete.") {
		t.Error("getContextSummary() did not include the history")
	}
}

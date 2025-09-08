package main

import (
	"debugagent/config"
	"os"
	"path/filepath"
	"testing"
)

func setupFileResolverTest(t *testing.T) (*FileResolver, string) {
	// Create a temporary directory for testing
	tempDir, err := os.MkdirTemp("", "file-resolver-test")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	t.Cleanup(func() { os.RemoveAll(tempDir) })

	// Set up minimal config
	config.AppConfig = &config.Config{
		Analysis: config.AnalysisConfig{
			MaxFileRetryAttempts: 2,
		},
	}

	// Create test files
	testFiles := []string{
		"composer.json",
		"package.json",
		"go.mod",
		"README.md",
	}

	for _, file := range testFiles {
		filePath := filepath.Join(tempDir, file)
		if err := os.WriteFile(filePath, []byte("test content"), 0644); err != nil {
			t.Fatalf("Failed to create test file %s: %v", file, err)
		}
	}

	kb := NewKnowledgeBase(tempDir)
	resolver := NewFileResolver(tempDir, kb)

	return resolver, tempDir
}

func TestResolveFile_ExactMatch(t *testing.T) {
	resolver, _ := setupFileResolverTest(t)

	// Test exact file match
	resolved, err := resolver.ResolveFile("composer.json")
	if err != nil {
		t.Errorf("Expected no error, got: %v", err)
	}
	if resolved != "composer.json" {
		t.Errorf("Expected 'composer.json', got: %s", resolved)
	}
}

func TestResolveFile_Alternative(t *testing.T) {
	resolver, _ := setupFileResolverTest(t)

	// Test alternative file resolution
	resolved, err := resolver.ResolveFile("composer-info.php")
	if err != nil {
		t.Errorf("Expected no error, got: %v", err)
	}
	if resolved != "composer.json" {
		t.Errorf("Expected 'composer.json' as alternative, got: %s", resolved)
	}
}

func TestResolveFile_NotFound(t *testing.T) {
	resolver, _ := setupFileResolverTest(t)

	// Test file not found
	_, err := resolver.ResolveFile("nonexistent.txt")
	if err == nil {
		t.Error("Expected error for nonexistent file, got nil")
	}
}

func TestResolveFile_RetryLimit(t *testing.T) {
	resolver, _ := setupFileResolverTest(t)

	// Attempt the same nonexistent file multiple times
	for i := 0; i < 3; i++ {
		_, err := resolver.ResolveFile("nonexistent.txt")
		if err == nil {
			t.Errorf("Expected error on attempt %d", i+1)
		}
	}

	// Should exceed retry limit now
	_, err := resolver.ResolveFile("nonexistent.txt")
	if err == nil {
		t.Error("Expected retry limit exceeded error")
	}
	if !resolver.kb.IsFileAttemptExceeded("nonexistent.txt", 2) {
		t.Error("Expected file attempt to be marked as exceeded")
	}
}

func TestDiscoverProjectFiles(t *testing.T) {
	resolver, _ := setupFileResolverTest(t)

	// Discover files
	resolver.DiscoverProjectFiles()

	// Check that dependency files were found
	if len(resolver.kb.DependencyFiles) == 0 {
		t.Error("Expected dependency files to be discovered")
	}

	// Check that available files were recorded
	if len(resolver.kb.AvailableFiles) == 0 {
		t.Error("Expected available files to be recorded")
	}

	// Check specific dependency types
	if _, exists := resolver.kb.DependencyFiles["composer"]; !exists {
		t.Error("Expected composer dependency to be found")
	}
	if _, exists := resolver.kb.DependencyFiles["npm"]; !exists {
		t.Error("Expected npm dependency to be found")
	}
	if _, exists := resolver.kb.DependencyFiles["go"]; !exists {
		t.Error("Expected go dependency to be found")
	}
}

func TestGetAvailableAlternatives(t *testing.T) {
	resolver, _ := setupFileResolverTest(t)

	// Get alternatives for composer
	alternatives := resolver.GetAvailableAlternatives("composer")
	if len(alternatives) == 0 {
		t.Error("Expected composer alternatives to be found")
	}

	found := false
	for _, alt := range alternatives {
		if alt == "composer.json" {
			found = true
			break
		}
	}
	if !found {
		t.Error("Expected composer.json to be in alternatives")
	}
}

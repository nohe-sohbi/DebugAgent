package files

import (
	"debugagent/config"
	"debugagent/internal/models"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/sirupsen/logrus"
)

// FileResolver handles intelligent file resolution and fallback strategies.
type FileResolver struct {
	projectPath      string
	kb               *models.KnowledgeBase
	maxRetryAttempts int
}

// CommonConfigFiles defines common configuration files to look for.
var CommonConfigFiles = []string{
	"README.md", "README.txt", "README.rst",
	"LICENSE", "LICENSE.txt", "LICENSE.md",
	"CHANGELOG.md", "CHANGELOG.txt",
	"docker-compose.yml", "docker-compose.yaml", "Dockerfile",
	".gitignore", ".env", ".env.example",
	"Makefile", "makefile",
}

// NewFileResolver creates a new FileResolver instance.
func NewFileResolver(projectPath string, kb *models.KnowledgeBase) *FileResolver {
	maxRetryAttempts := 3 // Default value
	if config.AppConfig != nil && config.AppConfig.Analysis.MaxFileRetryAttempts > 0 {
		maxRetryAttempts = config.AppConfig.Analysis.MaxFileRetryAttempts
	}

	return &FileResolver{
		projectPath:      projectPath,
		kb:               kb,
		maxRetryAttempts: maxRetryAttempts,
	}
}

// ResolveFile attempts to find the best available file for a given request.
func (fr *FileResolver) ResolveFile(requestedFile string) (string, error) {
	// Check if this file has been attempted too many times
	if fr.kb.IsFileAttemptExceeded(requestedFile, fr.maxRetryAttempts) {
		return "", fmt.Errorf("file '%s' has exceeded maximum retry attempts (%d)", requestedFile, fr.maxRetryAttempts)
	}

	// First, try the exact requested file
	fullPath := filepath.Join(fr.projectPath, requestedFile)
	if fr.fileExists(fullPath) {
		fr.kb.AddAvailableFile(requestedFile)
		return requestedFile, nil
	}

	// If exact file doesn't exist, try to find alternatives
	alternatives := fr.findAlternatives(requestedFile)
	for _, alt := range alternatives {
		altPath := filepath.Join(fr.projectPath, alt)
		if fr.fileExists(altPath) {
			logrus.Infof("Found alternative for '%s': '%s'", requestedFile, alt)
			fr.kb.AddAvailableFile(alt)
			return alt, nil
		}
	}

	// No alternatives found, record the failure
	fr.kb.AddFailedFileAttempt(requestedFile)
	return "", fmt.Errorf("file '%s' not found and no suitable alternatives available", requestedFile)
}

// findAlternatives suggests alternative files based on the requested file.
func (fr *FileResolver) findAlternatives(requestedFile string) []string {
	var alternatives []string

	// Handle specific known problematic files
	switch strings.ToLower(requestedFile) {
	case "composer-info.php":
		alternatives = append(alternatives, models.DependencyFileMapping["composer"]...)
	case "package-info.json":
		alternatives = append(alternatives, models.DependencyFileMapping["npm"]...)
	case "requirements-info.txt":
		alternatives = append(alternatives, models.DependencyFileMapping["python"]...)
	}

	// Try to infer file type from extension or name
	if strings.Contains(strings.ToLower(requestedFile), "composer") {
		alternatives = append(alternatives, models.DependencyFileMapping["composer"]...)
	}
	if strings.Contains(strings.ToLower(requestedFile), "package") {
		alternatives = append(alternatives, models.DependencyFileMapping["npm"]...)
	}
	if strings.Contains(strings.ToLower(requestedFile), "requirements") {
		alternatives = append(alternatives, models.DependencyFileMapping["python"]...)
	}

	// Add project-type specific alternatives
	projectType := strings.ToLower(fr.kb.ProjectType)
	if strings.Contains(projectType, "go") {
		alternatives = append(alternatives, models.DependencyFileMapping["go"]...)
	}
	if strings.Contains(projectType, "node") || strings.Contains(projectType, "react") || strings.Contains(projectType, "javascript") {
		alternatives = append(alternatives, models.DependencyFileMapping["npm"]...)
	}
	if strings.Contains(projectType, "python") {
		alternatives = append(alternatives, models.DependencyFileMapping["python"]...)
	}

	// Remove duplicates
	return fr.removeDuplicates(alternatives)
}

// DiscoverProjectFiles scans the project for available dependency and config files.
func (fr *FileResolver) DiscoverProjectFiles() {
	logrus.Info("Discovering available project files...")

	// Check for dependency files
	for depType, files := range models.DependencyFileMapping {
		for _, file := range files {
			fullPath := filepath.Join(fr.projectPath, file)
			if fr.fileExists(fullPath) {
				fr.kb.AddDependencyFile(depType, file)
				fr.kb.AddAvailableFile(file)
			}
		}
	}

	// Check for common config files
	for _, file := range CommonConfigFiles {
		fullPath := filepath.Join(fr.projectPath, file)
		if fr.fileExists(fullPath) {
			fr.kb.AddAvailableFile(file)
		}
	}

	logrus.Infof("File discovery complete. Found %d available files", len(fr.kb.AvailableFiles))
}

// fileExists checks if a file exists and is readable.
func (fr *FileResolver) fileExists(filePath string) bool {
	info, err := os.Stat(filePath)
	if err != nil {
		return false
	}
	return !info.IsDir()
}

// removeDuplicates removes duplicate strings from a slice.
func (fr *FileResolver) removeDuplicates(slice []string) []string {
	keys := make(map[string]bool)
	var result []string

	for _, item := range slice {
		if !keys[item] {
			keys[item] = true
			result = append(result, item)
		}
	}
	return result
}

// GetAvailableAlternatives returns a list of available alternatives for a given file type.
func (fr *FileResolver) GetAvailableAlternatives(fileType string) []string {
	var alternatives []string

	if files, exists := models.DependencyFileMapping[fileType]; exists {
		for _, file := range files {
			fullPath := filepath.Join(fr.projectPath, file)
			if fr.fileExists(fullPath) {
				alternatives = append(alternatives, file)
			}
		}
	}

	return alternatives
}

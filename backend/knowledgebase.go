package main

import (
	"encoding/json"
	"fmt"
	"path/filepath"
	"strings"
	"sync"

	"github.com/sirupsen/logrus"
)

// KnowledgeBase structure pour stocker les informations collectées pendant l'analyse.
type KnowledgeBase struct {
	ProjectPath        string
	ProjectStructure   map[string]interface{}
	ProjectType        string
	ReadmeContent      string
	FileContents       map[string]string
	AnalysisNotes      []string
	ExplorationPlan    []string
	ExplorationHistory []string
	FailedFileAttempts map[string]int    // Track failed file read attempts with retry count
	AvailableFiles     []string          // Track files that exist and can be read
	DependencyFiles    map[string]string // Map dependency types to found files
	mu                 sync.Mutex        // Pour gérer l'accès concurrentiel
}

// NewKnowledgeBase crée une nouvelle instance de KnowledgeBase.
func NewKnowledgeBase(projectPath string) *KnowledgeBase {
	absPath, err := filepath.Abs(projectPath)
	if err != nil {
		logrus.Warnf("Could not resolve absolute path for %s: %v", projectPath, err)
		absPath = projectPath
	}

	return &KnowledgeBase{
		ProjectPath:        absPath,
		ProjectStructure:   make(map[string]interface{}),
		ProjectType:        "Inconnu",
		FileContents:       make(map[string]string),
		AnalysisNotes:      []string{},
		ExplorationPlan:    []string{},
		ExplorationHistory: []string{},
		FailedFileAttempts: make(map[string]int),
		AvailableFiles:     []string{},
		DependencyFiles:    make(map[string]string),
	}
}

// getRelativePath convertit un chemin absolu en chemin relatif au projet.
func (kb *KnowledgeBase) getRelativePath(absFilepath string) (string, error) {
	return filepath.Rel(kb.ProjectPath, absFilepath)
}


// AddFileContent ajoute le contenu d'un fichier à la base de connaissances.
func (kb *KnowledgeBase) AddFileContent(absFilepath string, content string) {
	kb.mu.Lock()
	defer kb.mu.Unlock()

	relPath, err := kb.getRelativePath(absFilepath)
	if err != nil {
		logrus.Warnf("Could not get relative path for %s: %v. Using absolute path.", absFilepath, err)
		relPath = absFilepath
	}

	kb.FileContents[relPath] = content
	logrus.Infof("Content added/updated for '%s'", relPath)
}

// AddNote ajoute une note d'analyse.
func (kb *KnowledgeBase) AddNote(note string) {
	kb.mu.Lock()
	defer kb.mu.Unlock()

	// Éviter les notes dupliquées consécutives
	if len(kb.AnalysisNotes) == 0 || kb.AnalysisNotes[len(kb.AnalysisNotes)-1] != note {
		kb.AnalysisNotes = append(kb.AnalysisNotes, note)
		logrus.Debugf("Note added: %s...", note[:min(100, len(note))])
	}
}

// AddHistory ajoute une action à l'historique.
func (kb *KnowledgeBase) AddHistory(actionDescription string) {
	kb.mu.Lock()
	defer kb.mu.Unlock()

	// Éviter les entrées d'historique dupliquées consécutives
	if len(kb.ExplorationHistory) == 0 || kb.ExplorationHistory[len(kb.ExplorationHistory)-1] != actionDescription {
		kb.ExplorationHistory = append(kb.ExplorationHistory, actionDescription)
		logrus.Debugf("History added: %s", actionDescription)
	}
}

// SetProjectType met à jour le type de projet.
func (kb *KnowledgeBase) SetProjectType(pType string) {
	kb.mu.Lock()
	defer kb.mu.Unlock()

	if pType != "" && kb.ProjectType != pType {
		kb.ProjectType = pType
		logrus.Infof("Project type updated: %s", pType)
	}
}

// AddFailedFileAttempt tracks a failed file read attempt.
func (kb *KnowledgeBase) AddFailedFileAttempt(filePath string) {
	kb.mu.Lock()
	defer kb.mu.Unlock()

	kb.FailedFileAttempts[filePath]++
	logrus.Debugf("Failed file attempt recorded for '%s' (attempt #%d)", filePath, kb.FailedFileAttempts[filePath])
}

// IsFileAttemptExceeded checks if a file has been attempted too many times.
func (kb *KnowledgeBase) IsFileAttemptExceeded(filePath string, maxAttempts int) bool {
	kb.mu.Lock()
	defer kb.mu.Unlock()

	return kb.FailedFileAttempts[filePath] >= maxAttempts
}

// AddAvailableFile tracks a file that exists and can be read.
func (kb *KnowledgeBase) AddAvailableFile(filePath string) {
	kb.mu.Lock()
	defer kb.mu.Unlock()

	// Avoid duplicates
	for _, existing := range kb.AvailableFiles {
		if existing == filePath {
			return
		}
	}
	kb.AvailableFiles = append(kb.AvailableFiles, filePath)
	logrus.Debugf("Available file recorded: '%s'", filePath)
}

// AddDependencyFile maps a dependency type to a found file.
func (kb *KnowledgeBase) AddDependencyFile(depType, filePath string) {
	kb.mu.Lock()
	defer kb.mu.Unlock()

	kb.DependencyFiles[depType] = filePath
	logrus.Infof("Dependency file found: %s -> %s", depType, filePath)
}


func (kb *KnowledgeBase) getContextSummary(userProblem string, maxPromptLength int) string {
	var summary strings.Builder

	summary.WriteString(fmt.Sprintf("Problème utilisateur: \"%s\"\n", userProblem))
	summary.WriteString(fmt.Sprintf("Projet: %s (Type: %s)\n", filepath.Base(kb.ProjectPath), kb.ProjectType))

	if kb.ProjectStructure != nil {
		structureBytes, err := json.MarshalIndent(kb.ProjectStructure, "", "  ")
		if err == nil {
			structureStr := string(structureBytes)
			maxStructureLen := 1800
			if len(structureStr) > maxStructureLen {
				structureStr = structureStr[:maxStructureLen] + "\n...(structure tronquée)"
			}
			summary.WriteString(fmt.Sprintf("\nStructure Projet (partielle):\n```json\n%s\n```\n", structureStr))
		}
	}

	summary.WriteString("\nFichiers Lus (Extraits):\n")
	if len(kb.FileContents) == 0 {
		summary.WriteString("(Aucun)\n")
	} else {
		count := 0
		for path, content := range kb.FileContents {
			excerpt := strings.ReplaceAll(strings.ReplaceAll(content, "`", ""), "\n", " ")
			if len(excerpt) > 80 {
				excerpt = excerpt[:80]
			}
			summary.WriteString(fmt.Sprintf("- `%s`: %s...\n", path, excerpt))
			count++
			if count >= 5 {
				summary.WriteString(fmt.Sprintf("... et %d autres fichiers lus.\n", len(kb.FileContents)-count))
				break
			}
		}
	}

	// Add information about failed file attempts
	summary.WriteString("\nFichiers Non Disponibles (éviter de les redemander):\n")
	if len(kb.FailedFileAttempts) == 0 {
		summary.WriteString("(Aucun)\n")
	} else {
		for filePath, attempts := range kb.FailedFileAttempts {
			summary.WriteString(fmt.Sprintf("- %s (tenté %d fois)\n", filePath, attempts))
		}
	}

	// Add information about available dependency files
	summary.WriteString("\nFichiers de Dépendances Disponibles:\n")
	if len(kb.DependencyFiles) == 0 {
		summary.WriteString("(Aucun détecté)\n")
	} else {
		for depType, filePath := range kb.DependencyFiles {
			summary.WriteString(fmt.Sprintf("- %s: %s\n", depType, filePath))
		}
	}

	summary.WriteString("\nHistorique/Notes Récentes:\n")
	combinedInfo := append(kb.AnalysisNotes, kb.ExplorationHistory...)
	if len(combinedInfo) == 0 {
		summary.WriteString("(Aucun)\n")
	} else {
		maxHistory := 6 // Reduced to make room for new sections
		start := 0
		if len(combinedInfo) > maxHistory {
			start = len(combinedInfo) - maxHistory
		}
		for _, info := range combinedInfo[start:] {
			if len(info) > 80 { // Reduced length to save space
				info = info[:80] + "..."
			}
			summary.WriteString(fmt.Sprintf("- %s\n", info))
		}
	}

	// Truncate if too long
	finalSummary := summary.String()
	if len(finalSummary) > maxPromptLength-500 {
		logrus.Warnf("Context summary is potentially too long (%d chars).", len(finalSummary))
	}

	return finalSummary
}

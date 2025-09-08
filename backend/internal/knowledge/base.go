package knowledge

import (
	"debugagent/internal/models"
	"debugagent/utils"
	"encoding/json"
	"fmt"
	"path/filepath"
	"strings"

	"github.com/sirupsen/logrus"
)

// NewKnowledgeBase crée une nouvelle instance de KnowledgeBase.
func NewKnowledgeBase(projectPath string) *models.KnowledgeBase {
	absPath, err := filepath.Abs(projectPath)
	if err != nil {
		logrus.Warnf("Could not resolve absolute path for %s: %v", projectPath, err)
		absPath = projectPath
	}

	return &models.KnowledgeBase{
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
func (kb *models.KnowledgeBase) getRelativePath(absFilepath string) (string, error) {
	return filepath.Rel(kb.ProjectPath, absFilepath)
}

// AddFileContent ajoute le contenu d'un fichier à la base de connaissances.
func (kb *models.KnowledgeBase) AddFileContent(absFilepath string, content string) {
	kb.Mu.Lock()
	defer kb.Mu.Unlock()

	relPath, err := kb.getRelativePath(absFilepath)
	if err != nil {
		logrus.Warnf("Could not get relative path for %s: %v. Using absolute path.", absFilepath, err)
		relPath = absFilepath
	}

	kb.FileContents[relPath] = content
	logrus.Infof("Content added/updated for '%s'", relPath)
}

// AddNote ajoute une note d'analyse.
func (kb *models.KnowledgeBase) AddNote(note string) {
	kb.Mu.Lock()
	defer kb.Mu.Unlock()

	// Éviter les notes dupliquées consécutives
	if len(kb.AnalysisNotes) == 0 || kb.AnalysisNotes[len(kb.AnalysisNotes)-1] != note {
		kb.AnalysisNotes = append(kb.AnalysisNotes, note)
		logrus.Debugf("Note added: %s...", note[:utils.Min(100, len(note))])
	}
}

// AddHistory ajoute une action à l'historique.
func (kb *models.KnowledgeBase) AddHistory(actionDescription string) {
	kb.Mu.Lock()
	defer kb.Mu.Unlock()

	// Éviter les entrées d'historique dupliquées consécutives
	if len(kb.ExplorationHistory) == 0 || kb.ExplorationHistory[len(kb.ExplorationHistory)-1] != actionDescription {
		kb.ExplorationHistory = append(kb.ExplorationHistory, actionDescription)
		logrus.Debugf("History added: %s", actionDescription)
	}
}

// SetProjectType met à jour le type de projet.
func (kb *models.KnowledgeBase) SetProjectType(pType string) {
	kb.Mu.Lock()
	defer kb.Mu.Unlock()

	if pType != "" && kb.ProjectType != pType {
		kb.ProjectType = pType
		logrus.Infof("Project type updated: %s", pType)
	}
}

// AddFailedFileAttempt tracks a failed file read attempt.
func (kb *models.KnowledgeBase) AddFailedFileAttempt(filePath string) {
	kb.Mu.Lock()
	defer kb.Mu.Unlock()

	kb.FailedFileAttempts[filePath]++
	logrus.Debugf("Failed file attempt recorded for '%s' (attempt #%d)", filePath, kb.FailedFileAttempts[filePath])
}

// IsFileAttemptExceeded checks if a file has been attempted too many times.
func (kb *models.KnowledgeBase) IsFileAttemptExceeded(filePath string, maxAttempts int) bool {
	kb.Mu.Lock()
	defer kb.Mu.Unlock()

	return kb.FailedFileAttempts[filePath] >= maxAttempts
}

// AddAvailableFile tracks a file that exists and can be read.
func (kb *models.KnowledgeBase) AddAvailableFile(filePath string) {
	kb.Mu.Lock()
	defer kb.Mu.Unlock()

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
func (kb *models.KnowledgeBase) AddDependencyFile(depType, filePath string) {
	kb.Mu.Lock()
	defer kb.Mu.Unlock()

	kb.DependencyFiles[depType] = filePath
	logrus.Infof("Dependency file found: %s -> %s", depType, filePath)
}

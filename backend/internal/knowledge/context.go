package knowledge

import (
	"debugagent/internal/models"
	"encoding/json"
	"fmt"
	"path/filepath"
	"strings"

	"github.com/sirupsen/logrus"
)

// GetContextSummary generates a context summary for the knowledge base.
func (kb *models.KnowledgeBase) GetContextSummary(userProblem string, maxPromptLength int) string {
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

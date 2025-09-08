package models

import "sync"

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
	Mu                 sync.Mutex        // Pour gérer l'accès concurrentiel (exported for package access)
}

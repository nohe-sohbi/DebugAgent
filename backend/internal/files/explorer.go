package files

import (
	"debugagent/config"
	"fmt"
	"io/ioutil"
	"os"
	"path/filepath"
	"strings"

	"github.com/sirupsen/logrus"
)

var (
	ignoreDirs       map[string]bool
	ignoreExtensions map[string]bool
	ignorePrefixes   []string
)

func initializeExplorerConfig() {
	cfg := config.AppConfig.Explorer
	ignoreDirs = make(map[string]bool)
	for _, dir := range cfg.IgnoreDirs {
		ignoreDirs[dir] = true
	}
	ignoreExtensions = make(map[string]bool)
	for _, ext := range cfg.IgnoreExtensions {
		ignoreExtensions[ext] = true
	}
	ignorePrefixes = cfg.IgnorePrefixes
}

// GetDirectoryStructure récupère la structure récursivement, en filtrant et limitant la profondeur.
func GetDirectoryStructure(rootDir string, maxDepth int, currentDepth int) (map[string]interface{}, error) {
	if ignoreDirs == nil {
		initializeExplorerConfig()
	}
	structure := make(map[string]interface{})
	if currentDepth >= maxDepth {
		structure["..."] = fmt.Sprintf("(limite de profondeur %d atteinte)", maxDepth)
		return structure, nil
	}

	files, err := ioutil.ReadDir(rootDir)
	if err != nil {
		return nil, fmt.Errorf("impossible de lister le dossier '%s': %w", rootDir, err)
	}

	for _, file := range files {
		fileName := file.Name()

		// Ignorer les répertoires et préfixes
		if ignoreDirs[fileName] {
			continue
		}
		isIgnoredPrefix := false
		for _, prefix := range ignorePrefixes {
			if strings.HasPrefix(fileName, prefix) {
				isIgnoredPrefix = true
				break
			}
		}
		if isIgnoredPrefix {
			continue
		}

		if file.IsDir() {
			subStructure, err := GetDirectoryStructure(filepath.Join(rootDir, fileName), maxDepth, currentDepth+1)
			if err != nil {
				structure[fileName+"/"] = fmt.Sprintf("Erreur d'accès: %v", err)
			} else {
				structure[fileName+"/"] = subStructure
			}
		} else {
			// Ignorer les extensions
			ext := strings.ToLower(filepath.Ext(fileName))
			if ignoreExtensions[ext] {
				continue
			}
			structure[fileName] = fmt.Sprintf("%d bytes", file.Size())
		}
	}
	return structure, nil
}

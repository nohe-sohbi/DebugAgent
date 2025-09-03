package main

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

// getDirectoryStructure récupère la structure récursivement, en filtrant et limitant la profondeur.
func getDirectoryStructure(rootDir string, maxDepth int, currentDepth int) (map[string]interface{}, error) {
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
			subStructure, err := getDirectoryStructure(filepath.Join(rootDir, fileName), maxDepth, currentDepth+1)
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

// readFileContent lit le contenu d'un fichier avec gestion d'erreurs et de taille.
func readFileContent(absFilepath string) (string, error) {
	fileInfo, err := os.Stat(absFilepath)
	if err != nil {
		return "", fmt.Errorf("fichier non trouvé ou erreur de stat: %w", err)
	}

	if fileInfo.IsDir() {
		return "", fmt.Errorf("le chemin '%s' est un dossier, pas un fichier", absFilepath)
	}

	// Vérifier si le fichier est binaire
	buffer := make([]byte, 1024)
	file, err := os.Open(absFilepath)
	if err != nil {
		return "", fmt.Errorf("impossible d'ouvrir le fichier pour vérification binaire: %w", err)
	}
	n, _ := file.Read(buffer)
	file.Close()

	for i := 0; i < n; i++ {
		if buffer[i] == 0 {
			return "", fmt.Errorf("le fichier '%s' semble être binaire", filepath.Base(absFilepath))
		}
	}

	// Lire le contenu du fichier
	size := fileInfo.Size()
	maxSize := config.AppConfig.Analysis.MaxFileReadSize
	if size > maxSize {
		logrus.Warnf("File '%s' (%d bytes) is too large. Reading partially.", filepath.Base(absFilepath), size)
		content, err := os.ReadFile(absFilepath)
		if err != nil {
			return "", fmt.Errorf("error reading partial file: %w", err)
		}

		startContent := string(content[:int(maxSize)/2])
		endContent := string(content[len(content)-(int(maxSize)/2):])

		return fmt.Sprintf("%s\n\n[... content truncated (file too large) ...]\n\n%s", startContent, endContent), nil
	}

	logrus.Infof("Reading complete file '%s' (%d bytes).", filepath.Base(absFilepath), size)
	content, err := os.ReadFile(absFilepath)
	if err != nil {
		return "", fmt.Errorf("error reading complete file: %w", err)
	}

	return string(content), nil
}

package main

import (
	"fmt"
	"io/ioutil"
	"log"
	"os"
	"path/filepath"
	"strings"
)


var (
	ignoreDirs = map[string]bool{
		".git":           true,
		".vscode":        true,
		"node_modules":   true,
		"__pycache__":    true,
		"venv":           true,
		".venv":          true,
		"target":         true,
		"build":          true,
		"dist":           true,
		"vendor":         true,
		".idea":          true,
		".composer":      true,
		"cache":          true,
		"logs":           true,
		"tmp":            true,
		"temp":           true,
	}
	ignorePrefixes = []string{".", "_"}
	ignoreExtensions = map[string]bool{
		".log":   true, ".tmp": true, ".bak": true, ".swp": true, ".map": true, ".lock": true, ".DS_Store": true,
		".pyc":   true, ".pyo": true, ".class": true, ".o": true, ".so": true, ".dll": true, ".exe": true,
		".jar":   true, ".war": true, ".ear": true, ".zip": true, ".gz": true, ".tar": true, ".rar": true, ".7z": true,
		".pdf":   true, ".doc": true, ".docx": true, ".xls": true, ".xlsx": true, ".ppt": true, ".pptx": true,
		".odt":   true, ".ods": true, ".odp": true, ".jpg": true, ".jpeg": true, ".png": true, ".gif": true,
		".bmp":   true, ".svg": true, ".webp": true, ".mp3": true, ".wav": true, ".ogg": true, ".mp4": true,
		".mov":   true, ".avi": true, ".webm": true,
	}
)

// getDirectoryStructure récupère la structure récursivement, en filtrant et limitant la profondeur.
func getDirectoryStructure(rootDir string, maxDepth int, currentDepth int) (map[string]interface{}, error) {
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
	if size > maxFileReadSize {
		log.Printf("Fichier '%s' (%d octets) trop volumineux. Lecture partielle.", filepath.Base(absFilepath), size)
		content, err := os.ReadFile(absFilepath)
		if err != nil {
			return "", fmt.Errorf("erreur lors de la lecture partielle du fichier: %w", err)
		}

		startContent := string(content[:maxFileReadSize/2])
		endContent := string(content[len(content)-(maxFileReadSize/2):])

		return fmt.Sprintf("%s\n\n[... contenu tronqué (fichier trop volumineux) ...]\n\n%s", startContent, endContent), nil
	}

	log.Printf("Lecture complète du fichier '%s' (%d octets).", filepath.Base(absFilepath), size)
	content, err := os.ReadFile(absFilepath)
	if err != nil {
		return "", fmt.Errorf("erreur lors de la lecture complète du fichier: %w", err)
	}

	return string(content), nil
}

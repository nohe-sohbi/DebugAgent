package files

import (
	"debugagent/config"
	"fmt"
	"os"
	"path/filepath"

	"github.com/sirupsen/logrus"
)

// ReadFileContent lit le contenu d'un fichier avec gestion d'erreurs et de taille.
func ReadFileContent(absFilepath string) (string, error) {
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
	maxSize := int64(config.AppConfig.Analysis.MaxFileReadSize)
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

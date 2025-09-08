package main

import (
	"debugagent/config"
	"fmt"
	"net/url"
	"strings"

	"github.com/JexSrs/go-ollama"
	"github.com/sirupsen/logrus"
)


// OllamaClient est une structure pour interagir avec l'API Ollama.
type OllamaClient struct {
	client *ollama.Ollama
	model  string
}

// NewOllamaClient crée un nouveau client pour Ollama.
func NewOllamaClient() (*OllamaClient, error) {
	host := config.AppConfig.Ollama.Host
	model := config.AppConfig.Ollama.Model

	ollamaURL, err := url.Parse(host)
	if err != nil {
		return nil, fmt.Errorf("URL Ollama invalide: %w", err)
	}

	client := ollama.New(*ollamaURL)

	logrus.Infof("Using Ollama client for host: %s", host)
	logrus.Infof("Using Ollama model: %s", model)

	return &OllamaClient{
		client: client,
		model:  model,
	}, nil
}

// ollamaRequest envoie une requête à Ollama en utilisant la fonction Generate.
func (oc *OllamaClient) ollamaRequest(systemMessage, userPrompt string) (string, error) {
	maxPromptLen := config.AppConfig.Analysis.MaxPromptLength
	logrus.Debugf("Sending prompt of %d characters to Ollama (max: %d)", len(userPrompt), maxPromptLen)
	
	if len(userPrompt) > maxPromptLen {
		logrus.Warnf("Prompt is being truncated from %d to %d characters.", len(userPrompt), maxPromptLen)
		userPrompt = userPrompt[:maxPromptLen]
	}

	// Utilisation de la fonction Generate qui est plus simple pour des requêtes uniques.
	res, err := oc.client.Generate(
		oc.client.Generate.WithModel(oc.model),
		oc.client.Generate.WithSystem(systemMessage),
		oc.client.Generate.WithPrompt(userPrompt),
	)

	if err != nil {
		return "", fmt.Errorf("erreur lors de l'appel à l'API Generate d'Ollama: %w", err)
	}

	if res.Done {
		if res.Response != "" {
			logrus.Debug("Response received from Ollama.")
			// Nettoyer la réponse des "```" que le modèle ajoute parfois
			return strings.TrimSpace(strings.Trim(res.Response, "```")), nil
		}
		return "", fmt.Errorf("réponse d'Ollama vide mais marquée comme terminée")
	}

	return "", fmt.Errorf("la requête à Ollama n'est pas terminée (comportement de streaming inattendu)")
}

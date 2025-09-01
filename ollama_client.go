package main

import (
	"fmt"
	"log"
	"net/url"
	"os"
	"strings"

	"github.com/JexSrs/go-ollama"
)


// OllamaClient est une structure pour interagir avec l'API Ollama.
type OllamaClient struct {
	client *ollama.Ollama
	model  string
}

// NewOllamaClient crée un nouveau client pour Ollama.
func NewOllamaClient() (*OllamaClient, error) {
	host := os.Getenv("OLLAMA_HOST")
	if host == "" {
		host = ollamaDefaultHost
	}

	ollamaURL, err := url.Parse(host)
	if err != nil {
		return nil, fmt.Errorf("URL Ollama invalide: %w", err)
	}

	client := ollama.New(*ollamaURL)

	model := os.Getenv("OLLAMA_MODEL")
	if model == "" {
		model = ollamaDefaultModel
	}

	log.Printf("Utilisation du client Ollama pour l'hôte: %s", host)
	log.Printf("Utilisation du modèle Ollama: %s", model)

	return &OllamaClient{
		client: client,
		model:  model,
	}, nil
}

// ollamaRequest envoie une requête à Ollama en utilisant la fonction Generate.
func (oc *OllamaClient) ollamaRequest(systemMessage, userPrompt string) (string, error) {
	if len(userPrompt) > maxPromptLength {
		log.Printf("Avertissement : le prompt est tronqué à %d caractères.", maxPromptLength)
		userPrompt = userPrompt[:maxPromptLength]
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
			log.Println("Réponse reçue d'Ollama.")
			// Nettoyer la réponse des "```" que le modèle ajoute parfois
			return strings.TrimSpace(strings.Trim(res.Response, "```")), nil
		}
		return "", fmt.Errorf("réponse d'Ollama vide mais marquée comme terminée")
	}

	return "", fmt.Errorf("la requête à Ollama n'est pas terminée (comportement de streaming inattendu)")
}

package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)


// AnalyzeRequest définit la structure pour la requête de l'API.
type AnalyzeRequest struct {
	ProjectPath string `json:"project_path"`
	Question    string `json:"question"`
}

// AnalyzeResponse définit la structure pour la réponse de l'API.
type AnalyzeResponse struct {
	Answer string `json:"answer"`
}


func parsePlan(planStr string) []string {
	lines := strings.Split(planStr, "\n")
	var plan []string
	// Regex améliorée pour extraire les actions et leurs arguments (y compris les chemins avec des espaces entre guillemets)
	actionRegex := regexp.MustCompile(`^\s*\d+\.\s*(READ_FILE|ANALYZE|FINISH)\s*(?:"([^"]+)"|'([^']+)'|(\S+.*))?$`)

	for _, line := range lines {
		matches := actionRegex.FindStringSubmatch(line)
		if len(matches) > 1 {
			action := strings.TrimSpace(matches[1])
			if action == "FINISH" {
				plan = append(plan, "FINISH")
				break
			}

			// Les arguments peuvent être dans l'un des groupes de capture
			args := ""
			if len(matches) > 2 && matches[2] != "" {
				args = matches[2] // Guillemets doubles
			} else if len(matches) > 3 && matches[3] != "" {
				args = matches[3] // Guillemets simples
			} else if len(matches) > 4 && matches[4] != "" {
				args = strings.TrimSpace(matches[4]) // Sans guillemets
			}

			if args != "" {
				plan = append(plan, fmt.Sprintf("%s %s", action, args))
			}
		}
	}
	return plan
}

func analyzeHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Seule la méthode POST est autorisée", http.StatusMethodNotAllowed)
		return
	}

	var req AnalyzeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Erreur de décodage de la requête JSON", http.StatusBadRequest)
		return
	}

	// --- Validation du chemin du projet ---
	projInfo, err := os.Stat(req.ProjectPath)
	if os.IsNotExist(err) || !projInfo.IsDir() {
		http.Error(w, fmt.Sprintf("Le chemin du projet '%s' n'est pas un dossier valide.", req.ProjectPath), http.StatusBadRequest)
		return
	}

	// --- Initialisation ---
	kb := NewKnowledgeBase(req.ProjectPath)
	ollamaClient, err := NewOllamaClient()
	if err != nil {
		http.Error(w, fmt.Sprintf("Erreur d'initialisation du client Ollama: %v", err), http.StatusInternalServerError)
		return
	}

	// --- 1. Analyse Initiale ---
	log.Println("1. Lancement de l'analyse initiale du projet...")
	structure, err := getDirectoryStructure(kb.ProjectPath, maxDirDepth, 0)
	if err != nil {
		kb.AddNote(fmt.Sprintf("Erreur lors de l'analyse de la structure: %v", err))
	} else {
		kb.ProjectStructure = structure
		kb.AddHistory("Analyse de la structure du répertoire terminée.")
	}

	// Lecture du README
	readmePath := filepath.Join(kb.ProjectPath, "README.md")
	if _, err := os.Stat(readmePath); err == nil {
		content, err := readFileContent(readmePath)
		if err != nil {
			kb.AddNote(fmt.Sprintf("Erreur de lecture du README: %v", err))
		} else {
			kb.AddFileContent(readmePath, content)
			kb.ReadmeContent = content[:min(500, len(content))]
			kb.AddHistory("Fichier README.md lu.")
		}
	}

	// Identification du type de projet par Ollama
	typePrompt := fmt.Sprintf(`
Contexte initial du projet %s:
Structure du projet (partielle): %v
---
Basé sur la structure, quel est le type de ce projet (ex: Backend Go, Frontend React)?
Sois bref (1 phrase).`, filepath.Base(kb.ProjectPath), kb.ProjectStructure)
	projectType, err := ollamaClient.ollamaRequest("Tu es un expert en architecture logicielle.", typePrompt)
	if err == nil {
		kb.SetProjectType(strings.TrimSpace(projectType))
		kb.AddHistory(fmt.Sprintf("Type de projet estimé: %s", kb.ProjectType))
	}

	// --- 2. Boucle d'Exploration ---
	log.Println("2. Démarrage de la boucle d'exploration...")
	for i := 0; i < maxExplorationIterations; i++ {
		log.Printf("--- Itération %d/%d ---", i+1, maxExplorationIterations)

		// a. Planification
		contextSummary := kb.getContextSummary(req.Question, maxPromptLength)
		planPrompt := fmt.Sprintf(`
Objectif: Répondre à "%s"
Contexte actuel:
%s
---
Propose les 3-5 prochaines étapes logiques. Utilise les actions: READ_FILE <chemin>, ANALYZE <sujet>, FINISH.
Format de sortie IMPERATIF: Liste numérotée simple.
Exemple:
1. READ_FILE main.go
2. ANALYZE le point d'entrée de l'application
`, req.Question, contextSummary)

		planSystemPrompt := "Tu es un planificateur d'exploration de code. Réponds UNIQUEMENT avec la liste numérotée des actions."
		rawPlan, err := ollamaClient.ollamaRequest(planSystemPrompt, planPrompt)
		if err != nil {
			kb.AddNote(fmt.Sprintf("Erreur de planification à l'itération %d: %v", i, err))
			continue
		}

		plan := parsePlan(rawPlan)
		if len(plan) == 0 || (len(plan) == 1 && plan[0] == "FINISH") {
			log.Println("Plan vide ou 'FINISH' reçu, fin de l'exploration.")
			break
		}
		kb.ExplorationPlan = plan

		// b. Exécution
		for _, step := range kb.ExplorationPlan {
			log.Printf("Exécution de l'étape: %s", step)
			parts := strings.SplitN(step, " ", 2)
			action := parts[0]
			args := ""
			if len(parts) > 1 {
				args = parts[1]
			}

			switch action {
			case "READ_FILE":
				filePath := filepath.Join(kb.ProjectPath, args)
				content, err := readFileContent(filePath)
				if err != nil {
					kb.AddNote(fmt.Sprintf("Échec lecture '%s': %v", args, err))
				} else {
					kb.AddFileContent(filePath, content)
				}
			case "ANALYZE":
				analysisPrompt := fmt.Sprintf(`
Contexte: %s
---
Analyse la question suivante: "%s"`, kb.getContextSummary(req.Question, maxPromptLength), args)
				analysisResult, err := ollamaClient.ollamaRequest("Tu es un assistant d'analyse de code.", analysisPrompt)
				if err != nil {
					kb.AddNote(fmt.Sprintf("Échec analyse '%s': %v", args, err))
				} else {
					kb.AddNote(fmt.Sprintf("Analyse de '%s': %s", args, analysisResult))
				}
			}
		}
	}

	// --- 3. Génération de la Réponse Finale ---
	log.Println("3. Génération de la réponse finale...")
	finalContext := kb.getContextSummary(req.Question, maxPromptLength)
	finalPrompt := fmt.Sprintf(`
Contexte final collecté:
%s
---
Synthétise toutes ces informations pour fournir une réponse complète et structurée à la question initiale de l'utilisateur: "%s"`, finalContext, req.Question)

	finalAnswer, err := ollamaClient.ollamaRequest("Tu es un assistant IA expert qui synthétise des informations techniques.", finalPrompt)
	if err != nil {
		http.Error(w, fmt.Sprintf("Erreur lors de la génération de la réponse finale: %v", err), http.StatusInternalServerError)
		return
	}

	// --- Envoi de la réponse ---
	resp := AnalyzeResponse{
		Answer: finalAnswer,
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

func main() {
	http.HandleFunc("/analyze", analyzeHandler)
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("Démarrage du serveur sur le port :%s...", port)
	if err := http.ListenAndServe(":"+port, nil); err != nil {
		log.Fatalf("Échec du démarrage du serveur : %v", err)
	}
}

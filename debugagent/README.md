# DebugAgent API (Go Version)

DebugAgent est une API Go qui utilise un agent IA pour analyser la structure d'un projet logiciel, lire des fichiers, et fournir des explications détaillées en réponse à des questions.

## Fonctionnalités

- Exposition d'une API pour l'analyse de projets.
- Analyse automatique de la structure d'un projet.
- Lecture et résumé des fichiers pertinents.
- Génération d'explications détaillées pour répondre à des questions sur le projet via Ollama.

## Prérequis

Avant d'utiliser DebugAgent, assurez-vous d'avoir les éléments suivants :

- **Go 1.18+** installé sur votre machine.
- **Ollama** en cours d'exécution sur votre machine.

## Installation et Lancement

1. Clonez le dépôt :
   ```bash
   git clone <URL_DU_DEPOT>
   cd <NOM_DU_DOSSIER>
   ```

2. Installez les dépendances Go :
   ```bash
   go mod tidy
   ```

3. Configurez les variables d'environnement (optionnel) :
   - `OLLAMA_MODEL` : Nom du modèle Ollama à utiliser (par défaut : `gemma3:latest`).
   - `PORT` : Port sur lequel le serveur écoutera (par défaut : `8080`).
   - Exemple :
     ```bash
     export OLLAMA_MODEL="gemma3:latest"
     export PORT="8888"
     ```

4. Lancez le serveur :
   ```bash
   go run .
   ```
   Le serveur démarrera et écoutera sur le port configuré (8080 par défaut).

## Utilisation de l'API

Pour analyser un projet, envoyez une requête `POST` au point de terminaison `/analyze`.

### Exemple avec `curl`

```bash
curl -X POST http://localhost:8080/analyze \
-H "Content-Type: application/json" \
-d '{
    "project_path": "/chemin/vers/votre/projet",
    "question": "Explique le but du fichier principal de ce projet."
}'
```

### Paramètres de la Requête

- `project_path` (string, requis) : Le chemin absolu vers le dossier du projet que vous souhaitez analyser.
- `question` (string, requis) : La question que vous posez sur le projet.

### Réponse

L'API retournera une réponse JSON contenant l'explication générée par l'IA.

```json
{
    "answer": "L'explication générée par l'IA sur le projet..."
}
```

## Contribution

Les contributions sont les bienvenues ! Si vous souhaitez contribuer, veuillez ouvrir une issue ou soumettre une pull request.

## Licence

Ce projet est sous licence Creative Commons BY-NC. Consultez le fichier `LICENSE` pour plus d'informations.

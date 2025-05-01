
# DebugAgent

DebugAgent est un outil d'analyse et d'exploration de projets logiciels. Il utilise un agent IA pour analyser la structure d'un projet, lire des fichiers, effectuer des recherches dans le code et fournir des explications détaillées basées sur le contexte.

## Fonctionnalités

- Analyse automatique de la structure d'un projet.
- Lecture et résumé des fichiers pertinents.
- Recherche de termes spécifiques dans le code.
- Génération d'explications détaillées pour répondre à des questions sur le projet.
- Interaction avec le modèle Ollama pour des analyses avancées.

## Prérequis

Avant d'installer et d'utiliser DebugAgent, assurez-vous d'avoir les éléments suivants :

- **Python 3.8+** installé sur votre machine.
- Le package `ollama` installé (voir ci-dessous).
- Un environnement virtuel Python (recommandé).
- Les dépendances listées dans `requirements.txt`.

## Installation

Suivez les étapes ci-dessous pour installer et configurer DebugAgent :

1. Clonez le dépôt :
   ```bash
   git clone <URL_DU_DEPOT>
   cd DebugAgent
   ```

2. Créez un environnement virtuel Python :
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Sur Windows : venv\Scripts\activate
   ```

3. Installez les dépendances :
   ```bash
   pip install -r requirements.txt
   ```

4. Configurez les variables d'environnement nécessaires :
   - `OLLAMA_MODEL` : Nom du modèle Ollama à utiliser (par défaut : `gemma3:latest`).
   - `LOG_LEVEL` : Niveau de journalisation (`DEBUG`, `INFO`, etc.).
   - Exemple :
     ```bash
     export OLLAMA_MODEL="gemma3:latest"
     export LOG_LEVEL="INFO"
     ```

5. Lancez l'application :
   ```bash
   python main.py
   ```

## Utilisation

1. Lors de l'exécution, l'agent vous demandera de spécifier un dossier projet et une question ou un problème à résoudre.
2. L'agent analysera le projet, planifiera des étapes d'exploration et fournira des explications basées sur les résultats.

## Journalisation

Les journaux sont configurés pour afficher les messages dans la console. Vous pouvez ajuster le niveau de détail en modifiant la variable d'environnement `LOG_LEVEL`.

## Contribution

Les contributions sont les bienvenues ! Si vous souhaitez contribuer, veuillez ouvrir une issue ou soumettre une pull request.

## Licence

Ce projet est sous licence Creative Commons BY-NC. Consultez le fichier `LICENSE` pour plus d'informations.

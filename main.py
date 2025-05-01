import ollama
import os
import json
import re
from pathlib import Path
import logging
from typing import Dict, List, Optional, Any

# --- Configuration du Logging ---
# Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration Globale ---
# Mettez ici le nom du modèle Ollama que vous souhaitez utiliser
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'gemma3:latest') # ou llama3, etc.
# Taille maximale des fichiers à lire entièrement (en octets)
MAX_FILE_READ_SIZE = int(os.environ.get('MAX_FILE_READ_SIZE', 150000)) # 150 KB
# Limite de sécurité pour éviter les boucles infinies
MAX_EXPLORATION_ITERATIONS = int(os.environ.get('MAX_EXPLORATION_ITERATIONS', 6))
# Profondeur max pour l'exploration de la structure du répertoire
MAX_DIR_DEPTH = int(os.environ.get('MAX_DIR_DEPTH', 5))
# Taille max du prompt (approximative, pour éviter erreurs)
MAX_PROMPT_LENGTH = int(os.environ.get('MAX_PROMPT_LENGTH', 7500)) # Ajuster selon modèle/RAM

class KnowledgeBase:
    """Structure pour stocker les informations collectées pendant l'analyse."""
    def __init__(self, project_path: Path):
        self.project_path: Path = project_path.resolve() # Assurer chemin absolu
        self.project_structure: Optional[Dict[str, Any]] = None
        self.project_type: str = "Inconnu"
        self.readme_content: Optional[str] = None # Peut être redondant avec file_contents
        # Stocke le contenu des fichiers lus (chemin relatif -> contenu/résumé)
        self.file_contents: Dict[str, str] = {}
        self.analysis_notes: List[str] = []
        self.exploration_plan: List[str] = [] # Le plan *actuel*
        self.exploration_history: List[str] = [] # Historique des actions effectuées

    def _get_relative_path(self, abs_filepath_str: str) -> str:
        """Convertit un chemin absolu en chemin relatif au projet."""
        try:
            abs_path = Path(abs_filepath_str).resolve()
            if self.project_path in abs_path.parents or self.project_path == abs_path.parent:
                 return str(abs_path.relative_to(self.project_path))
            else:
                 # Si hors projet (ne devrait pas arriver avec les vérifs), retourne le nom du fichier ?
                 return Path(abs_filepath_str).name
        except ValueError: # Si relative_to échoue
             return Path(abs_filepath_str).name
        except Exception: # Autres erreurs potentielles
            return abs_filepath_str # Retourne le chemin original en dernier recours

    def add_file_content(self, abs_filepath: str, content: str):
        """Ajoute le contenu d'un fichier à la base de connaissances."""
        relative_path = self._get_relative_path(abs_filepath)
        self.file_contents[relative_path] = content # Stocker avec chemin relatif
        logging.info(f"Contenu ajouté/mis à jour pour '{relative_path}'")
        # N'ajoute plus à l'historique ici, c'est fait par l'appelant (_execute_read_file)

    def add_note(self, note: str):
        """Ajoute une note d'analyse."""
        # Éviter les doublons simples
        if not self.analysis_notes or note != self.analysis_notes[-1]:
            self.analysis_notes.append(note)
            logging.info(f"Note ajoutée: {note[:100]}...") # Log tronqué
        else:
            logging.debug(f"Note dupliquée ignorée: {note[:100]}...")

    def add_history(self, action_description: str):
        """Ajoute une action à l'historique."""
         # Éviter les doublons simples
        if not self.exploration_history or action_description != self.exploration_history[-1]:
            self.exploration_history.append(action_description)
            logging.debug(f"Historique ajouté: {action_description}")
        else:
             logging.debug(f"Action historique dupliquée ignorée: {action_description}")


    def set_project_type(self, p_type: str):
        if p_type and p_type != self.project_type:
            self.project_type = p_type
            logging.info(f"Type de projet mis à jour: {p_type}")

    def set_plan(self, plan: List[str]):
        self.exploration_plan = plan
        logging.info("Nouveau plan d'exploration défini.")

    def get_context_summary(self, user_problem: str, include_plan: bool = False) -> str:
        """Génère un résumé du contexte pour les prompts Ollama."""
        summary = f"Problème utilisateur: \"{user_problem}\"\n"
        summary += f"Chemin du projet: {self.project_path}\n"
        # Mettre en évidence le type de projet pour l'IA
        summary += f"TYPE DE PROJET ESTIMÉ: {self.project_type}\n"

        if self.project_structure:
             try:
                 # Formatter la structure en JSON pour la lisibilité par l'IA
                 structure_str = json.dumps(self.project_structure, indent=2, ensure_ascii=False)
                 # Limiter la taille globale de la structure dans le prompt
                 MAX_STRUCTURE_LENGTH = 2500 # Ajustable
                 if len(structure_str) > MAX_STRUCTURE_LENGTH:
                     structure_str = structure_str[:MAX_STRUCTURE_LENGTH] + f"\n... (structure tronquée à {MAX_STRUCTURE_LENGTH} caractères)"
                 summary += f"\nStructure du projet (fichiers/dossiers détectés, chemins relatifs):\n```json\n{structure_str}\n```\n"
             except Exception as e:
                 summary += f"\nStructure du projet: (Erreur de formatage JSON: {e})\n"
                 logging.error(f"Erreur lors du formatage JSON de la structure: {e}")

        summary += "\nFichiers déjà explorés (chemins relatifs) et extraits/résumés:\n"
        if not self.file_contents:
            summary += "(Aucun fichier lu pour le moment)\n"
        else:
            count = 0
            MAX_FILES_IN_SUMMARY = 10 # Limite pour la concision
            # Trier par nom pour la cohérence
            sorted_files = sorted(self.file_contents.items())
            for path, content in sorted_files:
                 summary += f"- `{path}`: {content[:150].replace('`','').strip()}...\n" # Extrait court, chemin en backticks
                 count += 1
                 if count >= MAX_FILES_IN_SUMMARY:
                     summary += f"... et {len(self.file_contents) - count} autres fichiers lus.\n"
                     break

        summary += "\nNotes d'analyse et historique récent des actions:\n"
        combined_info = self.analysis_notes + self.exploration_history
        if not combined_info:
            summary += "(Aucune note ou action enregistrée)\n"
        else:
            # Afficher les N dernières infos pour garder le contexte pertinent
            MAX_HISTORY_ITEMS_IN_SUMMARY = 15 # Ajustable
            start_index = max(0, len(combined_info) - MAX_HISTORY_ITEMS_IN_SUMMARY)
            displayed_items = combined_info[start_index:]
            for info in displayed_items:
                # Précéder d'un tiret pour la clarté
                summary += f"- {info}\n"
            if start_index > 0:
                 summary += f"... ({start_index} notes/actions précédentes omises pour la concision)\n"

        # Optionnellement inclure le plan actuel dans le contexte (utilisé par evaluate_progress?)
        if include_plan and self.exploration_plan:
             summary += "\nPlan d'exploration actuel (prochaines étapes prévues):\n"
             for i, step in enumerate(self.exploration_plan):
                 summary += f"{i+1}. {step}\n"

        # Vérifier la taille totale du résumé pour éviter de dépasser les limites du modèle
        if len(summary) > MAX_PROMPT_LENGTH - 500: # Garder une marge pour le reste du prompt
            logging.warning(f"Le résumé du contexte ({len(summary)} caractères) est très long, risque de troncature.")
            # On pourrait tronquer ici, mais c'est risqué de perdre des infos clés.
            # Pour l'instant, on laisse _ollama_request gérer la troncature finale si nécessaire.

        return summary

class OllamaCodingAgent:
    """Agent IA interagissant avec Ollama pour analyser du code et répondre à des questions."""
    def __init__(self, project_folder: str):
        self.project_path = Path(project_folder).resolve()
        if not self.project_path.is_dir():
            raise ValueError(f"Le dossier spécifié n'existe pas ou n'est pas un dossier: {self.project_path}")
        self.kb = KnowledgeBase(self.project_path)
        self.user_problem = ""
        logging.info(f"Agent initialisé pour le projet: {self.project_path}")
        logging.info(f"Utilisation du modèle Ollama: {OLLAMA_MODEL}")

    def _ollama_request(self, prompt: str, system_message: str = "") -> Optional[str]:
        """Méthode privée pour les appels Ollama avec gestion d'erreurs et troncature."""
        # Tronquer le prompt si nécessaire pour respecter la limite configurée
        if len(prompt) > MAX_PROMPT_LENGTH:
            chars_to_cut = len(prompt) - MAX_PROMPT_LENGTH
            prompt = prompt[:-chars_to_cut] # Couper la fin
            logging.warning(f"Prompt tronqué à {MAX_PROMPT_LENGTH} caractères (supprimé {chars_to_cut} de la fin).")
            prompt += "\n... (Fin du prompt tronquée)"

        logging.debug(f"Appel Ollama - Système: '{system_message}' - Prompt (taille={len(prompt)}, début): '{prompt[:150].replace(chr(10),' ')}...'")
        try:
            messages = []
            if system_message:
                messages.append({'role': 'system', 'content': system_message})
            messages.append({'role': 'user', 'content': prompt})

            response = ollama.chat(model=OLLAMA_MODEL, messages=messages)

            # Vérifier si la réponse contient bien le message attendu
            if 'message' in response and 'content' in response['message']:
                content = response['message']['content'].strip()
                logging.debug(f"Réponse Ollama (taille={len(content)}, début): {content[:150].replace(chr(10),' ')}...")
                return content
            else:
                logging.error(f"Réponse inattendue d'Ollama: {response}")
                return None

        except Exception as e:
            logging.error(f"Erreur lors de l'appel à Ollama: {e}", exc_info=True)
            # Ajouter une note KB sur l'échec de l'appel ?
            # self.kb.add_note(f"Erreur critique lors de l'appel Ollama: {e}")
            return None

    # --- Fonctions utilitaires (get_directory_structure, read_file_content) ---

    def get_directory_structure(self, root_dir: Path, max_depth=MAX_DIR_DEPTH, current_depth=0) -> Dict[str, Any]:
        """Récupère la structure récursivement, en filtrant et limitant la profondeur."""
        structure = {}
        # Condition d'arrêt de la récursion
        if current_depth >= max_depth:
            return {"...": f"(limite de profondeur {max_depth} atteinte)"}

        try:
            # Dossiers et préfixes à ignorer systématiquement
            ignore_dirs = {'.git', '.vscode', 'node_modules', '__pycache__', 'venv', '.venv', 'target', 'build', 'dist', 'vendor', '.idea', '.composer', 'cache', 'logs', 'tmp', 'temp'}
            ignore_prefixes = ('.', '_') # Ignorer fichiers/dossiers cachés ou préfixés par _
            # Extensions de fichiers souvent non pertinentes pour l'analyse de code source
            ignore_extensions = {'.log', '.tmp', '.bak', '.swp', '.map', '.lock', '.DS_Store', '.pyc', '.pyo', '.class', '.o', '.so', '.dll', '.exe', '.jar', '.war', '.ear', '.zip', '.gz', '.tar', '.rar', '.7z', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp'}
            # Ignorer les images, vidéos, audio...
            media_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.mp3', '.wav', '.ogg', '.mp4', '.mov', '.avi', '.webm'}
            ignore_extensions.update(media_extensions)

            items_to_process = []
            # Utiliser os.scandir pour plus d'efficacité (récupère type et nom en un appel)
            for entry in os.scandir(root_dir):
                if entry.name not in ignore_dirs and not entry.name.startswith(ignore_prefixes):
                    items_to_process.append(entry)

            # Trier : dossiers en premier, puis par nom
            items_to_process.sort(key=lambda x: (not x.is_dir(), x.name.lower()))

            for entry in items_to_process:
                try: # try/except individuel pour la robustesse
                    if entry.is_dir(follow_symlinks=False): # Ne pas suivre les liens symboliques pour les dossiers pour éviter les boucles et rester dans le projet
                        structure[entry.name + '/'] = self.get_directory_structure(Path(entry.path), max_depth, current_depth + 1)
                    elif entry.is_file(follow_symlinks=True): # Suivre les liens pour les fichiers si besoin
                        file_path = Path(entry.path)
                        # Vérifier l'extension
                        if file_path.suffix.lower() not in ignore_extensions:
                            try:
                                # Ajouter la taille pour aider l'IA à prioriser
                                size = entry.stat().st_size
                                structure[entry.name] = f"{size} bytes"
                            except OSError:
                                structure[entry.name] = "Erreur lecture taille"
                    # Ignorer silencieusement les autres types (liens symboliques non suivis, etc.)
                except OSError as e:
                    structure[entry.name] = f"Erreur d'accès ({e.strerror})"
                except Exception as e:
                    structure[entry.name] = f"Erreur inattendue ({type(e).__name__})"

        except PermissionError:
            # Si on n'a pas la permission de lister le dossier racine (rare ici, mais possible)
            return {"ERREUR": f"Permission refusée pour lister le dossier '{root_dir.name}'"}
        except FileNotFoundError:
             # Si le dossier root_dir a disparu entre-temps
             return {"ERREUR": f"Dossier '{root_dir.name}' non trouvé pendant le listage"}
        except Exception as e:
             # Erreur générique pour le listage du dossier lui-même
             return {"ERREUR": f"Erreur inattendue lors du listage de '{root_dir.name}': {e}"}

        # Indiquer si un dossier est vide (après filtrage) pour éviter la confusion avec profondeur max
        if not structure and current_depth < max_depth :
             # Seulement si le dossier existe et qu'on avait la permission
             if 'ERREUR' not in structure :
                 return {"(vide ou contenu ignoré)": ""}

        return structure

    def read_file_content(self, abs_filepath_str: str) -> str:
        """Lit le contenu d'un fichier (chemin absolu), avec gestion d'erreurs et de taille."""
        try:
            abs_filepath = Path(abs_filepath_str).resolve() # Résoudre au cas où c'est un lien symbolique etc.

            # Vérification de sécurité primordiale : est-ce bien DANS le projet ?
            if self.project_path not in abs_filepath.parents and self.project_path != abs_filepath.parent:
                 # Tenter de le résoudre relativement au projet si jamais l'entrée était relative
                 potential_path = self.project_path / abs_filepath_str
                 if potential_path.is_file() and self.project_path in potential_path.resolve().parents:
                     abs_filepath = potential_path.resolve()
                     logging.warning(f"Chemin '{abs_filepath_str}' résolu en '{abs_filepath}' relatif au projet.")
                 else:
                     error_msg = f"Erreur Sécurité: Tentative de lecture hors du dossier projet: '{abs_filepath_str}'"
                     logging.error(error_msg)
                     # Ne pas ajouter ce chemin à l'historique d'échec ?
                     return error_msg

            # Vérifier si le fichier existe et est bien un fichier
            if not abs_filepath.is_file():
                error_msg = f"Erreur: '{self.kb._get_relative_path(str(abs_filepath))}' n'est pas un fichier valide ou n'existe pas."
                logging.error(error_msg)
                # Ajouter l'échec à l'historique ici ? Non, fait par l'appelant.
                return error_msg

            # Vérifier la taille du fichier
            try:
                size = abs_filepath.stat().st_size
            except OSError as e:
                error_msg = f"Erreur: Impossible d'obtenir la taille de '{self.kb._get_relative_path(str(abs_filepath))}': {e}"
                logging.error(error_msg)
                return error_msg

            if size == 0:
                logging.info(f"Fichier '{self.kb._get_relative_path(str(abs_filepath))}' est vide.")
                return "" # Retourner une chaîne vide

            # --- Détection de binaire (heuristique simple) ---
            is_binary = False
            try:
                with open(abs_filepath, 'rb') as f_test:
                    # Lire un échantillon pour détecter des caractères nuls (commun dans les binaires)
                    chunk = f_test.read(1024)
                    if b'\x00' in chunk:
                        # Exclure certains types de fichiers texte qui *peuvent* contenir null (UTF-16 etc) ? Pour l'instant non.
                        is_binary = True
                        logging.warning(f"Fichier '{self.kb._get_relative_path(str(abs_filepath))}' semble être binaire (contient \\x00), lecture ignorée.")
                        return f"Erreur: Fichier '{self.kb._get_relative_path(str(abs_filepath))}' semble binaire."
            except Exception as e:
                 # Si on ne peut pas tester, on suppose que ce n'est pas binaire mais on log
                 logging.warning(f"Impossible de vérifier si '{self.kb._get_relative_path(str(abs_filepath))}' est binaire: {e}")

            # --- Lecture du contenu (texte) ---
            if size > MAX_FILE_READ_SIZE:
                logging.warning(f"Fichier '{self.kb._get_relative_path(str(abs_filepath))}' ({size} octets > {MAX_FILE_READ_SIZE}) est trop volumineux. Lecture partielle (début et fin).")
                try:
                    with open(abs_filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        # Lire une partie du début et une partie de la fin
                        start_content = f.read(MAX_FILE_READ_SIZE // 2)
                        # Se déplacer vers la fin (ne pas lire deux fois le même contenu si fichier petit)
                        f.seek(max(MAX_FILE_READ_SIZE // 2, size - (MAX_FILE_READ_SIZE // 2)))
                        end_content = f.read(MAX_FILE_READ_SIZE // 2)
                        # S'assurer qu'on ne duplique pas si le fichier est à peine plus grand que MAX_FILE_READ_SIZE
                        if f.tell() < size: # Vérifier si on a vraiment lu la fin
                             return f"{start_content}\n\n[... contenu tronqué (fichier trop volumineux) ...]\n\n{end_content}"
                        else: # Le fichier était juste un peu plus grand, start_content contient presque tout
                            return start_content + "\n[... fin du fichier tronquée ...]"

                except Exception as e:
                    error_msg = f"Erreur lors de la lecture partielle de '{self.kb._get_relative_path(str(abs_filepath))}': {e}"
                    logging.error(error_msg)
                    return error_msg
            else:
                # Lire le fichier complet
                logging.info(f"Lecture complète du fichier '{self.kb._get_relative_path(str(abs_filepath))}' ({size} octets).")
                try:
                    with open(abs_filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        return f.read()
                except Exception as e:
                    error_msg = f"Erreur lors de la lecture complète de '{self.kb._get_relative_path(str(abs_filepath))}': {e}"
                    logging.error(error_msg)
                    return error_msg

        except Exception as e:
            # Erreur générale inattendue
            logging.error(f"Erreur inattendue lors de la tentative de lecture de '{abs_filepath_str}': {e}", exc_info=True)
            return f"Erreur inattendue lors de la lecture de '{abs_filepath_str}': {e}"


    # --- Fonctions d'analyse et d'exploration ---

    def analyze_initial_context(self):
        """Analyse initiale : structure, README, type de projet."""
        logging.info("1. Analyse initiale du projet...")
        # --- Structure du répertoire ---
        project_structure_data = self.get_directory_structure(self.project_path)
        self.kb.project_structure = project_structure_data # Stocker dans KB
        # Log plus détaillé si besoin en mode DEBUG
        logging.debug(f"Structure complète détectée:\n{json.dumps(project_structure_data, indent=2, ensure_ascii=False)}")
        # Log INFO tronqué pour ne pas polluer
        structure_summary_for_log = json.dumps(project_structure_data, indent=2, ensure_ascii=False)
        if len(structure_summary_for_log) > 1000:
            structure_summary_for_log = structure_summary_for_log[:1000] + "\n... (structure log tronquée)"
        logging.info(f"Structure détectée (partielle pour log):\n{structure_summary_for_log}")

        # --- Lecture du README ---
        readme_path_abs = None
        found_readme = False
        # Chercher de manière insensible à la casse et prioriser .md
        for fname_pattern in ['readme.md', 'README.md', 'readme.*', 'README.*']:
             potential_readmes = sorted(list(self.project_path.glob(fname_pattern)), key=lambda p: p.suffix.lower() != '.md')
             if potential_readmes:
                 readme_path_abs = str(potential_readmes[0].resolve()) # Prendre le premier (priorité .md)
                 found_readme = True
                 break

        if found_readme:
            readme_rel_path = self.kb._get_relative_path(readme_path_abs)
            logging.info(f"Lecture du fichier README trouvé: '{readme_rel_path}'...")
            readme_content = self.read_file_content(readme_path_abs)
            if not readme_content.startswith("Erreur:"):
                # Ajouter le contenu à la KB (sera fait par _execute_read_file plus tard si planifié, mais utile pour contexte initial)
                self.kb.add_file_content(readme_path_abs, readme_content)
                # On peut aussi stocker une référence directe pour le résumé initial si besoin
                self.kb.readme_content = readme_content[:500] # Garder juste un extrait
                self.kb.add_history(f"Lu le fichier README '{readme_rel_path}' lors de l'analyse initiale.")
            else:
                 logging.warning(f"Impossible de lire le README '{readme_rel_path}': {readme_content}")
                 self.kb.add_history(f"Échec lecture README '{readme_rel_path}' lors analyse initiale.")
        else:
            logging.info("Aucun fichier README standard trouvé à la racine.")
            self.kb.add_history("Aucun fichier README trouvé lors analyse initiale.")

        # --- Identification Type/Stack Projet par Ollama ---
        # Préparer un contexte SANS les contenus de fichiers pour cette étape (basé structure)
        context_for_type_prompt = f"Problème utilisateur: \"{self.user_problem}\"\n"
        context_for_type_prompt += f"Chemin du projet: {self.project_path}\n"
        if self.kb.project_structure:
            structure_str_type = json.dumps(self.kb.project_structure, indent=2, ensure_ascii=False)
            if len(structure_str_type) > 1500: structure_str_type = structure_str_type[:1500] + "\n..."
            context_for_type_prompt += f"\nStructure du projet:\n```json\n{structure_str_type}\n```\n"
        # Lister les fichiers racine clés s'ils existent
        important_files = ["composer.json", "package.json", "requirements.txt", "pom.xml", "go.mod", "Gemfile", "Cargo.toml", "build.gradle", "Makefile"]
        root_files_context = "Fichiers notables à la racine:\n"
        found_notable = False
        for imp_file in important_files:
            if (self.project_path / imp_file).is_file():
                 try:
                    size = (self.project_path / imp_file).stat().st_size
                    root_files_context += f"- {imp_file} ({size} bytes)\n"
                    found_notable = True
                 except OSError:
                    root_files_context += f"- {imp_file} (accès impossible)\n"
        if found_notable:
             context_for_type_prompt += root_files_context

        type_prompt = f"""
        Contexte initial du projet situé à `{self.project_path}`:
        {context_for_type_prompt}
        ---
        Basé **uniquement** sur la structure de fichiers/dossiers fournie et les fichiers racine notables (NE PAS utiliser le contenu du README pour l'instant), quelle est la stack technique principale et le type de ce projet (ex: Web Backend PHP avec Composer, Frontend React avec npm, Application CLI Python, etc.) ?
        Sois bref et direct (1 phrase maximum).
        """
        system_type = "Tu identifies la stack technique et le type d'un projet logiciel **uniquement** d'après sa structure de fichiers/dossiers et les fichiers de configuration racine. Réponds en une seule phrase."
        project_type_guess = self._ollama_request(type_prompt, system_type)

        if project_type_guess:
            # Nettoyer la réponse (peut ajouter des justifications non demandées)
            project_type_guess = project_type_guess.split('\n')[0].strip()
            # Enlever les phrases génériques si présentes
            project_type_guess = re.sub(r"^(Basé sur.*?, |Il semble que |Le projet est |This appears to be )", "", project_type_guess, flags=re.IGNORECASE)
            self.kb.set_project_type(project_type_guess)
            self.kb.add_note(f"Analyse initiale type/stack (basée structure): {project_type_guess}")
            self.kb.add_history(f"Type de projet estimé (structure): {project_type_guess}")
        else:
            # Garder "Inconnu" mais ajouter une note d'échec
             self.kb.add_note("Échec de l'identification initiale du type de projet.")
             self.kb.add_history("Échec identification type projet initial.")
        logging.info(f"Type de projet estimé (structure): {self.kb.project_type}")

    def plan_exploration(self, current_context: str):
        """Demande à Ollama de créer ou raffiner un plan d'exploration basé sur le contexte."""
        logging.info("-> Planification/Re-planification de l'exploration...")

        # Construire le prompt pour Ollama
        plan_prompt = f"""
        OBJECTIF: Répondre à la question utilisateur : "{self.user_problem}"
        PROJET: Type estimé '{self.kb.project_type}' situé à `{self.project_path}`.

        CONTEXTE ACTUEL (Structure, fichiers lus, notes, historique):
        ```
        {current_context}
        ```
        ---
        HISTORIQUE RÉCENT (5 dernières actions/notes):
        {chr(10).join(f'- {h}' for h in (self.kb.analysis_notes + self.kb.exploration_history)[-5:]) if (self.kb.analysis_notes + self.kb.exploration_history) else "(aucune action/note récente)"}
        ---
        INSTRUCTIONS POUR LE PLAN:
        1. Propose les 3-5 prochaines étapes **les plus logiques** pour trouver la réponse à l'objectif dans ce projet **{self.kb.project_type}**.
        2. **BASE-TOI STRICTEMENT sur la structure de fichiers/dossiers fournie dans le contexte.** N'invente PAS de fichiers ou de chemins qui n'y figurent pas. Si la structure indique `... (limite atteinte)`, tu ne peux pas proposer de lire des fichiers dans cette partie; concentre-toi sur ce qui est visible.
        3. **Privilégie les fichiers correspondant au type de projet** (ex: fichiers `.php` pour un projet PHP). Vérifie l'extension des fichiers avant de les proposer.
        4. Indique des actions claires utilisant les verbes `READ_FILE`, `SEARCH_CODE`, `ANALYZE`. Utilise des chemins **relatifs** au projet (ex: `application/model/Song.php`).
        5. Si une action précédente a échoué (ex: fichier non trouvé, erreur lecture), ne la repropose pas et adapte ton plan pour chercher ailleurs ou analyser pourquoi ça a échoué.
        6. Si tu penses avoir assez d'informations pour répondre à l'objectif **maintenant**, propose comme SEULE étape: `FINISH`.

        Format attendu: Liste numérotée simple, une action par ligne. PAS de blabla avant/après la liste. PAS de markdown dans les étapes.
        Exemple PHP:
        1. READ_FILE application/controllers/SongsController.php
        2. SEARCH_CODE "INSERT INTO song" dans application/model/SongModel.php
        3. READ_FILE application/config/database.php
        4. ANALYZE comment la connexion DB est partagée entre les modèles
        """
        system_plan = f"Tu es un assistant expert en code {self.kb.project_type}. Tu planifies une exploration de code étape par étape pour répondre à la question: '{self.user_problem}'. Sois rigoureux, base-toi **uniquement** sur le contexte fourni (structure, type, historique). Propose un plan clair au format demandé (liste numérotée d'actions `VERBE arguments`)."

        plan_str = self._ollama_request(plan_prompt, system_plan)

        if plan_str:
            # Parsing robuste : nettoie chaque ligne, enlève numéros/markdown avant de valider
            plan_list = []
            potential_finish = False
            raw_lines = [line.strip() for line in plan_str.split('\n') if line.strip()]

            for line in raw_lines:
                 # Nettoyer la ligne: enlever numéro, points, espaces, potentiels **/__
                 cleaned_line = re.sub(r'^\s*\d+\.\s*(\*\*|__)?', '', line).strip()
                 # Enlever les backticks si présents
                 cleaned_line = cleaned_line.strip('`').strip()

                 if not cleaned_line: continue # Ignorer ligne vide après nettoyage

                 # Vérifier FINISH
                 if cleaned_line.upper() == "FINISH":
                     potential_finish = True
                     # Si FINISH est seul, on le prend
                     if len(raw_lines) == 1:
                         plan_list = ["FINISH"]
                         break
                     else:
                         # Si FINISH est mélangé, on l'ignore pour l'instant et on prend les autres actions ?
                         # Ou on considère que l'IA est confuse ? On va l'ignorer pour l'instant si d'autres étapes sont là.
                         logging.warning(f"Action FINISH trouvée dans un plan mixte, ignorée pour l'instant: '{line}'")
                         continue # Ne pas ajouter FINISH si d'autres étapes sont proposées

                 # Vérifier si ça commence par un verbe connu (plus fiable que juste numéro)
                 match = re.match(r'^(READ_FILE|SEARCH_CODE|ANALYZE)\s+(.*)', cleaned_line, re.IGNORECASE)
                 if match:
                     # Reformater pour être sûr: VERBE en majuscule, args nettoyés
                     verb = match.group(1).upper()
                     args = match.group(2).strip()
                     # Nettoyer les args (enlever guillemets potentiels autour du chemin/terme si SEARCH)
                     if verb == "SEARCH_CODE":
                          # Ex: SEARCH_CODE "term" dans path -> "term" dans path
                          # Ex: SEARCH_CODE term dans path -> term dans path
                          # On garde les guillemets autour du terme pour le parsing plus tard
                          pass # Garder les args tels quels pour l'instant
                     elif verb == "READ_FILE":
                          # Enlever guillemets autour du chemin si présents
                           args = args.strip("'\"")

                     # Ajouter l'étape formatée à la liste
                     plan_list.append(f"{verb} {args}")
                 else:
                      logging.warning(f"Étape du plan non reconnue ou mal formatée ignorée: '{line}' (nettoyée: '{cleaned_line}')")

            # Décision finale sur le plan
            if potential_finish and not plan_list: # FINISH était seul (ou détecté comme tel)
                 self.kb.set_plan(["FINISH"])
                 logging.info("Plan suggéré par Ollama: Terminer l'exploration.")
            elif plan_list:
                 self.kb.set_plan(plan_list)
                 logging.info("Nouveau plan généré et validé :")
                 for step in self.kb.exploration_plan:
                      logging.info(f"      {step}")
            else:
                 logging.warning(f"La réponse d'Ollama ne contient aucun plan valide après nettoyage:\n{plan_str}")
                 self.kb.set_plan([]) # Plan vide pour éviter erreur boucle infinie
        else:
            logging.error("Impossible de générer un plan (Ollama n'a pas répondu).")
            self.kb.set_plan([]) # Plan vide

    def _extract_path_from_step_or_args(self, text_input: str) -> Optional[str]:
        """Tente d'extraire un chemin de fichier (relatif ou absolu mais dans projet) d'une chaîne."""
        # Priorité aux chemins entre ` ou ' ou "
        # Chemin: commence par lettre, chiffre, ./ ou ../, contient / ou \ , finit par extension connue
        common_extensions = r'\.(php|py|js|ts|go|java|c|cpp|h|hpp|cs|rb|rs|md|txt|json|yaml|yml|xml|html|css|scss|sql|sh|config|ini|env)'
        # 1. Chemins entre quotes/backticks
        match = re.search(r"[`'\"]([\.\/\w\\-]+?" + common_extensions + r")[`'\"]", text_input, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # 2. Chemins sans quotes mais plausibles (contiennent / ou \)
        match = re.search(r"([\.\/\w\\-]+?" + common_extensions + r")", text_input, re.IGNORECASE)
        if match:
            path_str = match.group(1).strip()
            # Vérifier qu'il contient bien un séparateur de dossier pour éviter faux positifs (ex: Object.keys)
            if '/' in path_str or '\\' in path_str:
                return path_str

        # 3. Juste un nom de fichier (moins fiable, on suppose relatif à la racine)
        match = re.search(r"([\w\-]+\." + common_extensions + r")", text_input, re.IGNORECASE)
        if match:
             # Attention, peut être un nom de classe.méthode. Vérifier s'il existe à la racine ?
             potential_path = self.project_path / match.group(1).strip()
             # Ne retourne que si le fichier existe vraiment à la racine (ou si on tente quand même?)
             # Pour l'instant, on ne le retourne pas pour éviter erreurs, l'IA devrait donner chemin plus complet.
             # return match.group(1).strip() # Moins sûr
             pass

        return None

    def _resolve_path(self, path_str: str) -> Optional[Path]:
         """Résoud un chemin (potentiellement relatif) en chemin absolu Path DANS le projet."""
         if not path_str: return None
         path = Path(path_str)

         if path.is_absolute():
             # Sécurité: vérifier qu'il est DANS le projet
             try:
                 if self.project_path in path.resolve().parents or self.project_path == path.resolve().parent:
                     return path.resolve()
                 else:
                     logging.warning(f"Chemin absolu '{path_str}' est hors du projet. Ignoré.")
                     return None
             except OSError: # Peut arriver avec des chemins invalides sur Windows
                 logging.warning(f"Chemin absolu '{path_str}' non valide. Ignoré.")
                 return None
         else:
             # C'est un chemin relatif, le joindre au chemin du projet
             abs_path = (self.project_path / path).resolve()
             # Sécurité: re-vérifier qu'on n'est pas sorti avec des ../../..
             if self.project_path in abs_path.parents or self.project_path == abs_path:
                 return abs_path
             else:
                  logging.warning(f"Chemin relatif '{path_str}' résolu hors du projet ('{abs_path}'). Ignoré.")
                  return None

    def _execute_read_file(self, args: str, step_context: str):
        """Exécute l'action READ_FILE."""
        # L'argument 'args' devrait contenir le chemin direct après 'READ_FILE '
        filepath_to_read = args.strip().strip("'\"`")

        if not filepath_to_read:
             logging.warning(f"Action READ_FILE sans chemin de fichier clair dans les arguments ('{args}'). Vérification étape: '{step_context}'")
             # Tenter d'extraire de l'étape complète en dernier recours
             filepath_to_read = self._extract_path_from_step_or_args(step_context)
             if not filepath_to_read:
                 logging.error("Échec READ_FILE: Chemin de fichier manquant ou non extractible.")
                 self.kb.add_note(f"Échec lecture pour étape '{step_context}': Chemin de fichier manquant.")
                 self.kb.add_history(f"Échec lecture (chemin manquant) pour étape: {step_context}")
                 return
             else:
                  logging.info(f"Chemin extrait de l'étape: '{filepath_to_read}'")


        # Résoudre le chemin en absolu et vérifier qu'il est dans le projet
        abs_filepath_obj = self._resolve_path(filepath_to_read)

        if not abs_filepath_obj:
            # Erreur déjà loguée par _resolve_path si hors projet ou invalide
            self.kb.add_note(f"Échec lecture pour étape '{step_context}': Chemin '{filepath_to_read}' invalide ou hors projet.")
            self.kb.add_history(f"Échec lecture (chemin invalide/hors projet: {filepath_to_read}) pour étape: {step_context}")
            return

        abs_filepath_str = str(abs_filepath_obj)
        rel_filepath_str = self.kb._get_relative_path(abs_filepath_str)

        logging.info(f"Action READ_FILE: Tentative lecture de '{rel_filepath_str}'")
        content = self.read_file_content(abs_filepath_str)

        # Gérer le résultat de la lecture
        if content.startswith("Erreur:"):
            logging.error(f"Échec lecture de '{rel_filepath_str}': {content}")
            self.kb.add_note(f"Échec lecture '{rel_filepath_str}': {content}")
            self.kb.add_history(f"Échec lecture '{rel_filepath_str}' ({content.split(':')[1].strip()})")
        else:
            # Ajouter le contenu (même vide ou tronqué) à la KB
            self.kb.add_file_content(abs_filepath_str, content)
            self.kb.add_history(f"Lu fichier '{rel_filepath_str}' ({len(content)} octets{' - tronqué' if 'tronqué' in content else ''})")

            # Demander un résumé à Ollama SEULEMENT si contenu significatif et non tronqué ?
            # Ou toujours demander pour avoir une note ? On va demander si > 50 chars.
            if len(content) > 50 and "tronqué" not in content and not content.startswith("Erreur:"):
                summary_prompt = f"""Voici le contenu du fichier `{rel_filepath_str}`:
                ```
                {content[:1500]}
                ```
                Résume son rôle principal en 1 phrase concise pour le contexte de la question "{self.user_problem}".
                """
                summary = self._ollama_request(summary_prompt, "Tu résumes des fichiers de code de manière très concise en lien avec une question spécifique.")
                if summary:
                    # Nettoyer le résumé
                    summary = summary.split('\n')[0].strip()
                    self.kb.add_note(f"Résumé '{rel_filepath_str}': {summary}")
                else:
                    self.kb.add_note(f"Échec résumé pour '{rel_filepath_str}'.")
            elif "tronqué" in content:
                self.kb.add_note(f"Fichier '{rel_filepath_str}' lu mais tronqué, pas de résumé demandé.")
            elif len(content) <= 50:
                 self.kb.add_note(f"Fichier '{rel_filepath_str}' lu (contenu court ou vide).")


    def _execute_search_code(self, args: str, step_context: str):
        """Exécute une recherche de code réelle en utilisant rg (ripgrep) si disponible, sinon fallback Python."""
        term, search_target_path, search_path_log, search_target_is_file = self._parse_search_args(args, step_context)

        if not term:
            return # Erreur déjà loguée par _parse_search_args

        logging.info(f"Action SEARCH_CODE: Recherche réelle de '{term}' dans {search_path_log}")

        found_results = []
        search_method = "Inconnu"

        # --- Option 1: Utiliser ripgrep (rg) si disponible ---
        rg_path = shutil.which('rg')
        if rg_path:
            search_method = "ripgrep (rg)"
            logging.info(f"Utilisation de {search_method} trouvé à '{rg_path}'")
            command = [
                rg_path,
                '--case-insensitive', # Recherche insensible à la casse
                '--count',            # Compte les occurrences par fichier
                '--no-heading',       # Pas d'en-tête avant les résultats
                '--no-ignore-vcs',    # Ne pas ignorer .git etc par défaut (rg le fait) - Optionnel
                '--glob', '!*'+os.path.sep+'.git'+os.path.sep+'**', # Exclure .git explicitement si besoin
                # Ajouter d'autres exclusions si nécessaire (ex: node_modules si rg ne le fait pas assez)
                # '--glob', '!**/node_modules/**',
                '--',                 # Fin des options, début du pattern et chemin
                term,                 # Le terme à rechercher
                str(search_target_path) # Le chemin où chercher (fichier ou dossier)
            ]
            try:
                # Timeout pour éviter les blocages sur des recherches très longues/complexes
                timeout_seconds = 60
                logging.debug(f"Exécution commande rg: {' '.join(command)}")
                process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=timeout_seconds, check=False) # check=False pour gérer nous-même

                if process.returncode == 0: # Succès, des correspondances ont été trouvées
                    logging.debug(f"rg stdout:\n{process.stdout}")
                    for line in process.stdout.strip().split('\n'):
                        if line:
                            parts = line.split(':', 1) # Split sur le premier ':' seulement
                            if len(parts) == 2:
                                try:
                                    file_path_str = parts[0].strip()
                                    count = int(parts[1].strip())
                                    # Convertir en chemin relatif
                                    rel_path = self.kb._get_relative_path(file_path_str)
                                    found_results.append({'path': rel_path, 'count': count})
                                except ValueError:
                                    logging.warning(f"Impossible de parser la ligne de sortie rg (count): '{line}'")
                                except Exception as e_parse:
                                     logging.warning(f"Erreur parsing ligne rg '{line}': {e_parse}")

                            else:
                                 logging.warning(f"Impossible de parser la ligne de sortie rg (split): '{line}'")
                elif process.returncode == 1: # Aucune correspondance trouvée (comportement normal de rg)
                    logging.info("rg n'a trouvé aucune correspondance.")
                    # found_results reste vide
                else: # Autre code d'erreur
                    logging.error(f"Erreur lors de l'exécution de rg (code {process.returncode}):\n{process.stderr}")
                    self.kb.add_note(f"Erreur recherche '{term}' avec rg: {process.stderr[:200]}...")
                    # Pas d'ajout à l'historique d'erreur ici, sera fait à la fin si found_results est vide

            except FileNotFoundError:
                logging.error(f"La commande '{rg_path}' n'a pas pu être exécutée (FileNotFoundError).")
                search_method = "Erreur (rg non exécutable)"
            except subprocess.TimeoutExpired:
                 logging.error(f"La recherche avec rg a dépassé le délai de {timeout_seconds} secondes.")
                 self.kb.add_note(f"Erreur recherche '{term}' avec rg: Timeout ({timeout_seconds}s)")
                 search_method = "Erreur (rg timeout)"
            except Exception as e:
                 logging.error(f"Erreur inattendue lors de l'exécution de rg: {e}", exc_info=True)
                 self.kb.add_note(f"Erreur recherche '{term}' avec rg: {e}")
                 search_method = f"Erreur (rg: {type(e).__name__})"

        # --- Option 2: Fallback en Pure Python si rg n'est pas trouvé ---
        else:
            search_method = "Pure Python (os.walk)"
            logging.warning(f"ripgrep (rg) non trouvé. Utilisation du fallback {search_method} (peut être plus lent et moins précis sur les exclusions).")

            # Réutiliser les filtres de get_directory_structure
            ignore_dirs_py = {'.git', '.vscode', 'node_modules', '__pycache__', 'venv', '.venv', 'target', 'build', 'dist', 'vendor', '.idea', '.composer', 'cache', 'logs', 'tmp', 'temp'}
            ignore_prefixes_py = ('.', '_')
            ignore_extensions_py = {'.log', '.tmp', '.bak', '.swp', '.map', '.lock', '.DS_Store', '.pyc', '.pyo', '.class', '.o', '.so', '.dll', '.exe', '.jar', '.war', '.ear', '.zip', '.gz', '.tar', '.rar', '.7z', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.mp3', '.wav', '.ogg', '.mp4', '.mov', '.avi', '.webm'}

            try:
                term_lower = term.lower() # Pour recherche insensible à la casse

                if search_target_is_file:
                    # Recherche dans un seul fichier
                    if search_target_path.suffix.lower() not in ignore_extensions_py and not search_target_path.name.startswith(ignore_prefixes_py):
                        count = self._search_in_file(search_target_path, term_lower)
                        if count > 0:
                            rel_path = self.kb._get_relative_path(str(search_target_path))
                            found_results.append({'path': rel_path, 'count': count})
                    else:
                         logging.info(f"Fichier '{search_target_path.name}' ignoré par les règles d'extension/préfixe.")

                else:
                    # Recherche récursive dans un dossier
                    for root, dirs, files in os.walk(str(search_target_path), topdown=True):
                        # Filtrer les dossiers ignorés en place
                        dirs[:] = [d for d in dirs if d not in ignore_dirs_py and not d.startswith(ignore_prefixes_py)]

                        for filename in files:
                            if filename.startswith(ignore_prefixes_py): continue
                            file_path = Path(root) / filename
                            if file_path.suffix.lower() in ignore_extensions_py: continue

                            count = self._search_in_file(file_path, term_lower)
                            if count > 0:
                                rel_path = self.kb._get_relative_path(str(file_path))
                                found_results.append({'path': rel_path, 'count': count})
            except Exception as e:
                 logging.error(f"Erreur inattendue lors de la recherche Python: {e}", exc_info=True)
                 self.kb.add_note(f"Erreur recherche Python pour '{term}': {e}")
                 search_method = f"Erreur (Python: {type(e).__name__})"


        # --- Mettre à jour KB avec les résultats ---
        result_summary = ""
        if found_results:
              found_results.sort(key=lambda x: x['path']) # Trier par chemin
              results_str = ", ".join([f"`{r['path']}` ({r['count']})" for r in found_results])
              # Limiter la longueur de la string de résultats pour la note
              max_res_len = 300
              if len(results_str) > max_res_len: results_str = results_str[:max_res_len] + "..."
              result_summary = f"Trouvé '{term}' dans {len(found_results)} fichier(s) via {search_method}: {results_str}."
              logging.info(f"      {result_summary}")
        else:
             # Vérifier si une erreur s'est produite pendant la recherche
             if "Erreur" in search_method:
                 result_summary = f"Recherche de '{term}' via {search_method} a échoué. Voir logs pour détails."
                 logging.error(f"      {result_summary}")
             else:
                 result_summary = f"Terme '{term}' non trouvé via {search_method} dans {search_path_log}."
                 logging.info(f"      {result_summary}")

        # Ajouter note et historique (ne pas ajouter si erreur déjà notée pendant recherche)
        if "Erreur" not in search_method:
            self.kb.add_note(f"Résultat recherche '{term}' dans {search_path_log} ({search_method}): {result_summary}")
            self.kb.add_history(f"Recherché '{term}' dans {search_path_log} ({search_method}). {'Trouvé' if found_results else 'Non trouvé'}.")
        else:
             # Si erreur, l'erreur spécifique a déjà été ajoutée à la note/log
             self.kb.add_history(f"Tentative recherche '{term}' dans {search_path_log} ({search_method}). Échec.")

    def _parse_search_args(self, args: str, step_context: str) -> tuple:
        """Parse les arguments de SEARCH_CODE et résout le chemin."""
        term = ""
        location_str = "."
        search_target_path = self.project_path
        search_path_log = "projet entier"
        search_target_is_file = False

        # Regex pour parser : groupe 1 = quote, groupe 2 = terme, groupe 4 = location
        match = re.match(r"""^\s*(["'])(.*?)\1\s*(?:dans\s+(.+))?$""", args)
        if match:
            term = match.group(2)
            if match.group(4):
                location_str = match.group(4).strip().strip("'\"`")
        else:
            # Fallback si pas de guillemets (moins fiable)
            logging.warning(f"Arguments SEARCH_CODE ('{args}') sans guillemets autour du terme. Tentative de parsing simple.")
            parts = args.split(" dans ", 1)
            term = parts[0].strip().strip("'\"`")
            if len(parts) > 1:
                location_str = parts[1].strip().strip("'\"`")

        if not term:
           logging.error(f"Échec SEARCH_CODE: Terme de recherche manquant dans les args '{args}' pour l'étape '{step_context}'.")
           self.kb.add_note(f"Échec recherche pour étape '{step_context}': Terme manquant.")
           self.kb.add_history(f"Échec recherche (terme manquant) pour étape: {step_context}")
           return None, None, None, None # Retourner des Nones pour indiquer l'erreur

        # Résoudre le chemin de recherche
        search_path_obj = self._resolve_path(location_str)

        if not search_path_obj:
            logging.warning(f"Chemin de recherche '{location_str}' invalide ou hors projet. Recherche ciblera tout le projet.")
            search_target_path = self.project_path
            search_path_log = f"projet entier (chemin '{location_str}' invalide/hors projet)"
        else:
            search_target_path = search_path_obj
            search_path_log = f"'{self.kb._get_relative_path(str(search_target_path))}'"
            if search_target_path.is_file():
                search_target_is_file = True

        return term, search_target_path, search_path_log, search_target_is_file


    def _search_in_file(self, file_path: Path, term_lower: str) -> int:
        """Fonction utilitaire pour chercher un terme (insensible casse) dans un seul fichier (utilisé par le fallback Python)."""
        count = 0
        try:
            # Lire par blocs pour gérer de gros fichiers sans tout charger en mémoire
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                while True:
                    chunk = f.read(1024 * 1024) # Lire par blocs de 1MB
                    if not chunk:
                        break
                    # Recherche insensible à la casse simple
                    count += chunk.lower().count(term_lower)
                    # # Alternative avec regex (peut être plus lent sur gros blocs)
                    # try:
                    #     matches = re.findall(re.escape(term_lower), chunk, re.IGNORECASE)
                    #     count += len(matches)
                    # except re.error:
                    #      # Si le terme est invalide pour regex, fallback sur count simple
                    #      count += chunk.lower().count(term_lower)

        except FileNotFoundError:
            logging.warning(f"_search_in_file: Fichier non trouvé '{file_path}' (a peut-être été supprimé entre temps).")
            return 0
        except PermissionError:
             logging.warning(f"_search_in_file: Permission refusée pour lire '{file_path}'.")
             return 0
        except OSError as e:
             logging.warning(f"_search_in_file: Erreur OS lors de la lecture de '{file_path}': {e}")
             return 0
        except Exception as e:
             logging.warning(f"_search_in_file: Erreur inattendue lors de la lecture/recherche dans '{file_path}': {e}")
             return 0 # Ignorer le fichier en cas d'erreur de lecture/décodage
        return count

    def _execute_analyze(self, args: str, step_context: str):
        """Exécute l'action ANALYZE en demandant à Ollama."""
        analysis_description = args if args else step_context # Utiliser l'argument ou l'étape complète si args vide
        if not analysis_description:
            logging.error("Échec ANALYZE: Description de l'analyse manquante.")
            self.kb.add_note(f"Échec analyse pour étape '{step_context}': Description manquante.")
            self.kb.add_history(f"Échec analyse (description manquante) pour étape: {step_context}")
            return

        logging.info(f"Action ANALYZE: '{analysis_description}'")
        # Ajouter à l'historique AVANT l'appel à l'IA
        self.kb.add_history(f"Analyse demandée: {analysis_description}")

        # Créer le prompt pour l'analyse
        analysis_prompt = f"""Contexte actuel du projet ({self.kb.project_type} à {self.project_path}):
        {self.kb.get_context_summary(self.user_problem)}
        ---
        Question initiale: "{self.user_problem}"
        ---
        Demande d'analyse spécifique (issue du plan d'exploration):
        "{analysis_description}"
        ---
        Réponds à cette demande d'analyse en te basant **strictement** sur le contexte fourni (structure, fichiers lus, notes, historique). Ne fais PAS de suppositions externes. Sois concis (2-4 phrases maximum). Si le contexte ne permet pas de répondre, indique-le clairement.
        """
        system_analyzer = f"Tu es un assistant IA analysant une base de code {self.kb.project_type}. Réponds de manière concise à une demande d'analyse spécifique en te basant strictement sur le contexte fourni."

        analysis_result = self._ollama_request(analysis_prompt, system_analyzer)

        if analysis_result:
             # Nettoyer la réponse
             analysis_result = analysis_result.strip()
             note = f"Résultat analyse '{analysis_description[:50]}...': {analysis_result}"
             logging.info(f"      {note}")
             self.kb.add_note(note) # Ajouter la conclusion de l'analyse aux notes
        else:
            logging.warning(f"L'analyse demandée pour '{analysis_description[:50]}...' n'a pas retourné de résultat d'Ollama.")
            self.kb.add_note(f"Échec de l'analyse '{analysis_description[:50]}...' (pas de résultat Ollama).")
            # L'historique contient déjà la demande d'analyse.


    def execute_exploration_step(self, step: str) -> bool:
        """Exécute une seule étape du plan (déjà formatée `VERBE args`) et retourne True si FINISH."""
        logging.info(f"--> Exécution étape: {step}")
        step = step.strip() # Assurer pas d'espaces autour

        # Gérer FINISH en premier
        if step.upper() == "FINISH":
             logging.info("      Action FINISH détectée dans le plan.")
             self.kb.add_history("Action FINISH reçue du planificateur.")
             return True # Indique qu'il faut terminer

        # Parser l'action (devrait être déjà bien formatée par plan_exploration)
        action_verb = ""
        action_args = ""
        parts = step.split(' ', 1)
        if parts:
            action_verb = parts[0].upper()
            if len(parts) > 1:
                action_args = parts[1].strip() # Garder les arguments

        # Vérifier si le verbe est connu
        known_verbs = ["READ_FILE", "SEARCH_CODE", "ANALYZE", "SKIP"] # FINISH est géré avant
        if action_verb not in known_verbs:
             # Si l'étape vient directement du plan non parsé, on peut essayer de la faire interpréter par Ollama
             logging.warning(f"Étape du plan non reconnue: '{step}'. Tentative d'interprétation par Ollama...")
             return self._interpret_and_execute_unknown_step(step) # Appeler une fonction de fallback

        # Exécuter l'action correspondante
        try:
            # Noter: On passe 'step' comme contexte au cas où args est incomplet
            if action_verb == "READ_FILE":
                self._execute_read_file(action_args, step)
            elif action_verb == "SEARCH_CODE":
                 self._execute_search_code(action_args, step)
            elif action_verb == "ANALYZE":
                 self._execute_analyze(action_args, step)
            elif action_verb == "SKIP": # SKIP n'est pas une action de plan, mais peut venir de l'interprétation
                logging.info(f"      Étape sautée (indiqué dans le plan ou interprété): {step}")
                self.kb.add_note(f"Étape '{step}' sautée.")
                self.kb.add_history(f"Sauté étape: {step}")

        except Exception as e:
            # Erreur inattendue pendant l'exécution de l'action
            logging.error(f"Erreur lors de l'exécution de l'action {action_verb} pour l'étape '{step}': {e}", exc_info=True)
            self.kb.add_note(f"Erreur exécution étape '{step}' (Action: {action_verb}): {e}")
            self.kb.add_history(f"Erreur exécution action '{action_verb}' pour étape: {step} ({e})")
            # Continuer avec les étapes suivantes ? Oui, pour l'instant.

        return False # Ne pas terminer par défaut


    def _interpret_and_execute_unknown_step(self, step: str) -> bool:
        """Fallback: Demande à Ollama d'interpréter une étape mal formatée et de choisir une action."""
        logging.info(f"   Tentative d'interprétation de l'étape ambiguë: '{step}'")
        context_summary = self.kb.get_context_summary(self.user_problem, include_plan=False)

        action_prompt = f"""
        Contexte (résumé):
        {context_summary}
        ---
        L'étape suivante du plan d'exploration n'est pas dans le format attendu `VERBE arguments`:
        Étape ambiguë: "{step}"
        ---
        Quelle action standard (`READ_FILE <path>`, `SEARCH_CODE "<term>" [dans <loc>]`, `ANALYZE <desc>`, `SKIP`) correspond le mieux à cette étape ambiguë ?
        Si aucune action ne correspond ou si l'étape est invalide (ex: fichier hors contexte), réponds `SKIP`.

        Réponds **UNIQUEMENT** avec la ligne d'action au format `VERBE arguments` ou `SKIP`.
        **NE PAS utiliser de formatage markdown (pas de backticks \`) dans la réponse.**
        """
        system_action = "Interprète une étape de plan ambiguë et choisis l'action standard correspondante (READ_FILE, SEARCH_CODE, ANALYZE, SKIP). Réponds *uniquement* avec la ligne d'action SANS MARKDOWN."

        action_str_raw = self._ollama_request(action_prompt, system_action)

        if not action_str_raw:
            logging.error("      Impossible d'interpréter l'étape ambiguë via Ollama (réponse vide).")
            self.kb.add_note(f"Étape ambiguë '{step}' non interprétée (Ollama n'a pas répondu).")
            self.kb.add_history(f"Échec interprétation étape ambiguë (réponse vide): {step}")
            return False

        # Nettoyer et parser la réponse d'Ollama
        action_str = action_str_raw.strip().strip('`').strip()
        logging.info(f"      Interprétation Ollama pour étape ambiguë: '{action_str}'")

        # Exécuter l'action interprétée (même logique que execute_exploration_step)
        action_verb = ""
        action_args = ""
        parts = action_str.split(' ', 1)
        if parts:
            action_verb = parts[0].upper()
            if len(parts) > 1:
                action_args = parts[1].strip()

        known_verbs = ["READ_FILE", "SEARCH_CODE", "ANALYZE", "SKIP", "FINISH"]
        if action_verb not in known_verbs:
             logging.warning(f"      Interprétation a retourné une action invalide: '{action_str}'")
             self.kb.add_note(f"Étape '{step}': Interprétation a donné une action invalide '{action_str}'")
             self.kb.add_history(f"Action invalide '{action_str}' après interprétation étape: {step}")
             return False

        try:
            if action_verb == "READ_FILE":
                self._execute_read_file(action_args, step) # Passer step original comme contexte
            elif action_verb == "SEARCH_CODE":
                 self._execute_search_code(action_args, step)
            elif action_verb == "ANALYZE":
                 self._execute_analyze(action_args, step)
            elif action_verb == "SKIP":
                logging.info(f"      Étape '{step}' interprétée comme SKIP.")
                self.kb.add_note(f"Étape '{step}' interprétée comme SKIP.")
                self.kb.add_history(f"Sauté étape (interprété comme SKIP): {step}")
            elif action_verb == "FINISH":
                 logging.info("      FINISH interprété pour étape ambiguë.")
                 self.kb.add_history("FINISH interprété pour étape ambiguë.")
                 return True
        except Exception as e:
            logging.error(f"      Erreur lors de l'exécution de l'action interprétée {action_str}: {e}", exc_info=True)
            self.kb.add_note(f"Erreur pendant étape '{step}' (Action interprétée: {action_str}): {e}")
            self.kb.add_history(f"Erreur exécution action interprétée '{action_verb}' pour étape: {step} ({e})")

        return False # Ne pas terminer par défaut


    def evaluate_progress(self) -> bool:
        """Demande à Ollama si le problème semble résolu avec le contexte actuel."""
        logging.info("-> Évaluation de la progression pour répondre à: '{self.user_problem}'")
        context_summary = self.kb.get_context_summary(self.user_problem, include_plan=False) # Plan pas utile ici

        eval_prompt = f"""
        Contexte collecté jusqu'à présent pour répondre à la question : "{self.user_problem}"
        ```
        {context_summary}
        ```
        ---
        Question pour l'IA: Penses-tu avoir suffisamment d'informations **fiables et vérifiées** dans le contexte ci-dessus pour fournir une réponse **complète et précise** à la question initiale de l'utilisateur ?

        Réponds **uniquement** par "OUI" ou "NON". Ne justifie PAS ta réponse.
        """
        system_eval = "Évalue si les informations collectées sont suffisantes pour répondre à une question spécifique sur une base de code. Réponds strictement par OUI ou NON."

        evaluation = self._ollama_request(eval_prompt, system_eval)

        if evaluation:
            # Nettoyer la réponse (peut contenir des points, etc.)
            eval_clean = evaluation.strip().upper().rstrip('.')
            logging.info(f"   Évaluation Ollama: '{evaluation}' -> '{eval_clean}'")
            if eval_clean == "OUI":
                logging.info("   Ollama estime avoir assez d'informations.")
                return True
            elif eval_clean == "NON":
                 logging.info("   Ollama estime ne pas avoir assez d'informations.")
                 return False
            else:
                 logging.warning(f"   Réponse d'évaluation non standard ('{evaluation}'). On considère NON.")
                 return False
        else:
            logging.error("   Impossible d'obtenir une évaluation d'Ollama. On considère NON.")
            # Ajouter une note sur l'échec de l'évaluation ?
            self.kb.add_note("Échec de l'évaluation de la progression par Ollama.")
            return False


    def generate_final_explanation(self, termination_reason: str):
        """Demande à Ollama de générer l'explication finale basée sur TOUT le contexte collecté."""
        logging.info("4. Génération de l'explication finale...")
        # Utiliser le contexte complet SANS le plan d'exploration (qui n'est plus pertinent)
        context_summary = self.kb.get_context_summary(self.user_problem, include_plan=False)

        explanation_prompt = f"""
        Voici le résumé complet du contexte collecté lors de l'exploration de la base de code `{self.kb.project_path}` (type: {self.kb.project_type}) pour répondre à la demande : "{self.user_problem}"
        ```
        {context_summary}
        ```
        ---
        L'exploration s'est terminée pour la raison suivante: "{termination_reason}"
        ---
        INSTRUCTIONS POUR L'EXPLICATION FINALE:
        1. Synthétise TOUTES les informations pertinentes du contexte pour répondre directement et clairement à la question initiale de l'utilisateur: "{self.user_problem}".
        2. Structure ta réponse de manière logique (étapes, points clés).
        3. **Cite les fichiers pertinents** (avec leur chemin relatif, ex: `application/model/Song.php`) et les découvertes clés (contenu de fichier, résultats de recherche, conclusions d'analyse) pour appuyer ton explication.
        4. Base-toi **strictement** sur le contexte fourni. Ne fais PAS de suppositions externes ou n'invente pas d'informations non présentes dans le résumé.
        5. Si l'exploration s'est arrêtée avant d'avoir une réponse complète (ex: limite d'itérations, fichiers clés non trouvés/illisibles), **indique-le clairement**. Explique ce qui a été trouvé, ce qui manque, et suggère éventuellement comment continuer l'investigation manuellement si pertinent.
        6. Adapte le niveau de détail à la complexité de la question et des informations trouvées. Sois aussi précis que le contexte le permet.
        """
        system_explainer = f"Tu es un assistant IA expert en code {self.kb.project_type}. Tu expliques clairement une solution ou un fonctionnement technique en te basant **strictement** sur l'analyse de code fournie dans le contexte. Adapte ta réponse si l'analyse est incomplète en indiquant ce qui manque."

        final_explanation = self._ollama_request(explanation_prompt, system_explainer)

        print("\n--- Explication Générée ---")
        if final_explanation:
            print(final_explanation)
        else:
            print("   Erreur: Impossible de générer l'explication finale via Ollama.")
            logging.error("Impossible de générer l'explication finale.")
            # Afficher le contexte brut comme fallback ?
            print("\n   Contexte final collecté (Fallback car explication échouée) :\n", context_summary)
        print("--- Fin de l'Explication ---\n")


    def run(self):
        """Orchestre l'exécution complète de l'agent : analyse, planification, exploration en boucle, explication."""
        # --- Demande Utilisateur ---
        self.user_problem = ""
        while not self.user_problem:
             self.user_problem = input("Quel problème souhaitez-vous résoudre ou quel fonctionnement souhaitez-vous comprendre ?\n> ").strip()
             if not self.user_problem:
                 print("La question ne peut pas être vide.")

        logging.info(f"Lancement de l'analyse pour : '{self.user_problem}' dans {self.project_path}")

        # --- 1. Analyse Initiale ---
        try:
            self.analyze_initial_context()
        except Exception as e:
             logging.critical(f"Erreur critique lors de l'analyse initiale: {e}", exc_info=True)
             print(f"\nErreur critique pendant l'analyse initiale: {e}")
             return # Arrêter l'agent si l'analyse initiale échoue

        # --- 2. Planification Initiale ---
        # Utiliser le contexte après l'analyse initiale
        initial_context = self.kb.get_context_summary(self.user_problem, include_plan=False)
        try:
            self.plan_exploration(initial_context)
        except Exception as e:
             logging.critical(f"Erreur critique lors de la planification initiale: {e}", exc_info=True)
             print(f"\nErreur critique pendant la planification initiale: {e}")
             return # Arrêter l'agent

        # --- 3. Boucle d'Exploration & Évaluation ---
        iteration = 0
        termination_reason = "Raison inconnue"
        max_iterations = MAX_EXPLORATION_ITERATIONS

        while iteration < max_iterations:
            iteration += 1
            logging.info(f"\n--- Début Itération d'Exploration {iteration}/{max_iterations} ---")

            if not self.kb.exploration_plan:
                logging.warning(f"Aucun plan à exécuter pour l'itération {iteration}. Tentative de re-planification.")
                current_context = self.kb.get_context_summary(self.user_problem, include_plan=False)
                self.plan_exploration(current_context)
                if not self.kb.exploration_plan:
                     logging.error("Échec de la re-planification. Arrêt de l'exploration.")
                     termination_reason = "Aucun plan d'exploration généré ou valide."
                     break # Sortir de la boucle while

            # Copier le plan actuel pour l'exécution et vider pour le prochain cycle
            plan_to_execute = self.kb.exploration_plan[:]
            self.kb.set_plan([]) # Prépare pour une éventuelle replanification
            logging.info(f"Plan pour itération {iteration}: {len(plan_to_execute)} étape(s)")

            finish_requested = False
            for step_index, step in enumerate(plan_to_execute):
                logging.info(f"Itération {iteration}, Étape {step_index + 1}/{len(plan_to_execute)}")
                try:
                    finish_requested = self.execute_exploration_step(step)
                    if finish_requested:
                         termination_reason = "Action FINISH rencontrée ou interprétée."
                         logging.info(f"FINISH demandé pendant l'itération {iteration}. Arrêt de l'exploration.")
                         break # Sortir de la boucle for (étapes du plan)
                except Exception as e:
                     # Erreur inattendue non capturée dans execute_exploration_step
                     logging.critical(f"Erreur critique non gérée pendant l'exécution de l'étape '{step}': {e}", exc_info=True)
                     self.kb.add_note(f"Erreur critique pendant étape '{step}': {e}")
                     self.kb.add_history(f"Erreur critique étape '{step}': {e}")
                     # Que faire ? Arrêter tout ? Continuer ? Pour l'instant on continue avec les étapes/itérations suivantes.
                     # finish_requested = True # Option: considérer une erreur critique comme un arrêt
                     # termination_reason = f"Erreur critique pendant l'étape: {e}"
                     # break

            if finish_requested:
                 break # Sortir de la boucle while (itérations)

            # --- Évaluation après l'exécution du plan de l'itération ---
            if self.evaluate_progress():
                termination_reason = "L'IA estime avoir trouvé la réponse."
                logging.info(f"Évaluation positive à la fin de l'itération {iteration}. Arrêt de l'exploration.")
                break
            else:
                # Si on n'a pas fini et qu'on n'a pas atteint la limite d'itérations, on replanifie
                if iteration < max_iterations:
                    logging.info(f"Fin de l'itération {iteration}. Re-planification nécessaire.")
                    current_context = self.kb.get_context_summary(self.user_problem, include_plan=False)
                    try:
                        self.plan_exploration(current_context)
                        # Si le nouveau plan est vide, la boucle s'arrêtera au début de la prochaine itération.
                    except Exception as e:
                         logging.critical(f"Erreur critique lors de la re-planification (itération {iteration}): {e}", exc_info=True)
                         print(f"\nErreur critique pendant la re-planification: {e}")
                         termination_reason = f"Erreur critique pendant la re-planification: {e}"
                         break # Arrêter la boucle

        # --- Fin de la boucle ---
        else:
            # La boucle s'est terminée car max_iterations a été atteint
            logging.warning(f"Limite de {max_iterations} itérations atteinte.")
            termination_reason = f"Limite de {max_iterations} itérations atteinte."

        # --- 4. Génération de l'Explication Finale ---
        try:
            self.generate_final_explanation(termination_reason)
        except Exception as e:
            logging.critical(f"Erreur critique lors de la génération de l'explication finale: {e}", exc_info=True)
            print(f"\nErreur critique pendant la génération de l'explication: {e}")
            # Afficher au moins la raison de l'arrêt
            print(f"\nL'exploration s'est terminée ({termination_reason}) mais l'explication finale n'a pu être générée.")


        logging.info(f"Analyse terminée ({termination_reason}).")


# --- Programme Principal ---
if __name__ == "__main__":
    agent = None # Pour le bloc finally
    try:
        # Utiliser un chemin par défaut pour faciliter les tests, ou demander
        # default_folder = "." # Dossier courant par défaut
        # Trouver un chemin par défaut plus robuste (ex: le dossier du script)
        script_dir = Path(__file__).parent.resolve()
        default_folder = str(script_dir) # Ou str(script_dir.parent) si les projets sont à côté

        user_input_folder = input(f"Entrez le chemin du dossier projet (laissez vide pour utiliser '{default_folder}'):\n> ").strip()
        if not user_input_folder:
            project_folder = default_folder
        else:
            project_folder = user_input_folder

        # Vérifier si le dossier existe avant de créer l'agent
        if not Path(project_folder).is_dir():
             print(f"\nErreur: Le dossier '{project_folder}' n'existe pas ou n'est pas accessible.")
             exit(1) # Quitter si le dossier n'est pas valide

        print(f"Utilisation du dossier projet: {Path(project_folder).resolve()}")
        agent = OllamaCodingAgent(project_folder)
        agent.run()

    except ValueError as ve:
        # Erreur de configuration attrapée par l'init de l'agent
        logging.error(f"Erreur de configuration: {ve}")
        print(f"\nErreur: {ve}")
    except FileNotFoundError:
         # Devrait être attrapé avant maintenant, mais sécurité
         logging.error(f"Erreur: Le dossier spécifié n'a pas été trouvé.")
         print(f"\nErreur: Le dossier spécifié n'a pas été trouvé.")
    except KeyboardInterrupt:
         logging.info("Arrêt demandé par l'utilisateur (Ctrl+C).")
         print("\nArrêt demandé.")
         if agent: # Si l'agent a été initialisé, essayer de donner une conclusion partielle?
             print("\nTentative de génération d'une conclusion basée sur l'état actuel...")
             agent.generate_final_explanation("Arrêt par l'utilisateur (Ctrl+C)")
    except Exception as e:
        # Attraper toutes les autres erreurs inattendues
        logging.critical(f"Une erreur inattendue et non gérée est survenue: {e}", exc_info=True)
        print(f"\nUne erreur critique est survenue: {e}")
        # Si l'agent existe, on peut peut-être logger son état ?
        # if agent and agent.kb:
        #    logging.error(f"État final KB avant crash: {agent.kb.__dict__}")


    finally:
         logging.info("Fin du script.")
         print("\nScript terminé.")
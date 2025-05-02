import ollama
import os
import json
import re
from pathlib import Path
import logging
from typing import Dict, List, Optional, Any
import subprocess
import shutil
import fnmatch

# --- Configuration du Logging ---
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration Globale ---
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'gemma3:latest')
MAX_FILE_READ_SIZE = int(os.environ.get('MAX_FILE_READ_SIZE', 150000))
MAX_EXPLORATION_ITERATIONS = int(os.environ.get('MAX_EXPLORATION_ITERATIONS', 6))
MAX_DIR_DEPTH = int(os.environ.get('MAX_DIR_DEPTH', 5))
MAX_PROMPT_LENGTH = int(os.environ.get('MAX_PROMPT_LENGTH', 7500))

class KnowledgeBase:
    """Structure pour stocker les informations collectées pendant l'analyse."""
    def __init__(self, project_path: Path):
        self.project_path: Path = project_path.resolve()
        self.project_structure: Optional[Dict[str, Any]] = None
        self.project_type: str = "Inconnu"
        self.readme_content: Optional[str] = None
        self.file_contents: Dict[str, str] = {}
        self.analysis_notes: List[str] = []
        self.exploration_plan: List[str] = []
        self.exploration_history: List[str] = []

    def _get_relative_path(self, abs_filepath_str: str) -> str:
        """Convertit un chemin absolu en chemin relatif au projet."""
        try:
            abs_path = Path(abs_filepath_str).resolve()
            if self.project_path in abs_path.parents or self.project_path == abs_path.parent or self.project_path == abs_path:
                 if self.project_path == abs_path:
                     return "."
                 return str(abs_path.relative_to(self.project_path))
            else:
                 return Path(abs_filepath_str).name # Fallback
        except ValueError:
             return Path(abs_filepath_str).name # Fallback
        except Exception:
            return abs_filepath_str # Fallback

    def add_file_content(self, abs_filepath: str, content: str):
        """Ajoute le contenu d'un fichier à la base de connaissances."""
        relative_path = self._get_relative_path(abs_filepath)
        self.file_contents[relative_path] = content
        logging.info(f"Contenu ajouté/mis à jour pour '{relative_path}'")

    def add_note(self, note: str):
        """Ajoute une note d'analyse."""
        if not self.analysis_notes or note != self.analysis_notes[-1]:
            self.analysis_notes.append(note)
            logging.info(f"Note ajoutée: {note[:100]}...")
        else:
            logging.debug(f"Note dupliquée ignorée: {note[:100]}...")

    def add_history(self, action_description: str):
        """Ajoute une action à l'historique."""
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
        if plan:
            logging.info("Nouveau plan d'exploration défini.")

    def get_context_summary(self, user_problem: str, include_plan: bool = False) -> str:
        """Génère un résumé du contexte pour les prompts Ollama, en limitant la taille."""
        summary = f"Problème utilisateur: \"{user_problem}\"\n"
        summary += f"Projet: {self.project_path.name} (Type: {self.project_type})\n"

        if self.project_structure:
             try:
                 structure_str = json.dumps(self.project_structure, indent=1, ensure_ascii=False, separators=(',', ': '))
                 MAX_STRUCTURE_LEN_PROMPT = 1800
                 if len(structure_str) > MAX_STRUCTURE_LEN_PROMPT:
                     structure_str = structure_str[:MAX_STRUCTURE_LEN_PROMPT] + "\n...(structure tronquée)"
                 summary += f"\nStructure Projet (partielle):\n```json\n{structure_str}\n```\n"
             except Exception as e:
                 summary += f"\nStructure Projet: (Erreur formatage: {e})\n"

        summary += "\nFichiers Lus (Extraits):\n"
        if not self.file_contents:
            summary += "(Aucun)\n"
        else:
            count = 0
            MAX_FILES_IN_PROMPT = 5
            sorted_files = sorted(self.file_contents.items())
            for path, content in sorted_files:
                 excerpt = content[:80].replace('`','').replace('\n',' ').strip()
                 summary += f"- `{path}`: {excerpt}...\n"
                 count += 1
                 if count >= MAX_FILES_IN_PROMPT:
                     summary += f"... et {len(self.file_contents) - count} autres fichiers lus.\n"
                     break

        summary += "\nHistorique/Notes Récentes:\n"
        combined_info = self.analysis_notes + self.exploration_history
        if not combined_info:
            summary += "(Aucun)\n"
        else:
            MAX_HISTORY_IN_PROMPT = 8
            start_index = max(0, len(combined_info) - MAX_HISTORY_IN_PROMPT)
            displayed_items = combined_info[start_index:]
            for info in displayed_items:
                 summary += f"- {info[:100]}\n"
            if start_index > 0:
                 summary += f"... ({start_index} actions/notes précédentes omises)\n"

        if include_plan and self.exploration_plan:
             summary += "\nPlan Actuel:\n"
             plan_text = "\n".join(f"{i+1}. {step}" for i, step in enumerate(self.exploration_plan))
             summary += plan_text[:300] + ("..." if len(plan_text) > 300 else "") + "\n"

        logging.debug(f"Taille finale du résumé contexte pour prompt: {len(summary)} caractères.")
        if len(summary) > MAX_PROMPT_LENGTH - 500:
            logging.warning(f"Résumé contexte ({len(summary)} caractères) toujours potentiellement trop long pour MAX_PROMPT_LENGTH={MAX_PROMPT_LENGTH}.")

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
        if len(prompt) > MAX_PROMPT_LENGTH:
            chars_to_cut = len(prompt) - MAX_PROMPT_LENGTH
            prompt = prompt[:-chars_to_cut]
            if chars_to_cut > 100:
                logging.warning(f"Prompt tronqué à {MAX_PROMPT_LENGTH} caractères (supprimé {chars_to_cut} de la fin).")
            prompt += "\n... (Fin du prompt tronquée)"

        logging.debug(f"Appel Ollama - Système: '{system_message}' - Prompt (taille={len(prompt)}, début): '{prompt[:150].replace(chr(10),' ')}...'")
        try:
            messages = []
            if system_message:
                messages.append({'role': 'system', 'content': system_message})
            messages.append({'role': 'user', 'content': prompt})
            response = ollama.chat(model=OLLAMA_MODEL, messages=messages)

            if 'message' in response and 'content' in response['message']:
                content = response['message']['content'].strip()
                logging.debug(f"Réponse Ollama (taille={len(content)}, début): {content[:150].replace(chr(10),' ')}...")
                return content
            else:
                logging.error(f"Réponse inattendue d'Ollama: {response}")
                return None
        except Exception as e:
            logging.error(f"Erreur lors de l'appel à Ollama: {e}", exc_info=True)
            return None

    def get_directory_structure(self, root_dir: Path, max_depth=MAX_DIR_DEPTH, current_depth=0) -> Dict[str, Any]:
        """Récupère la structure récursivement, en filtrant et limitant la profondeur."""
        structure = {}
        if current_depth >= max_depth:
            return {"...": f"(limite de profondeur {max_depth} atteinte)"}
        try:
            ignore_dirs = {'.git', '.vscode', 'node_modules', '__pycache__', 'venv', '.venv', 'target', 'build', 'dist', 'vendor', '.idea', '.composer', 'cache', 'logs', 'tmp', 'temp'}
            ignore_prefixes = ('.', '_')
            ignore_extensions = {'.log', '.tmp', '.bak', '.swp', '.map', '.lock', '.DS_Store', '.pyc', '.pyo', '.class', '.o', '.so', '.dll', '.exe', '.jar', '.war', '.ear', '.zip', '.gz', '.tar', '.rar', '.7z', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp'}
            media_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.mp3', '.wav', '.ogg', '.mp4', '.mov', '.avi', '.webm'}
            ignore_extensions.update(media_extensions)

            items_to_process = []
            for entry in os.scandir(root_dir):
                if entry.name not in ignore_dirs and not entry.name.startswith(ignore_prefixes):
                    items_to_process.append(entry)
            items_to_process.sort(key=lambda x: (not x.is_dir(), x.name.lower()))

            for entry in items_to_process:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        structure[entry.name + '/'] = self.get_directory_structure(Path(entry.path), max_depth, current_depth + 1)
                    elif entry.is_file(follow_symlinks=True):
                        file_path = Path(entry.path)
                        if file_path.suffix.lower() not in ignore_extensions:
                            try:
                                size = entry.stat().st_size
                                structure[entry.name] = f"{size} bytes"
                            except OSError:
                                structure[entry.name] = "Erreur lecture taille"
                except OSError as e:
                    structure[entry.name] = f"Erreur d'accès ({e.strerror})"
                except Exception as e:
                    structure[entry.name] = f"Erreur inattendue ({type(e).__name__})"
        except PermissionError:
            return {"ERREUR": f"Permission refusée pour lister le dossier '{root_dir.name}'"}
        except FileNotFoundError:
             return {"ERREUR": f"Dossier '{root_dir.name}' non trouvé pendant le listage"}
        except Exception as e:
             return {"ERREUR": f"Erreur inattendue lors du listage de '{root_dir.name}': {e}"}

        if not structure and current_depth < max_depth :
             if 'ERREUR' not in structure :
                 return {"(vide ou contenu ignoré)": ""}
        return structure

    def read_file_content(self, abs_filepath_str: str) -> str:
        """Lit le contenu d'un fichier (chemin absolu), avec gestion d'erreurs, de taille et de casse."""
        original_input_path_str = abs_filepath_str
        try:
            try:
                initial_abs_path = Path(abs_filepath_str).resolve()
            except Exception as e_resolve:
                 logging.error(f"Erreur lors de la résolution du chemin '{abs_filepath_str}': {e_resolve}")
                 return f"Erreur: Chemin '{abs_filepath_str}' invalide: {e_resolve}"

            logging.debug(f"Tentative de lecture. Chemin initial résolu: {initial_abs_path}")

            resolved_project_path = self.project_path.resolve()
            if not (resolved_project_path in initial_abs_path.parents or resolved_project_path == initial_abs_path.parent or resolved_project_path == initial_abs_path):
                 error_msg = f"Erreur Sécurité: Tentative de lecture hors du dossier projet: '{initial_abs_path}' (depuis l'entrée '{original_input_path_str}')"
                 logging.error(error_msg)
                 return error_msg

            abs_filepath_to_use = initial_abs_path
            if not abs_filepath_to_use.is_file():
                logging.warning(f"Le chemin sensible à la casse '{abs_filepath_to_use}' n'est pas un fichier. Recherche insensible à la casse...")
                parent_dir = abs_filepath_to_use.parent
                target_name_lower = abs_filepath_to_use.name.lower()
                found_alternative = None

                if parent_dir.is_dir():
                    try:
                        for item in parent_dir.iterdir():
                            if item.is_file() and item.name.lower() == target_name_lower:
                                logging.warning(f"Correspondance insensible à la casse trouvée: '{item.name}'. Utilisation de ce chemin.")
                                found_alternative = item
                                break
                    except OSError as e_list:
                        logging.warning(f"Impossible de lister le dossier '{parent_dir}' pour la recherche insensible à la casse: {e_list}")

                if found_alternative:
                    abs_filepath_to_use = found_alternative
                else:
                    rel_path_for_error = self.kb._get_relative_path(str(initial_abs_path))
                    error_msg = f"Erreur: '{rel_path_for_error}' n'est pas un fichier valide ou n'existe pas (même en ignorant la casse)."
                    logging.error(error_msg + f" (Chemin absolu testé: {initial_abs_path})")
                    return error_msg

            try:
                size = abs_filepath_to_use.stat().st_size
                logging.debug(f"Fichier '{abs_filepath_to_use.name}' trouvé, taille: {size} bytes.")
            except OSError as e_stat:
                error_msg = f"Erreur: Impossible d'obtenir la taille de '{self.kb._get_relative_path(str(abs_filepath_to_use))}': {e_stat}"
                logging.error(error_msg)
                return error_msg

            if size == 0:
                logging.info(f"Fichier '{self.kb._get_relative_path(str(abs_filepath_to_use))}' est vide.")
                return ""

            is_binary = False
            try:
                with open(abs_filepath_to_use, 'rb') as f_test:
                    chunk = f_test.read(1024)
                    if b'\x00' in chunk:
                        is_binary = True
                        rel_path_binary = self.kb._get_relative_path(str(abs_filepath_to_use))
                        logging.warning(f"Fichier '{rel_path_binary}' semble être binaire, lecture ignorée.")
                        return f"Erreur: Fichier '{rel_path_binary}' semble binaire."
            except Exception as e_bin_check:
                 logging.warning(f"Impossible de vérifier si '{self.kb._get_relative_path(str(abs_filepath_to_use))}' est binaire: {e_bin_check}")

            rel_path_reading = self.kb._get_relative_path(str(abs_filepath_to_use))
            if size > MAX_FILE_READ_SIZE:
                logging.warning(f"Fichier '{rel_path_reading}' ({size} octets > {MAX_FILE_READ_SIZE}) est trop volumineux. Lecture partielle.")
                try:
                    with open(abs_filepath_to_use, 'r', encoding='utf-8', errors='ignore') as f:
                        start_content = f.read(MAX_FILE_READ_SIZE // 2)
                        f.seek(max(MAX_FILE_READ_SIZE // 2, size - (MAX_FILE_READ_SIZE // 2)))
                        end_content = f.read(MAX_FILE_READ_SIZE // 2)
                        if f.tell() < size - 1:
                             return f"{start_content}\n\n[... contenu tronqué (fichier trop volumineux) ...]\n\n{end_content}"
                        else:
                            return start_content + "\n[... fin du fichier tronquée ...]"
                except Exception as e_read_partial:
                    error_msg = f"Erreur lors de la lecture partielle de '{rel_path_reading}': {e_read_partial}"
                    logging.error(error_msg)
                    return error_msg
            else:
                logging.info(f"Lecture complète du fichier '{rel_path_reading}' ({size} octets).")
                try:
                    with open(abs_filepath_to_use, 'r', encoding='utf-8', errors='ignore') as f:
                        return f.read()
                except Exception as e_read_full:
                    error_msg = f"Erreur lors de la lecture complète de '{rel_path_reading}': {e_read_full}"
                    logging.error(error_msg)
                    return error_msg

        except Exception as e_global:
            logging.error(f"Erreur inattendue lors de la tentative de lecture de '{original_input_path_str}': {e_global}", exc_info=True)
            return f"Erreur inattendue lors de la lecture de '{original_input_path_str}': {e_global}"

    # --- MÉTHODE RESTAURÉE ---
    def analyze_initial_context(self):
        """Analyse initiale : structure, README, type de projet."""
        logging.info("1. Analyse initiale du projet...")
        # --- Structure du répertoire ---
        project_structure_data = self.get_directory_structure(self.project_path)
        self.kb.project_structure = project_structure_data # Stocker dans KB
        logging.debug(f"Structure complète détectée:\n{json.dumps(project_structure_data, indent=2, ensure_ascii=False)}")
        structure_summary_for_log = json.dumps(project_structure_data, indent=1, ensure_ascii=False, separators=(',', ': ')) # Compact
        if len(structure_summary_for_log) > 1000:
            structure_summary_for_log = structure_summary_for_log[:1000] + "\n... (structure log tronquée)"
        logging.info(f"Structure détectée (partielle pour log):\n{structure_summary_for_log}")

        # --- Lecture du README ---
        readme_path_abs = None
        found_readme = False
        for fname_pattern in ['readme.md', 'README.md', 'readme.*', 'README.*']:
             potential_readmes = sorted(list(self.project_path.glob(fname_pattern)), key=lambda p: p.suffix.lower() != '.md')
             if potential_readmes:
                 readme_path_abs = str(potential_readmes[0].resolve())
                 found_readme = True
                 break

        if found_readme:
            readme_rel_path = self.kb._get_relative_path(readme_path_abs)
            logging.info(f"Lecture du fichier README trouvé: '{readme_rel_path}'...")
            readme_content = self.read_file_content(readme_path_abs) # Utilise notre fonction robuste
            if not readme_content.startswith("Erreur:"):
                # Ajouter le contenu à la KB (sera fait par _execute_read_file plus tard si planifié, mais utile pour contexte initial)
                self.kb.add_file_content(readme_path_abs, readme_content)
                self.kb.readme_content = readme_content[:500] # Garder juste un extrait
                self.kb.add_history(f"Lu le fichier README '{readme_rel_path}' lors de l'analyse initiale.")
            else:
                 logging.warning(f"Impossible de lire le README '{readme_rel_path}': {readme_content}")
                 self.kb.add_history(f"Échec lecture README '{readme_rel_path}' lors analyse initiale.")
        else:
            logging.info("Aucun fichier README standard trouvé à la racine.")
            self.kb.add_history("Aucun fichier README trouvé lors analyse initiale.")

        # --- Identification Type/Stack Projet par Ollama ---
        context_for_type_prompt = f"Problème utilisateur: \"{self.user_problem}\"\n"
        context_for_type_prompt += f"Chemin du projet: {self.project_path.name}\n" # Nom du projet suffit peut-être
        if self.kb.project_structure:
            # Utiliser la même structure limitée que get_context_summary
            structure_str_type = json.dumps(self.kb.project_structure, indent=1, ensure_ascii=False, separators=(',', ': '))
            MAX_STRUCTURE_LEN_TYPE_PROMPT = 1500
            if len(structure_str_type) > MAX_STRUCTURE_LEN_TYPE_PROMPT:
                structure_str_type = structure_str_type[:MAX_STRUCTURE_LEN_TYPE_PROMPT] + "\n...(structure tronquée)"
            context_for_type_prompt += f"\nStructure Projet (partielle):\n```json\n{structure_str_type}\n```\n"
        else:
             context_for_type_prompt += "\nStructure Projet: (non disponible ou vide)\n"

        important_files = ["composer.json", "package.json", "requirements.txt", "pom.xml", "go.mod", "Gemfile", "Cargo.toml", "build.gradle", "Makefile"]
        root_files_context = "Fichiers notables à la racine:\n"
        found_notable = False
        for imp_file in important_files:
            imp_path = self.project_path / imp_file
            if imp_path.is_file():
                 try:
                    size = imp_path.stat().st_size
                    root_files_context += f"- {imp_file} ({size} bytes)\n"
                    found_notable = True
                 except OSError:
                    root_files_context += f"- {imp_file} (accès impossible)\n"
        if found_notable:
             context_for_type_prompt += root_files_context
        else:
             root_files_context += "(aucun fichier de dépendance commun trouvé)\n"
             context_for_type_prompt += root_files_context


        type_prompt = f"""
        Contexte initial du projet `{self.project_path.name}`:
        {context_for_type_prompt}
        ---
        Basé **uniquement** sur la structure de fichiers/dossiers fournie et les fichiers racine notables (NE PAS utiliser le contenu du README pour l'instant), quelle est la stack technique principale et le type de ce projet (ex: Web Backend PHP avec Composer, Frontend React avec npm, Application CLI Python, etc.) ?
        Sois bref et direct (1 phrase maximum).
        """
        system_type = "Tu identifies la stack technique et le type d'un projet logiciel **uniquement** d'après sa structure de fichiers/dossiers et les fichiers de configuration racine. Réponds en une seule phrase."
        project_type_guess = self._ollama_request(type_prompt, system_type)

        if project_type_guess:
            project_type_guess = project_type_guess.split('\n')[0].strip()
            project_type_guess = re.sub(r"^(Basé sur.*?, |Il semble que |Le projet est |This appears to be )", "", project_type_guess, flags=re.IGNORECASE).strip()
            self.kb.set_project_type(project_type_guess)
            self.kb.add_note(f"Analyse initiale type/stack (basée structure): {project_type_guess}")
            self.kb.add_history(f"Type de projet estimé (structure): {project_type_guess}")
        else:
             self.kb.add_note("Échec de l'identification initiale du type de projet.")
             self.kb.add_history("Échec identification type projet initial.")
        logging.info(f"Type de projet estimé (structure): {self.kb.project_type}")
    # --- FIN MÉTHODE RESTAURÉE ---

    def plan_exploration(self, current_context: str):
        """Demande à Ollama de créer ou raffiner un plan, avec parsing TRES tolérant."""
        logging.info("-> Planification/Re-planification de l'exploration...")
        plan_prompt = f"""
        OBJECTIF: Répondre à la question utilisateur : "{self.user_problem}"
        PROJET: Type estimé '{self.kb.project_type}' situé à `{self.project_path.name}`.
        CONTEXTE ACTUEL (Structure limitée, Fichiers lus courts, Historique court):
        ```
        {current_context}
        ```
        ---
        HISTORIQUE RÉCENT (5 dernières actions/notes):
        {chr(10).join(f'- {h}' for h in (self.kb.analysis_notes + self.kb.exploration_history)[-5:]) if (self.kb.analysis_notes + self.kb.exploration_history) else "(aucune action/note récente)"}
        ---
        INSTRUCTIONS POUR LE PLAN (RAPPEL IMPORTANT):
        1. Propose 3-5 prochaines étapes **logiques** pour l'objectif.
        2. **BASE-TOI STRICTEMENT sur la structure fournie.** N'invente PAS de fichiers.
        3. Indique des actions claires utilisant les verbes `READ_FILE`, `SEARCH_CODE`, `ANALYZE`. Utilise des chemins **relatifs**.
        4. Si l'objectif semble atteint, propose **UNIQUEMENT** `FINISH`.
        5. **Format de sortie IMPERATIF:** Liste numérotée simple, une action par ligne. **AUCUN blabla, AUCUNE justification, AUCUN markdown (`**`, `` ` ``).**
           Exemple :
           1. READ_FILE main.py
           2. SEARCH_CODE "ma_fonction" dans main.py
           3. ANALYZE comment les arguments sont passés
        """
        system_plan = f"Tu es un assistant expert en code {self.kb.project_type}. Tu planifies une exploration pour répondre à : '{self.user_problem}'. Tu DOIS répondre **UNIQUEMENT** avec la liste numérotée des actions au format `VERBE arguments` SANS AUCUN TEXTE ADDITIONNEL NI MARKDOWN."

        plan_str = self._ollama_request(plan_prompt, system_plan)
        if plan_str:
            plan_list = []
            potential_finish = False
            action_pattern = re.compile(
                r"""
                ^\s*\d+\.\s*
                .*?
                (?:
                   (?P<verb>READ_FILE|SEARCH_CODE|ANALYZE)\s+(?P<args1>.*) |
                   (?:Lire|Read|Examiner|Explorer|Revoir)\s*[:\*]*\s*(?P<args_read>(?:`[^`]+`|'[^']+'|"[^"]+"|\S+?\.\w+).*)|
                   (?:Chercher|Search)\s*[:\*]*\s*(?P<args_search>.*?)(?:\s+dans\s+.*)? |
                   (?:Analyser|Analyze)\s*[:\*]*\s*(?P<args_analyze>.*)
                )
                """, re.IGNORECASE | re.VERBOSE
            )
            raw_lines = [line.strip() for line in plan_str.split('\n') if line.strip()]

            if len(raw_lines) == 1 and raw_lines[0].upper().strip() == "FINISH":
                 potential_finish = True

            if not potential_finish:
                for line in raw_lines:
                    match = action_pattern.search(line)
                    extracted_action = None
                    if match:
                        if match.group("verb"):
                            verb = match.group("verb").upper()
                            args = match.group("args1").strip()
                            if verb == "READ_FILE":
                                path_match = self._extract_path_from_step_or_args(args)
                                if path_match: args = path_match
                                else: args = args.split(":",1)[0].split("**",1)[0].strip().strip('`\'"')
                            elif verb == "SEARCH_CODE":
                                term_loc_match = re.match(r"""^\s*(["'])(.*?)\1(?:\s+dans\s+(.+))?""", args)
                                if term_loc_match:
                                     term = term_loc_match.group(2)
                                     loc = term_loc_match.group(3)
                                     args = f'"{term}"' + (f' dans {loc.strip()}' if loc else "")
                                else: args = args.split(":",1)[0].split("**",1)[0].strip()
                            extracted_action = f"{verb} {args}"
                        elif match.group("args_read"):
                            verb = "READ_FILE"
                            path_match = self._extract_path_from_step_or_args(match.group("args_read"))
                            if path_match: extracted_action = f"{verb} {path_match}"
                            else:
                                 args = match.group("args_read").split(":",1)[0].split("**",1)[0].strip().strip('`\'"')
                                 if args: extracted_action = f"{verb} {args}"
                        elif match.group("args_search"):
                             verb = "SEARCH_CODE"
                             term_match = re.search(r"[`'\"](.+?)[`'\"]|^\s*(\S+)", match.group("args_search"))
                             term = term_match.group(1) or term_match.group(2) if term_match else "terme_non_extrait"
                             loc_match = re.search(r"dans\s+(`[^`]+`|'[^']+'|\"[^\"]+\"|\S+)", match.group("args_search"))
                             loc = loc_match.group(1).strip('`\'"') if loc_match else "" # Nettoyer quotes de la loc
                             extracted_action = f'{verb} "{term}"' + (f' dans {loc}' if loc else "")
                        elif match.group("args_analyze"):
                            verb = "ANALYZE"
                            args = match.group("args_analyze").split(":",1)[0].split("**",1)[0].strip()
                            extracted_action = f"{verb} {args}"

                    if extracted_action:
                        plan_list.append(extracted_action)
                        logging.debug(f"Ligne plan brute: '{line}' -> Action extraite: '{extracted_action}'")
                    elif line.strip().upper() == "FINISH":
                         potential_finish = True
                         logging.info("Action FINISH détectée dans le plan.")
                         plan_list = ["FINISH"]
                         break
                    else:
                        if re.match(r'^\s*\d+\.', line):
                             logging.warning(f"Impossible d'extraire une action valide de l'étape potentielle: '{line}'")

            if potential_finish or (len(plan_list) == 1 and plan_list[0] == "FINISH"):
                 self.kb.set_plan(["FINISH"])
                 logging.info("Plan final: Terminer l'exploration.")
            elif plan_list:
                 self.kb.set_plan(plan_list)
                 logging.info("Plan généré (parsing tolérant) :")
                 for step in self.kb.exploration_plan:
                      logging.info(f"      {step}")
            else:
                 logging.warning(f"La réponse d'Ollama ne contient aucun plan valide même après parsing tolérant:\n{plan_str}")
                 self.kb.set_plan([])
        else:
            logging.error("Impossible de générer un plan (Ollama n'a pas répondu).")
            self.kb.set_plan([])

    def _extract_path_from_step_or_args(self, text_input: str) -> Optional[str]:
        """Tente d'extraire un chemin de fichier (relatif ou absolu mais dans projet) d'une chaîne."""
        common_extensions = r'\.(php|py|js|ts|go|java|c|cpp|h|hpp|cs|rb|rs|md|txt|json|yaml|yml|xml|html|css|scss|sql|sh|config|ini|env)'
        # 1. Essayer de matcher entre quotes/backticks
        match = re.search(r"[`'\"]([\.\/\w\\~-]+?" + common_extensions + r")[`'\"]", text_input, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        # 2. Essayer sans quotes mais avec / ou \ ou ~
        match = re.search(r"([\.\/\w\\~-]+?" + common_extensions + r")", text_input, re.IGNORECASE)
        if match:
            path_str = match.group(1).strip()
            if '/' in path_str or '\\' in path_str or path_str.startswith('~') or path_str.startswith('.'):
                return path_str
        # 3. Essayer juste le nom de fichier (à la racine)
        match = re.search(r"([\w\-]+\." + common_extensions + r")", text_input, re.IGNORECASE)
        if match:
             return match.group(1).strip() # Retourner même si on ne sait pas s'il existe
        return None

    def _resolve_path(self, path_str: str) -> Optional[Path]:
        """Résoud un chemin (potentiellement relatif) en chemin absolu Path DANS le projet."""
        if not path_str: return None
        # Expand ~ si présent
        path_str_expanded = os.path.expanduser(path_str)
        path = Path(path_str_expanded)

        if path.is_absolute():
            try:
                resolved_path = path.resolve()
                if self.project_path.resolve() in resolved_path.parents or self.project_path.resolve() == resolved_path:
                    return resolved_path
                else:
                    logging.warning(f"Chemin absolu '{path_str}' résolu hors du projet ('{resolved_path}'). Ignoré.")
                    return None
            except OSError as e:
                logging.warning(f"Chemin absolu '{path_str}' non valide ou inaccessible: {e}. Ignoré.")
                return None
            except Exception as e_resolve: # Catch autres erreurs potentielles de resolve
                 logging.warning(f"Erreur lors de la résolution de '{path_str}': {e_resolve}. Ignoré.")
                 return None
        else:
            # Chemin relatif
            try:
                 abs_path = (self.project_path / path).resolve()
                 # Sécurité: re-vérifier qu'on n'est pas sorti
                 if self.project_path.resolve() in abs_path.parents or self.project_path.resolve() == abs_path:
                     return abs_path
                 else:
                      logging.warning(f"Chemin relatif '{path_str}' résolu hors du projet ('{abs_path}'). Ignoré.")
                      return None
            except Exception as e_resolve:
                logging.warning(f"Erreur lors de la résolution du chemin relatif '{path_str}': {e_resolve}. Ignoré.")
                return None

    def _execute_read_file(self, args: str, step_context: str):
        """Exécute l'action READ_FILE, en s'assurant de passer un chemin absolu à read_file_content."""
        filepath_to_read = args.strip().strip("'\"`")

        if not filepath_to_read:
             logging.warning(f"Action READ_FILE sans chemin de fichier clair dans les arguments ('{args}'). Vérification étape: '{step_context}'")
             filepath_to_read = self._extract_path_from_step_or_args(step_context)
             if not filepath_to_read:
                 logging.error("Échec READ_FILE: Chemin de fichier manquant ou non extractible.")
                 self.kb.add_note(f"Échec lecture pour étape '{step_context}': Chemin de fichier manquant.")
                 self.kb.add_history(f"Échec lecture (chemin manquant) pour étape: {step_context}")
                 return
             else:
                  logging.info(f"Chemin extrait de l'étape: '{filepath_to_read}'")

        abs_filepath_obj = self._resolve_path(filepath_to_read)

        if not abs_filepath_obj:
            self.kb.add_note(f"Échec lecture pour étape '{step_context}': Chemin '{filepath_to_read}' invalide ou hors projet.")
            self.kb.add_history(f"Échec lecture (chemin invalide/hors projet: {filepath_to_read}) pour étape: {step_context}")
            return

        abs_filepath_str = str(abs_filepath_obj)
        rel_filepath_str = self.kb._get_relative_path(abs_filepath_str)

        logging.info(f"Action READ_FILE: Tentative lecture de '{rel_filepath_str}' (Absolu: {abs_filepath_str})")
        content = self.read_file_content(abs_filepath_str)

        if content.startswith("Erreur:"):
            error_msg = content.split(':', 1)[1].strip() if ':' in content else content
            self.kb.add_note(f"Échec lecture '{rel_filepath_str}': {error_msg}")
            self.kb.add_history(f"Échec lecture '{rel_filepath_str}' ({error_msg})")
        else:
            self.kb.add_file_content(abs_filepath_str, content)
            num_bytes = len(content.encode('utf-8', errors='ignore'))
            status = f"{num_bytes} bytes"
            is_truncated = "[... contenu tronqué" in content or "[... fin du fichier tronquée" in content
            if is_truncated: status += " - tronqué"
            self.kb.add_history(f"Lu fichier '{rel_filepath_str}' ({status})")

            if len(content) > 50 and not is_truncated:
                summary_prompt = f"""Voici le contenu du fichier `{rel_filepath_str}`:
                ```
                {content[:1500]}
                ```
                Résume son rôle principal en 1 phrase concise pour le contexte de la question "{self.user_problem}".
                """
                summary = self._ollama_request(summary_prompt, "Tu résumes des fichiers de code de manière très concise en lien avec une question spécifique.")
                if summary:
                    summary = summary.split('\n')[0].strip()
                    self.kb.add_note(f"Résumé '{rel_filepath_str}': {summary}")
                else:
                    self.kb.add_note(f"Échec résumé pour '{rel_filepath_str}'.")
            elif is_truncated:
                 note_exists = any(f"Fichier '{rel_filepath_str}' lu mais tronqué" in n for n in self.kb.analysis_notes)
                 if not note_exists:
                     self.kb.add_note(f"Fichier '{rel_filepath_str}' lu mais tronqué, pas de résumé demandé.")
            elif len(content) <= 50:
                 note_exists = any(f"Fichier '{rel_filepath_str}' lu (contenu court ou vide)" in n for n in self.kb.analysis_notes)
                 if not note_exists:
                     self.kb.add_note(f"Fichier '{rel_filepath_str}' lu (contenu court ou vide).")

    def _parse_search_args(self, args: str, step_context: str) -> tuple:
        """Parse les arguments de SEARCH_CODE et résout le chemin."""
        term = ""
        location_str = "."
        search_target_path = self.project_path
        search_path_log = "projet entier"
        search_target_is_file = False
        # Correction de la regex et de l'accès aux groupes
        match = re.match(r"""^\s*(["'])(.*?)\1(?:\s+dans\s+(.+))?$""", args)
        if match:
            term = match.group(2)
            if match.group(3): # Utiliser le groupe 3 pour la location
                location_str = match.group(3).strip().strip("'\"`")
        else:
            logging.warning(f"Arguments SEARCH_CODE ('{args}') sans guillemets autour du terme. Tentative de parsing simple.")
            parts = args.split(" dans ", 1)
            term = parts[0].strip().strip("'\"`")
            if len(parts) > 1:
                location_str = parts[1].strip().strip("'\"`")

        if not term:
           logging.error(f"Échec SEARCH_CODE: Terme de recherche manquant dans les args '{args}' pour l'étape '{step_context}'.")
           self.kb.add_note(f"Échec recherche pour étape '{step_context}': Terme manquant.")
           self.kb.add_history(f"Échec recherche (terme manquant) pour étape: {step_context}")
           return None, None, None, None

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

    def _execute_search_code(self, args: str, step_context: str):
        """Exécute une recherche de code réelle en utilisant rg (ripgrep) si disponible, sinon fallback Python."""
        parse_result = self._parse_search_args(args, step_context)
        if parse_result[0] is None: return
        term, search_target_path, search_path_log, search_target_is_file = parse_result

        logging.info(f"Action SEARCH_CODE: Recherche réelle de '{term}' dans {search_path_log}")
        found_results = []
        search_method = "Inconnu"
        rg_path = shutil.which('rg')

        if rg_path:
            search_method = "ripgrep (rg)"
            logging.info(f"Utilisation de {search_method} trouvé à '{rg_path}'")
            command = [ rg_path, '--case-insensitive', '--count', '--no-heading', '--no-ignore', '--', term, str(search_target_path)]
            try:
                timeout_seconds = 60
                logging.debug(f"Exécution commande rg: {' '.join(command)}")
                process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=timeout_seconds, check=False)
                if process.returncode == 0:
                    logging.debug(f"rg stdout:\n{process.stdout}")
                    for line in process.stdout.strip().split('\n'):
                        if line:
                            parts = line.split(':', 1)
                            if len(parts) == 2:
                                try:
                                    file_path_str = parts[0].strip()
                                    count = int(parts[1].strip())
                                    rel_path = self.kb._get_relative_path(file_path_str)
                                    found_results.append({'path': rel_path, 'count': count})
                                except ValueError: logging.warning(f"Impossible de parser la ligne de sortie rg (count): '{line}'")
                                except Exception as e_parse: logging.warning(f"Erreur parsing ligne rg '{line}': {e_parse}")
                            else: logging.warning(f"Impossible de parser la ligne de sortie rg (split): '{line}'")
                elif process.returncode == 1: logging.info("rg n'a trouvé aucune correspondance.")
                else:
                    error_output = process.stderr.strip() if process.stderr else "(aucune sortie d'erreur)"
                    logging.error(f"Erreur lors de l'exécution de rg (code {process.returncode}):\n{error_output}")
                    self.kb.add_note(f"Erreur recherche '{term}' avec rg: {error_output[:200]}...")
                    search_method += " (Erreur)"
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
        else:
            search_method = "Pure Python (os.walk)"
            logging.warning(f"ripgrep (rg) non trouvé. Utilisation du fallback {search_method} (peut être plus lent et moins précis sur les exclusions).")
            ignore_dirs_py = {'.git', '.vscode', 'node_modules', '__pycache__', 'venv', '.venv', 'target', 'build', 'dist', 'vendor', '.idea', '.composer', 'cache', 'logs', 'tmp', 'temp'}
            ignore_prefixes_py = ('.', '_')
            ignore_extensions_py = {'.log', '.tmp', '.bak', '.swp', '.map', '.lock', '.DS_Store', '.pyc', '.pyo', '.class', '.o', '.so', '.dll', '.exe', '.jar', '.war', '.ear', '.zip', '.gz', '.tar', '.rar', '.7z', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.mp3', '.wav', '.ogg', '.mp4', '.mov', '.avi', '.webm'}
            try:
                term_lower = term.lower()
                if search_target_is_file:
                    if search_target_path.suffix.lower() not in ignore_extensions_py and not search_target_path.name.startswith(ignore_prefixes_py):
                        count = self._search_in_file(search_target_path, term_lower)
                        if count > 0:
                            rel_path = self.kb._get_relative_path(str(search_target_path))
                            found_results.append({'path': rel_path, 'count': count})
                    else: logging.info(f"Fichier '{search_target_path.name}' ignoré par les règles d'extension/préfixe.")
                else:
                    for root, dirs, files in os.walk(str(search_target_path), topdown=True):
                        dirs[:] = [d for d in dirs if d not in ignore_dirs_py and not d.startswith(ignore_prefixes_py)]
                        for filename in files:
                            if filename.startswith(ignore_prefixes_py): continue
                            file_path = Path(root) / filename
                            if file_path.suffix.lower() in ignore_extensions_py: continue
                            try: # Ajouter try/except autour de resolve pour les liens cassés etc
                                resolved_file_path = file_path.resolve()
                                if not (self.project_path.resolve() in resolved_file_path.parents or self.project_path.resolve() == resolved_file_path):
                                    logging.debug(f"Ignoré fichier hors projet lors de l'os.walk: {file_path}")
                                    continue
                            except Exception: # Ignorer si resolve échoue
                                 logging.debug(f"Ignoré fichier non résolvable lors de l'os.walk: {file_path}")
                                 continue

                            count = self._search_in_file(file_path, term_lower)
                            if count > 0:
                                rel_path = self.kb._get_relative_path(str(file_path))
                                found_results.append({'path': rel_path, 'count': count})
            except Exception as e:
                 logging.error(f"Erreur inattendue lors de la recherche Python: {e}", exc_info=True)
                 self.kb.add_note(f"Erreur recherche Python pour '{term}': {e}")
                 search_method = f"Erreur (Python: {type(e).__name__})"

        result_summary = ""
        if found_results:
              found_results.sort(key=lambda x: x['path'])
              results_str = ", ".join([f"`{r['path']}` ({r['count']})" for r in found_results])
              max_res_len = 300
              if len(results_str) > max_res_len: results_str = results_str[:max_res_len] + "..."
              result_summary = f"Trouvé '{term}' dans {len(found_results)} fichier(s) via {search_method}: {results_str}."
              logging.info(f"      {result_summary}")
        else:
             if "Erreur" in search_method:
                 result_summary = f"Recherche de '{term}' via {search_method} a échoué."
                 logging.error(f"      {result_summary}")
             else:
                 result_summary = f"Terme '{term}' non trouvé via {search_method} dans {search_path_log}."
                 logging.info(f"      {result_summary}")

        if "Erreur" not in search_method:
            self.kb.add_note(f"Résultat recherche '{term}' dans {search_path_log} ({search_method}): {result_summary}")
            self.kb.add_history(f"Recherché '{term}' dans {search_path_log} ({search_method}). {'Trouvé' if found_results else 'Non trouvé'}.")
        else:
             self.kb.add_history(f"Tentative recherche '{term}' dans {search_path_log} ({search_method}). Échec.")

    def _search_in_file(self, file_path: Path, term_lower: str) -> int:
        """Fonction utilitaire pour chercher un terme (insensible casse) dans un seul fichier (utilisé par le fallback Python)."""
        count = 0
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    count += line.lower().count(term_lower)
        except FileNotFoundError:
             logging.warning(f"_search_in_file: Fichier non trouvé '{file_path}'.")
             return 0
        except PermissionError:
             logging.warning(f"_search_in_file: Permission refusée pour lire '{file_path}'.")
             return 0
        except OSError as e:
             # Logguer l'erreur spécifique (ex: trop de liens symboliques)
             logging.warning(f"_search_in_file: Erreur OS lors de la lecture de '{file_path}': {e}")
             return 0
        except Exception as e:
             logging.warning(f"_search_in_file: Erreur inattendue lors de la lecture/recherche dans '{file_path}': {e}")
             return 0
        return count

    def _execute_analyze(self, args: str, step_context: str):
        """Exécute l'action ANALYZE en demandant à Ollama."""
        analysis_description = args if args else step_context
        if not analysis_description:
            logging.error("Échec ANALYZE: Description de l'analyse manquante.")
            self.kb.add_note(f"Échec analyse pour étape '{step_context}': Description manquante.")
            self.kb.add_history(f"Échec analyse (description manquante) pour étape: {step_context}")
            return

        logging.info(f"Action ANALYZE: '{analysis_description}'")
        self.kb.add_history(f"Analyse demandée: {analysis_description}")
        analysis_prompt = f"""Contexte actuel du projet ({self.kb.project_type} à {self.project_path.name}):
        {self.kb.get_context_summary(self.user_problem)}
        ---
        Question initiale: "{self.user_problem}"
        ---
        Demande d'analyse spécifique (issue du plan d'exploration):
        "{analysis_description}"
        ---
        Réponds à cette demande d'analyse en te basant **strictement** sur le contexte fourni. Sois concis (2-4 phrases maximum). Si le contexte ne permet pas de répondre, indique-le clairement.
        """
        system_analyzer = f"Tu es un assistant IA analysant une base de code {self.kb.project_type}. Réponds de manière concise à la demande d'analyse en te basant strictement sur le contexte fourni."
        analysis_result = self._ollama_request(analysis_prompt, system_analyzer)

        if analysis_result:
             analysis_result = analysis_result.strip()
             note = f"Résultat analyse '{analysis_description[:50]}...': {analysis_result}"
             logging.info(f"      {note}")
             self.kb.add_note(note)
        else:
            logging.warning(f"L'analyse demandée pour '{analysis_description[:50]}...' n'a pas retourné de résultat d'Ollama.")
            self.kb.add_note(f"Échec de l'analyse '{analysis_description[:50]}...' (pas de résultat Ollama).")

    def execute_exploration_step(self, step: str) -> bool:
        """Exécute une seule étape du plan (déjà formatée `VERBE args`) et retourne True si FINISH."""
        logging.info(f"--> Exécution étape: {step}")
        step = step.strip()
        if step.upper() == "FINISH":
             logging.info("      Action FINISH détectée dans le plan.")
             self.kb.add_history("Action FINISH reçue du planificateur.")
             return True

        action_verb = ""
        action_args = ""
        parts = step.split(' ', 1)
        if parts:
            action_verb = parts[0].upper()
            if len(parts) > 1:
                action_args = parts[1].strip()

        known_verbs = ["READ_FILE", "SEARCH_CODE", "ANALYZE", "SKIP"]
        if action_verb not in known_verbs:
             logging.warning(f"Étape du plan non reconnue: '{step}'. Tentative d'interprétation par Ollama...")
             return self._interpret_and_execute_unknown_step(step)

        try:
            if action_verb == "READ_FILE":
                self._execute_read_file(action_args, step)
            elif action_verb == "SEARCH_CODE":
                 self._execute_search_code(action_args, step)
            elif action_verb == "ANALYZE":
                 self._execute_analyze(action_args, step)
            elif action_verb == "SKIP":
                logging.info(f"      Étape sautée (indiqué dans le plan ou interprété): {step}")
                self.kb.add_note(f"Étape '{step}' sautée.")
                self.kb.add_history(f"Sauté étape: {step}")
        except Exception as e:
            logging.error(f"Erreur lors de l'exécution de l'action {action_verb} pour l'étape '{step}': {e}", exc_info=True)
            self.kb.add_note(f"Erreur exécution étape '{step}' (Action: {action_verb}): {e}")
            self.kb.add_history(f"Erreur exécution action '{action_verb}' pour étape: {step} ({e})")

        return False

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

        action_str = action_str_raw.strip().strip('`').strip()
        logging.info(f"      Interprétation Ollama pour étape ambiguë: '{action_str}'")
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
            if action_verb == "READ_FILE": self._execute_read_file(action_args, step)
            elif action_verb == "SEARCH_CODE": self._execute_search_code(action_args, step)
            elif action_verb == "ANALYZE": self._execute_analyze(action_args, step)
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
        return False

    def evaluate_progress(self) -> bool:
        """Demande à Ollama si le problème semble résolu avec le contexte actuel."""
        logging.info("-> Évaluation de la progression pour répondre à: '{self.user_problem}'")
        if not self.kb.exploration_history:
             logging.warning("Aucune action n'a été exécutée, impossible d'évaluer la progression.")
             return False

        context_summary = self.kb.get_context_summary(self.user_problem, include_plan=False)
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
            eval_clean = evaluation.strip().upper().rstrip('.!')
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
            self.kb.add_note("Échec de l'évaluation de la progression par Ollama.")
            return False

    def generate_final_explanation(self, termination_reason: str):
        """Demande à Ollama de générer l'explication finale basée sur TOUT le contexte collecté."""
        logging.info("4. Génération de l'explication finale...")
        context_summary = self.kb.get_context_summary(self.user_problem, include_plan=False)
        explanation_prompt = f"""
        Voici le résumé complet du contexte collecté lors de l'exploration de la base de code `{self.kb.project_path.name}` (type: {self.kb.project_type}) pour répondre à la demande : "{self.user_problem}"
        ```
        {context_summary}
        ```
        ---
        L'exploration s'est terminée pour la raison suivante: "{termination_reason}"
        ---
        INSTRUCTIONS POUR L'EXPLICATION FINALE:
        1. Synthétise TOUTES les informations pertinentes du contexte pour répondre directement et clairement à la question initiale de l'utilisateur: "{self.user_problem}".
        2. Structure ta réponse de manière logique (étapes, points clés).
        3. **Cite les fichiers pertinents** (avec leur chemin relatif, ex: `main.py`) et les découvertes clés.
        4. Base-toi **strictement** sur le contexte fourni. Ne fais PAS de suppositions externes.
        5. Si l'exploration s'est arrêtée avant d'avoir une réponse complète, **indique-le clairement**. Explique ce qui a été trouvé, ce qui manque, et suggère éventuellement comment continuer l'investigation manuellement si pertinent.
        6. Adapte le niveau de détail à la complexité de la question et des informations trouvées.
        """
        system_explainer = f"Tu es un assistant IA expert en code {self.kb.project_type}. Tu expliques clairement une solution ou un fonctionnement technique en te basant **strictement** sur l'analyse de code fournie dans le contexte. Adapte ta réponse si l'analyse est incomplète en indiquant ce qui manque."
        final_explanation = self._ollama_request(explanation_prompt, system_explainer)

        print("\n--- Explication Générée ---")
        if final_explanation:
            print(final_explanation)
        else:
            print("   Erreur: Impossible de générer l'explication finale via Ollama.")
            logging.error("Impossible de générer l'explication finale.")
            print("\n   Contexte final collecté (Fallback car explication échouée) :\n", context_summary)
        print("--- Fin de l'Explication ---\n")

    def run(self):
        """Orchestre l'exécution complète de l'agent : analyse, planification, exploration en boucle, explication."""
        self.user_problem = ""
        while not self.user_problem:
             self.user_problem = input("Quel problème souhaitez-vous résoudre ou quel fonctionnement souhaitez-vous comprendre ?\n> ").strip()
             if not self.user_problem: print("La question ne peut pas être vide.")

        logging.info(f"Lancement de l'analyse pour : '{self.user_problem}' dans {self.project_path}")

        try:
            self.analyze_initial_context() # Appel de la méthode restaurée
        except Exception as e:
             logging.critical(f"Erreur critique lors de l'analyse initiale: {e}", exc_info=True)
             print(f"\nErreur critique pendant l'analyse initiale: {e}")
             return

        initial_context = self.kb.get_context_summary(self.user_problem, include_plan=False)
        try:
            self.plan_exploration(initial_context)
        except Exception as e:
             logging.critical(f"Erreur critique lors de la planification initiale: {e}", exc_info=True)
             print(f"\nErreur critique pendant la planification initiale: {e}")
             return

        iteration = 0
        termination_reason = "Raison inconnue"
        max_iterations = MAX_EXPLORATION_ITERATIONS

        while iteration < max_iterations:
            iteration += 1
            logging.info(f"\n--- Début Itération d'Exploration {iteration}/{max_iterations} ---")

            if not self.kb.exploration_plan:
                logging.warning(f"Aucun plan à exécuter pour l'itération {iteration}. Tentative de re-planification.")
                current_context_replan = self.kb.get_context_summary(self.user_problem, include_plan=False)
                try:
                    self.plan_exploration(current_context_replan)
                    if not self.kb.exploration_plan:
                         logging.error("Échec de la re-planification. Arrêt de l'exploration.")
                         termination_reason = "Aucun plan d'exploration généré ou valide."
                         break
                except Exception as e_replan:
                    logging.critical(f"Erreur critique lors de la re-planification (itération {iteration}): {e_replan}", exc_info=True)
                    print(f"\nErreur critique pendant la re-planification: {e_replan}")
                    termination_reason = f"Erreur critique pendant la re-planification: {e_replan}"
                    break

            if self.kb.exploration_plan:
                plan_to_execute = self.kb.exploration_plan[:]
                self.kb.set_plan([])
                logging.info(f"Plan pour itération {iteration}: {len(plan_to_execute)} étape(s)")

                finish_requested = False
                for step_index, step in enumerate(plan_to_execute):
                    logging.info(f"Itération {iteration}, Étape {step_index + 1}/{len(plan_to_execute)}")
                    try:
                        finish_requested = self.execute_exploration_step(step)
                        if finish_requested:
                             termination_reason = "Action FINISH rencontrée ou interprétée."
                             logging.info(f"FINISH demandé pendant l'itération {iteration}. Arrêt de l'exploration.")
                             break
                    except Exception as e_step:
                         logging.critical(f"Erreur critique non gérée pendant l'exécution de l'étape '{step}': {e_step}", exc_info=True)
                         self.kb.add_note(f"Erreur critique pendant étape '{step}': {e_step}")
                         self.kb.add_history(f"Erreur critique étape '{step}': {e_step}")

                if finish_requested: break

                if not finish_requested:
                     if self.evaluate_progress():
                         termination_reason = "L'IA estime avoir trouvé la réponse."
                         logging.info(f"Évaluation positive à la fin de l'itération {iteration}. Arrêt de l'exploration.")
                         break
                     else:
                         if iteration < max_iterations:
                              logging.info(f"Fin de l'itération {iteration}. Évaluation négative, passage à l'itération suivante.")

        else:
            logging.warning(f"Limite de {max_iterations} itérations atteinte.")
            termination_reason = f"Limite de {max_iterations} itérations atteinte."

        try:
            self.generate_final_explanation(termination_reason)
        except Exception as e_final:
            logging.critical(f"Erreur critique lors de la génération de l'explication finale: {e_final}", exc_info=True)
            print(f"\nErreur critique pendant la génération de l'explication: {e_final}")
            print(f"\nL'exploration s'est terminée ({termination_reason}) mais l'explication finale n'a pu être générée.")

        logging.info(f"Analyse terminée ({termination_reason}).")


# --- Programme Principal ---
if __name__ == "__main__":
    agent = None
    try:
        script_dir = Path(__file__).parent.resolve()
        default_folder = str(script_dir)
        user_input_folder = input(f"Entrez le chemin du dossier projet (laissez vide pour utiliser '{default_folder}'):\n> ").strip()
        if not user_input_folder: project_folder = default_folder
        else: project_folder = user_input_folder

        project_path_obj = Path(project_folder)
        if not project_path_obj.is_dir():
             print(f"\nErreur: Le dossier '{project_folder}' n'existe pas ou n'est pas accessible.")
             exit(1)

        print(f"Utilisation du dossier projet: {project_path_obj.resolve()}")
        agent = OllamaCodingAgent(project_folder)
        agent.run()
    except ValueError as ve:
        logging.error(f"Erreur de configuration: {ve}")
        print(f"\nErreur: {ve}")
    except FileNotFoundError:
         logging.error(f"Erreur: Le dossier spécifié n'a pas été trouvé.")
         print(f"\nErreur: Le dossier spécifié n'a pas été trouvé.")
    except KeyboardInterrupt:
         logging.info("Arrêt demandé par l'utilisateur (Ctrl+C).")
         print("\nArrêt demandé.")
         if agent:
             print("\nTentative de génération d'une conclusion basée sur l'état actuel...")
             try: agent.generate_final_explanation("Arrêt par l'utilisateur (Ctrl+C)")
             except Exception as e_interrupt_explain: print(f"Impossible de générer l'explication après interruption: {e_interrupt_explain}")
    except Exception as e:
        logging.critical(f"Une erreur inattendue et non gérée est survenue: {e}", exc_info=True)
        print(f"\nUne erreur critique est survenue: {e}")
    finally:
         logging.info("Fin du script.")
         print("\nScript terminé.")
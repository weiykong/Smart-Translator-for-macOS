import requests
import rumps
import pyperclip
from collections import deque
import json
import os
import threading
import logging
from datetime import datetime
from pynput import keyboard

# Setup Logging
LOG_DIR = os.path.expanduser("~/Library/Logs/SmartTranslator")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "app.log"),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class OllamaClient:
    """Handles all interactions with the Ollama API"""
    def __init__(self, base_url):
        self.base_url = base_url

    def check_connection(self):
        try:
            requests.get(self.base_url, timeout=2)
            return True
        except Exception:
            return False

    def fetch_models(self):
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            return [model["name"] for model in response.json().get("models", [])]
        except Exception as e:
            logging.error(f"Failed to fetch models: {e}")
            return []

    def generate(self, model, prompt):
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=120
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except Exception as e:
            logging.error(f"Generation failed: {e}")
            raise e

class SmartTranslatorApp(rumps.App):
    def __init__(self):
        super().__init__("🌍 Translator", quit_button=None)
        self.clipboard_history = deque(maxlen=10)
        self.is_processing = False
        
        # Paths
        self.app_support_dir = os.path.expanduser("~/Library/Application Support/SmartTranslator/")
        self.models_file = os.path.join(self.app_support_dir, "models.json")
        self.config_file = os.path.join(self.app_support_dir, "config.json")
        
        os.makedirs(self.app_support_dir, exist_ok=True)
        
        # State
        self.config = self.load_config()
        self.client = OllamaClient(self.config['ollama_url'])
        self.available_models, self.model = self.load_models()
        self.online = False
        
        self.setup_menu()
        self.start_connection_poll()
        self.start_hotkey_listener()
        logging.info("App initialized")

    def start_hotkey_listener(self):
        """Starts a background thread to listen for global hotkeys"""
        kb_controller = keyboard.Controller()

        def on_hotkey():
            if not self.is_processing and self.online and self.model:
                logging.info("Hotkey Ctrl+Cmd+C pressed")
                
                # Simulate Cmd+C to copy current selection
                # Note: We use Key.cmd for macOS
                with kb_controller.pressed(keyboard.Key.cmd):
                    kb_controller.tap('c')
                
                # Wait for clipboard to update
                threading.Event().wait(0.2)
                
                threading.Thread(target=self.process_task, args=("correct",), daemon=True).start()

        def listener_thread():
            try:
                # <ctrl>+<cmd>+c for macOS
                with keyboard.GlobalHotKeys({
                    '<ctrl>+<cmd>+c': on_hotkey
                }) as h:
                    logging.info("Hotkey listener started for <ctrl>+<cmd>+c")
                    h.join()
            except Exception as e:
                logging.error(f"Hotkey listener error: {e}")
                if "trusted" in str(e).lower() or "accessibility" in str(e).lower():
                    logging.warning("Accessibility permissions missing for hotkey listener")

        threading.Thread(target=listener_thread, daemon=True).start()

    def load_config(self):
        default_config = {
            "ollama_url": "http://localhost:11434",
            "targets": [
                {"name": "Chinese", "emoji": "🇨🇳"},
                {"name": "French", "emoji": "🇫🇷"},
                {"name": "English", "emoji": "🇺🇸"}
            ],
            "prompts": {
                "correct": "You're a language enhancer expert. Enhance and correct input text while preserving its language. Return ONLY the corrected text.\n\nText:\n{text}",
                "translate": "You're a translator expert. Accurate, preserve formatting. Return ONLY the translated text to {action}.\n\nText:\n{text}"
            },
            "use_cases": [
                {
                    "name": "Token Saver",
                    "emoji": "🪙",
                    "description": "Strip verbose content to reduce token usage",
                    "prompt": "Compress the following text. Remove filler words, redundant phrases, pleasantries, and unnecessary detail. Keep all technical terms, names, numbers, and key facts. Output the shorter version only, nothing else.\n\nText:\n{text}"
                },
                {
                    "name": "Debug Helper",
                    "emoji": "🐛",
                    "description": "Analyze code and suggest fixes",
                    "prompt": "You are a code debugger. Analyze the code below. List each bug or issue as:\n- LINE: issue → fix\n\nIf no bugs found, say \"No issues found.\" Output ONLY the bug list, no extra commentary.\n\nCode:\n{text}"
                },
                {
                    "name": "Error Condenser",
                    "emoji": "🔴",
                    "description": "Extract key info from verbose error logs",
                    "prompt": "Extract the essential information from this error output. Return ONLY:\n1. Error type and message (one line)\n2. Root cause file and line number\n3. Key variable values if shown\n\nDrop all stack frames that are from libraries or frameworks. Keep only YOUR code frames. No extra text.\n\nError:\n{text}"
                },
                {
                    "name": "Explain Code",
                    "emoji": "📖",
                    "description": "Explain what a piece of code does",
                    "prompt": "Explain what this code does in 2-3 short bullet points. Be direct. Mention inputs, outputs, and side effects. No code blocks in your answer.\n\nCode:\n{text}"
                },
                {
                    "name": "Git Commit Msg",
                    "emoji": "📝",
                    "description": "Generate a commit message from a diff",
                    "prompt": "Write a git commit message for this diff. Use conventional commit format: type(scope): description. One line, max 72 chars. Types: feat, fix, refactor, docs, test, chore. Output ONLY the commit message line.\n\nDiff:\n{text}"
                },
                {
                    "name": "JSON Cleaner",
                    "emoji": "🧹",
                    "description": "Fix and format broken JSON",
                    "prompt": "Fix and format the following JSON. Correct any syntax errors (missing quotes, trailing commas, unescaped characters). Return ONLY the valid, pretty-printed JSON. No explanation.\n\n{text}"
                },
                {
                    "name": "Log Extractor",
                    "emoji": "📋",
                    "description": "Extract warnings and errors from log output",
                    "prompt": "From the log output below, extract ONLY lines containing errors, warnings, or failures. Group them as:\n\nERRORS:\n- ...\n\nWARNINGS:\n- ...\n\nIf none found in a category, skip it. No other output.\n\nLogs:\n{text}"
                },
                {
                    "name": "SQL from Error",
                    "emoji": "🗄️",
                    "description": "Extract and fix SQL from database errors",
                    "prompt": "Extract the SQL query from this database error message. Fix the syntax error if there is one. Return ONLY the corrected SQL query, nothing else.\n\nError:\n{text}"
                }
            ]
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    for k, v in default_config.items():
                        if k not in config: config[k] = v
                    # Merge default use cases that don't exist yet
                    existing_names = {uc['name'] for uc in config.get('use_cases', [])}
                    for uc in default_config.get('use_cases', []):
                        if uc['name'] not in existing_names:
                            config.setdefault('use_cases', []).append(uc)
                    return config
            except Exception as e:
                logging.error(f"Config load error: {e}")
        return default_config

    def save_config(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            self.setup_menu()
        except Exception as e:
            logging.error(f"Config save error: {e}")

    def load_models(self):
        available = []
        current = None
        if os.path.exists(self.models_file):
            try:
                with open(self.models_file, 'r') as f:
                    data = json.load(f)
                    available = data.get("models", [])
                    current = data.get("default_model")
            except Exception as e:
                logging.error(f"Models load error: {e}")
        
        if not current and available:
            current = available[0]
        return available, current

    def save_models(self):
        try:
            with open(self.models_file, 'w') as f:
                json.dump({
                    "models": self.available_models,
                    "default_model": self.model,
                    "last_updated": datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logging.error(f"Models save error: {e}")

    def setup_menu(self):
        self.menu.clear()
        self.menu.add(rumps.MenuItem("Correct Clipboard", callback=self.on_action))
        self.menu.add(rumps.separator)

        for target in self.config.get("targets", []):
            self.menu.add(rumps.MenuItem(f"Translate to {target['name']}", callback=self.on_action))

        # Custom Use Cases
        use_cases = self.config.get("use_cases", [])
        if use_cases:
            self.menu.add(rumps.separator)
            for uc in use_cases:
                self.menu.add(rumps.MenuItem(f"{uc['emoji']} {uc['name']}", callback=self.on_use_case_action))

        self.menu.add(rumps.separator)
        self.add_models_submenu()

        settings = rumps.MenuItem("Settings")
        settings.add(rumps.MenuItem("Change Ollama URL", callback=self.change_url))

        # Language Management
        lang_menu = rumps.MenuItem("Manage Languages")
        lang_menu.add(rumps.MenuItem("Add Language...", callback=self.add_language))
        if self.config.get("targets"):
            lang_menu.add(rumps.separator)
            for t in self.config["targets"]:
                def make_remove_cb(name):
                    return lambda _: self.remove_language(name)
                lang_menu.add(rumps.MenuItem(f"Remove {t['name']}", callback=make_remove_cb(t['name'])))
        settings.add(lang_menu)

        # Use Case Management
        uc_menu = rumps.MenuItem("Manage Use Cases")
        uc_menu.add(rumps.MenuItem("Add Use Case...", callback=self.add_use_case))
        if use_cases:
            uc_menu.add(rumps.separator)
            for uc in use_cases:
                def make_remove_uc_cb(name):
                    return lambda _: self.remove_use_case(name)
                uc_menu.add(rumps.MenuItem(f"Remove {uc['name']}", callback=make_remove_uc_cb(uc['name'])))
        settings.add(uc_menu)

        settings.add(rumps.separator)
        settings.add(rumps.MenuItem("Edit Config File", callback=lambda _: os.system(f"open -e '{self.config_file}'")))
        settings.add(rumps.MenuItem("Open Logs", callback=lambda _: os.system(f"open {LOG_DIR}")))
        settings.add(rumps.MenuItem("Open Config Folder", callback=lambda _: os.system(f"open '{self.app_support_dir}'")))
        self.menu.add(settings)

        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("Undo Last", callback=self.undo_last))
        self.menu.add(rumps.MenuItem("Quit", callback=rumps.quit_application))

    def add_language(self, _):
        window = rumps.Window(
            message="Enter language name (e.g. Japanese, Spanish)",
            title="Add Language",
            default_text="",
            ok="Next",
            cancel="Cancel"
        )
        res = window.run()
        if res.clicked and res.text.strip():
            lang_name = res.text.strip()
            
            emoji_window = rumps.Window(
                message=f"Enter emoji for {lang_name} (optional)",
                title="Language Emoji",
                default_text="🌐",
                ok="Add",
                cancel="Cancel"
            )
            e_res = emoji_window.run()
            if e_res.clicked:
                emoji = e_res.text.strip() or "🌐"
                self.config["targets"].append({"name": lang_name, "emoji": emoji})
                self.save_config()
                rumps.notification("Success", f"Added {lang_name}", "")

    def remove_language(self, name):
        self.config["targets"] = [t for t in self.config["targets"] if t['name'] != name]
        self.save_config()
        rumps.notification("Success", f"Removed {name}", "")

    def add_use_case(self, _):
        """Guide user through creating a custom use case with LLM-refined prompt"""
        # Step 1: Get the use case description from user
        desc_window = rumps.Window(
            message="Describe what you want to do with your clipboard text.\n\n"
                    "Examples:\n"
                    "• Save tokens by removing verbose parts\n"
                    "• Strip HTML tags and clean up text\n"
                    "• Summarize long text into bullet points\n"
                    "• Convert to formal business tone",
            title="New Use Case - Describe Your Goal",
            default_text="",
            ok="Next",
            cancel="Cancel",
            dimensions=(320, 120)
        )
        desc_res = desc_window.run()
        if not desc_res.clicked or not desc_res.text.strip():
            return

        user_description = desc_res.text.strip()

        # Step 2: Get a short name
        name_window = rumps.Window(
            message="Give this use case a short name for the menu.",
            title="Use Case Name",
            default_text="",
            ok="Next",
            cancel="Cancel"
        )
        name_res = name_window.run()
        if not name_res.clicked or not name_res.text.strip():
            return

        uc_name = name_res.text.strip()

        # Step 3: Get emoji
        emoji_window = rumps.Window(
            message=f"Choose an emoji for '{uc_name}' (optional)",
            title="Use Case Emoji",
            default_text="⚡",
            ok="Generate Prompt",
            cancel="Cancel"
        )
        emoji_res = emoji_window.run()
        if not emoji_res.clicked:
            return
        uc_emoji = emoji_res.text.strip() or "⚡"

        # Step 4: Use the local LLM to refine the description into a proper prompt
        if not self.online or not self.model:
            rumps.notification("Error", "Ollama not available", "Cannot generate prompt without a running model")
            return

        self.title = "⏳ Generating prompt..."
        try:
            meta_prompt = (
                "You are a prompt engineering expert. The user wants to create a text processing tool "
                "that operates on clipboard text. Based on their description below, generate a clear, "
                "precise system prompt that an LLM will use to process the clipboard text.\n\n"
                "Requirements for the generated prompt:\n"
                "- It must instruct the LLM to return ONLY the processed text, nothing else\n"
                "- It must be specific and unambiguous\n"
                "- It must include {text} as a placeholder where the input text goes\n"
                "- Keep it concise but complete\n\n"
                f"User's description: {user_description}\n\n"
                "Return ONLY the prompt text, no explanation."
            )
            refined_prompt = self.client.generate(self.model, meta_prompt)
        except Exception as e:
            logging.error(f"Prompt generation failed: {e}")
            rumps.notification("Error", "Failed to generate prompt", str(e))
            self.title = "🌍 Translator" if self.online else "❌ Offline"
            return
        finally:
            self.title = "🌍 Translator" if self.online else "❌ Offline"

        if not refined_prompt:
            rumps.notification("Error", "Empty prompt generated", "Try again with a clearer description")
            return

        # Ensure {text} placeholder exists
        if "{text}" not in refined_prompt:
            refined_prompt += "\n\nText:\n{text}"

        # Step 5: Show the refined prompt to user for validation/editing
        validate_window = rumps.Window(
            message="Review and edit the AI-generated prompt below.\n"
                    "Make sure {text} placeholder is present.\n"
                    "Click 'Save' to add this use case.",
            title=f"Validate Prompt for '{uc_name}'",
            default_text=refined_prompt,
            ok="Save",
            cancel="Cancel",
            dimensions=(400, 200)
        )
        validate_res = validate_window.run()
        if not validate_res.clicked:
            return

        final_prompt = validate_res.text.strip()
        if not final_prompt:
            rumps.notification("Error", "Prompt cannot be empty", "")
            return

        if "{text}" not in final_prompt:
            final_prompt += "\n\nText:\n{text}"

        # Step 6: Save the use case
        if "use_cases" not in self.config:
            self.config["use_cases"] = []
        self.config["use_cases"].append({
            "name": uc_name,
            "emoji": uc_emoji,
            "description": user_description,
            "prompt": final_prompt
        })
        self.save_config()
        rumps.notification("Success", f"Added use case: {uc_name}", "Available in the menu now")

    def remove_use_case(self, name):
        self.config["use_cases"] = [uc for uc in self.config.get("use_cases", []) if uc['name'] != name]
        self.save_config()
        rumps.notification("Success", f"Removed use case: {name}", "")

    def on_use_case_action(self, sender):
        """Handle click on a custom use case menu item"""
        if self.is_processing:
            return
        # Parse the name by stripping the emoji prefix
        title = sender.title
        # Find matching use case
        for uc in self.config.get("use_cases", []):
            expected_title = f"{uc['emoji']} {uc['name']}"
            if title == expected_title:
                threading.Thread(
                    target=self.process_use_case, args=(uc,), daemon=True
                ).start()
                return

    def process_use_case(self, use_case):
        """Process clipboard text using a custom use case prompt"""
        self.is_processing = True
        self.title = "⏳ Processing..."
        try:
            text = pyperclip.paste().strip()
            if not text:
                rumps.notification("Clipboard Empty", "", "Copy some text first")
                return

            logging.info(f"Processing use case: {use_case['name']}")
            prompt = use_case['prompt'].format(text=text)
            result = self.client.generate(self.model, prompt)
            if result:
                pyperclip.copy(result)
                self.clipboard_history.append(result)
                preview = result[:50] + "..." if len(result) > 50 else result
                rumps.notification("Success", f"{use_case['emoji']} {use_case['name']} complete", preview)
            else:
                rumps.notification("Error", "Empty result", "")
        except Exception as e:
            logging.error(f"Use case task failed: {e}")
            rumps.notification("Error", "Action failed", str(e))
        finally:
            self.is_processing = False
            self.title = "🌍 Translator" if self.online else "❌ Offline"

    def add_models_submenu(self):
        short = self.model.split(':')[0] if self.model else "None"
        models_menu = rumps.MenuItem(f"Model: {short}")
        if self.available_models:
            for m in self.available_models:
                def make_callback(name):
                    return lambda _: self.select_model(name)
                item_title = f"● {m}" if m == self.model else f"  {m}"
                models_menu.add(rumps.MenuItem(item_title, callback=make_callback(m)))
        else:
            models_menu.add(rumps.MenuItem("No models found"))
        
        models_menu.add(rumps.separator)
        models_menu.add(rumps.MenuItem("↻ Refresh Models", callback=self.refresh_models))
        self.menu.add(models_menu)

    def start_connection_poll(self):
        def poll():
            while True:
                self.online = self.client.check_connection()
                if not self.is_processing:
                    self.title = "🌍 Translator" if self.online else "❌ Offline"
                self.update_menu_state()
                threading.Event().wait(10)
        threading.Thread(target=poll, daemon=True).start()

    def update_menu_state(self):
        clickable = self.online and self.available_models and self.model
        uc_titles = {f"{uc['emoji']} {uc['name']}" for uc in self.config.get("use_cases", [])}
        for k in self.menu.keys():
            if k == "Correct Clipboard" or k.startswith("Translate to"):
                self.menu[k].set_callback(self.on_action if clickable else None)
            elif k in uc_titles:
                self.menu[k].set_callback(self.on_use_case_action if clickable else None)

    def select_model(self, name):
        self.model = name
        self.save_models()
        self.setup_menu()
        rumps.notification("Model Changed", "", f"Using {name}")

    def refresh_models(self, _):
        def task():
            self.title = "⏳ Refreshing..."
            models = self.client.fetch_models()
            if models:
                self.available_models = models
                if not self.model: self.model = models[0]
                self.save_models()
                self.setup_menu()
                rumps.notification("Refreshed", f"Found {len(models)} models", "")
            else:
                rumps.notification("Error", "No models found", "Check Ollama connection")
            self.title = "🌍 Translator" if self.online else "❌ Offline"
        threading.Thread(target=task, daemon=True).start()

    def on_action(self, sender):
        if self.is_processing: return
        action = "correct" if sender.title == "Correct Clipboard" else sender.title.replace("Translate to ", "")
        threading.Thread(target=self.process_task, args=(action,), daemon=True).start()

    def process_task(self, action):
        self.is_processing = True
        self.title = "⏳ Processing..."
        try:
            text = pyperclip.paste().strip()
            if not text:
                rumps.notification("Clipboard Empty", "", "Copy some text first")
                return

            logging.info(f"Processing action: {action}")
            prompt_template = self.config['prompts']['correct'] if action == "correct" else self.config['prompts']['translate']
            prompt = prompt_template.format(text=text, action=action)
            
            result = self.client.generate(self.model, prompt)
            if result:
                pyperclip.copy(result)
                self.clipboard_history.append(result)
                
                emoji = "✏️"
                for t in self.config.get("targets", []):
                    if t['name'] == action: emoji = t['emoji']; break
                
                preview = result[:50] + "..." if len(result) > 50 else result
                rumps.notification("Success", f"{emoji} {action} complete", preview)
            else:
                rumps.notification("Error", "Empty result", "")
        except Exception as e:
            logging.error(f"Task failed: {e}")
            rumps.notification("Error", "Action failed", str(e))
        finally:
            self.is_processing = False
            self.title = "🌍 Translator" if self.online else "❌ Offline"

    def change_url(self, _):
        win = rumps.Window("Enter Ollama URL", "Settings", default_text=self.config['ollama_url'], ok="Save", cancel="Cancel")
        res = win.run()
        if res.clicked:
            self.config['ollama_url'] = res.text.strip()
            self.client.base_url = self.config['ollama_url']
            self.save_config()
            rumps.notification("Settings", "URL Updated", self.config['ollama_url'])

    def undo_last(self, _):
        if len(self.clipboard_history) > 1:
            self.clipboard_history.pop()
            prev = self.clipboard_history[-1]
            pyperclip.copy(prev)
            rumps.notification("Undone", "Restored previous clipboard", prev[:40] + "...")
        else:
            rumps.notification("Undo", "Nothing to undo", "")

if __name__ == "__main__":
    import AppKit
    info = AppKit.NSBundle.mainBundle().infoDictionary()
    info["LSUIElement"] = "1"
    
    app = SmartTranslatorApp()
    rumps.notification("Smart Translator", "🚀 Ready!", "Click the 🌍 icon to start translating")
    app.run()

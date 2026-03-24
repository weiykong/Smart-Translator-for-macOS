import requests
import rumps
import pyperclip
from collections import deque
import json
import os
import threading
import logging
from datetime import datetime

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
        logging.info("App initialized")

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
            }
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    for k, v in default_config.items():
                        if k not in config: config[k] = v
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
        for k in self.menu.keys():
            if k == "Correct Clipboard" or k.startswith("Translate to"):
                self.menu[k].set_callback(self.on_action if clickable else None)

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

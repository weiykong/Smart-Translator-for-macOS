import json
import logging
import os
import re
import subprocess
import threading
from collections import deque
from datetime import datetime

import pyperclip
import requests
import rumps
from pynput import keyboard
from requests.adapters import HTTPAdapter

# Setup Logging
LOG_DIR = os.path.expanduser("~/Library/Logs/SmartTranslator")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "app.log"),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

APP_TITLE_ONLINE = "🌍"
APP_TITLE_BUSY = "⏳"
APP_TITLE_OFFLINE = "❌"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"
DEFAULT_GEMINI_MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
]
SUPPORTED_PROVIDERS = {"ollama", "gemini"}

LEGACY_DEFAULT_PROMPTS = {
    "correct": (
        "You're a language enhancer expert. Enhance and correct input text while preserving its "
        "language. Return ONLY the corrected text.\n\nText:\n{text}"
    ),
    "translate": (
        "You're a translator expert. Accurate, preserve formatting. Return ONLY the translated "
        "text to {action}.\n\nText:\n{text}"
    ),
}

LEGACY_DEFAULT_USE_CASES = {
    "Token Saver": {
        "description": "Strip verbose content to reduce token usage",
        "prompt": (
            "Compress the following text. Remove filler words, redundant phrases, pleasantries, "
            "and unnecessary detail. Keep all technical terms, names, numbers, and key facts. "
            "Output the shorter version only, nothing else.\n\nText:\n{text}"
        ),
    },
    "Debug Helper": {
        "description": "Analyze code and suggest fixes",
        "prompt": (
            "You are a code debugger. Analyze the code below. List each bug or issue as:\n"
            "- LINE: issue → fix\n\nIf no bugs found, say \"No issues found.\" Output ONLY the "
            "bug list, no extra commentary.\n\nCode:\n{text}"
        ),
    },
    "Error Condenser": {
        "description": "Extract key info from verbose error logs",
        "prompt": (
            "Extract the essential information from this error output. Return ONLY:\n"
            "1. Error type and message (one line)\n"
            "2. Root cause file and line number\n"
            "3. Key variable values if shown\n\n"
            "Drop all stack frames that are from libraries or frameworks. Keep only YOUR code "
            "frames. No extra text.\n\nError:\n{text}"
        ),
    },
    "Explain Code": {
        "description": "Explain what a piece of code does",
        "prompt": (
            "Explain what this code does in 2-3 short bullet points. Be direct. Mention inputs, "
            "outputs, and side effects. No code blocks in your answer.\n\nCode:\n{text}"
        ),
    },
    "Git Commit Msg": {
        "description": "Generate a commit message from a diff",
        "prompt": (
            "Write a git commit message for this diff. Use conventional commit format: "
            "type(scope): description. One line, max 72 chars. Types: feat, fix, refactor, docs, "
            "test, chore. Output ONLY the commit message line.\n\nDiff:\n{text}"
        ),
    },
    "JSON Cleaner": {
        "description": "Fix and format broken JSON",
        "prompt": (
            "Fix and format the following JSON. Correct any syntax errors (missing quotes, "
            "trailing commas, unescaped characters). Return ONLY the valid, pretty-printed JSON. "
            "No explanation.\n\n{text}"
        ),
    },
    "Log Extractor": {
        "description": "Extract warnings and errors from log output",
        "prompt": (
            "From the log output below, extract ONLY lines containing errors, warnings, or "
            "failures. Group them as:\n\nERRORS:\n- ...\n\nWARNINGS:\n- ...\n\nIf none found in "
            "a category, skip it. No other output.\n\nLogs:\n{text}"
        ),
    },
    "SQL from Error": {
        "description": "Extract and fix SQL from database errors",
        "prompt": (
            "Extract the SQL query from this database error message. Fix the syntax error if "
            "there is one. Return ONLY the corrected SQL query, nothing else.\n\nError:\n{text}"
        ),
    },
}


def build_default_use_cases():
    return [
        {
            "name": "Token Saver (Safe)",
            "emoji": "🪙",
            "description": "Deterministically remove low-value clutter before sending text to a model",
            "processor": "deterministic",
            "profile": "token_saver_safe",
        },
        {
            "name": "Token Saver (Aggressive)",
            "emoji": "✂️",
            "description": "Use the model to shorten prose while preserving technical details",
            "processor": "gemini",
            "profile": "token_saver_aggressive",
            "prompt": (
                "Shorten the text conservatively.\n\n"
                "Rules:\n"
                "- Keep all names, numbers, commands, file paths, URLs, code, and decisions exactly\n"
                "- Remove filler, repetition, greetings, and polite phrasing\n"
                "- Preserve lists, markdown, placeholders, and line breaks when useful\n"
                "- Do not change technical meaning\n"
                "- If unsure whether something matters, keep it\n"
                "- Return only the shortened text\n\n"
                "Input:\n{text}"
            ),
        },
        {
            "name": "Debug Helper",
            "emoji": "🐛",
            "description": "Find concrete bugs fast and propose direct fixes",
            "prompt": (
                "You are a senior debugging assistant. Review the code or error context and list "
                "only real issues that are supported by the input. Use one bullet per issue in "
                "this format:\n- location or line: issue -> fix\n"
                "If the input is clean, return exactly: No issues found.\n"
                "Do not add setup advice, code fences, or commentary.\n\nInput:\n{text}"
            ),
        },
        {
            "name": "Error Condenser",
            "emoji": "🔴",
            "description": "Turn noisy stack traces into the few details that matter",
            "prompt": (
                "Extract the signal from this error output. Return only these sections when "
                "present:\n"
                "Error: one-line error type and message\n"
                "Location: first user-code file and line number\n"
                "Cause: short root-cause summary\n"
                "Key data: important variables or identifiers if visible\n"
                "Ignore framework and library stack frames unless they change the diagnosis.\n\n"
                "Input:\n{text}"
            ),
        },
        {
            "name": "Explain Code",
            "emoji": "📖",
            "description": "Explain code behavior in a compact, readable way",
            "prompt": (
                "Explain what this code does in 2 to 4 short bullet points. Cover purpose, main "
                "inputs, outputs, and important side effects. Be direct and concrete. Do not use "
                "code fences. Return only the bullets.\n\nInput:\n{text}"
            ),
        },
        {
            "name": "Git Commit Msg",
            "emoji": "📝",
            "description": "Write a crisp conventional commit from a diff",
            "prompt": (
                "Write one git commit message for this diff in conventional commit format: "
                "type(scope): description\n"
                "Use one line, present tense, and keep it under 72 characters. Prefer feat, fix, "
                "refactor, docs, test, or chore. Return only the commit message.\n\nInput:\n{text}"
            ),
        },
        {
            "name": "JSON Cleaner",
            "emoji": "🧹",
            "description": "Repair malformed JSON and pretty-print it",
            "prompt": (
                "Repair this JSON and return valid, pretty-printed JSON only. Preserve the "
                "original schema, values, key names, and ordering whenever possible. Fix missing "
                "quotes, trailing commas, invalid escapes, and other syntax issues. Do not add "
                "explanations.\n\nInput:\n{text}"
            ),
        },
        {
            "name": "Log Extractor",
            "emoji": "📋",
            "description": "Pull out the important warnings, failures, and error lines",
            "prompt": (
                "From this log output, extract only meaningful failures, errors, and warnings. "
                "Group the result with these headings when needed:\nERRORS:\nWARNINGS:\n"
                "Use bullet points under each heading. Skip empty headings. Return nothing else.\n\n"
                "Input:\n{text}"
            ),
        },
        {
            "name": "SQL from Error",
            "emoji": "🗄️",
            "description": "Recover the SQL statement and fix obvious syntax issues",
            "prompt": (
                "Extract the SQL query from this database error. If the query is malformed, fix "
                "only the syntax issue that caused the failure. Preserve table names, aliases, "
                "filters, and parameters. Return only the SQL.\n\nInput:\n{text}"
            ),
        },
    ]


def build_default_config():
    return {
        "ollama_url": "http://localhost:11434",
        "provider": "ollama",
        "targets": [
            {"name": "Chinese", "emoji": "🇨🇳"},
            {"name": "French", "emoji": "🇫🇷"},
            {"name": "English", "emoji": "🇺🇸"},
        ],
        "gemini": {
            "api_key": "",
            "model": DEFAULT_GEMINI_MODEL,
            "models": DEFAULT_GEMINI_MODELS,
            "transport": "auto",
            "playwright_url": "https://gemini.google.com/app",
            "playwright_profile_dir": "~/Library/Application Support/SmartTranslator/gemini-playwright-profile",
            "playwright_timeout_sec": 90,
        },
        "prompts": {
            "correct": (
                "You are a senior editor. Improve grammar, spelling, punctuation, and clarity "
                "while preserving the original language, tone, formatting, links, placeholders, "
                "markdown, code, and line breaks. Make the smallest changes needed when the text "
                "is already good. Return only the revised text.\n\nInput:\n{text}"
            ),
            "translate": (
                "You are a professional translator. Translate the input into {action}. Preserve "
                "meaning, tone, emphasis, markdown, code, lists, links, placeholders, and line "
                "breaks. Do not add explanations, quotes, or notes. Return only the translated "
                "text.\n\nInput:\n{text}"
            ),
        },
        "use_cases": build_default_use_cases(),
    }


class OllamaClient:
    """Handles all interactions with the Ollama API."""

    def __init__(self, base_url):
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=4, pool_maxsize=8)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.update_base_url(base_url)

    def update_base_url(self, base_url):
        self.base_url = base_url.rstrip("/")

    def check_connection(self):
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=(1.5, 3))
            response.raise_for_status()
            return True
        except Exception:
            return False

    def fetch_models(self):
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=(2, 5))
            response.raise_for_status()
            return [model["name"] for model in response.json().get("models", [])]
        except Exception as exc:
            logging.error(f"Failed to fetch models: {exc}")
            return None

    def generate(self, model, prompt):
        try:
            response = self.session.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=(3, 120),
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except Exception as exc:
            logging.error(f"Generation failed: {exc}")
            raise


class GeminiClient:
    """Minimal Gemini REST client."""

    API_BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self):
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=4, pool_maxsize=8)
        self.session.mount("https://", adapter)

    def check_connection(self, api_key):
        if not api_key:
            return False
        try:
            response = self.session.get(
                f"{self.API_BASE}/models",
                headers={"x-goog-api-key": api_key},
                timeout=(2, 5),
            )
            response.raise_for_status()
            return True
        except Exception:
            return False

    def fetch_models(self, api_key):
        if not api_key:
            return None
        try:
            response = self.session.get(
                f"{self.API_BASE}/models",
                headers={"x-goog-api-key": api_key},
                timeout=(2, 10),
            )
            response.raise_for_status()
            models = response.json().get("models", [])
            return [
                model["name"].replace("models/", "")
                for model in models
                if "generateContent" in model.get("supportedGenerationMethods", [])
            ]
        except Exception as exc:
            logging.error(f"Failed to fetch Gemini models: {exc}")
            return None

    def generate(self, api_key, model, prompt):
        response = self.session.post(
            f"{self.API_BASE}/models/{model}:generateContent",
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}],
                    }
                ],
                "generationConfig": {
                    "temperature": 0.2,
                    "topP": 0.95,
                    "maxOutputTokens": 2048,
                },
            },
            timeout=(3, 45),
        )
        response.raise_for_status()
        payload = response.json()
        return self.extract_text(payload)

    def extract_text(self, payload):
        parts = []
        for candidate in payload.get("candidates", []):
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                text = part.get("text")
                if text:
                    parts.append(text)
            if parts:
                break
        return "\n".join(parts).strip()


class GeminiPlaywrightClient:
    """Calls an external Playwright bridge so py2app does not need to bundle Playwright."""

    def generate(self, prompt, profile_dir, page_url, timeout_sec):
        bridge_path = self.get_bridge_path()
        python_cmd = os.environ.get("SMART_TRANSLATOR_PLAYWRIGHT_PYTHON", "python3")
        payload = {
            "prompt": prompt,
            "profile_dir": profile_dir,
            "page_url": page_url,
            "timeout_sec": timeout_sec,
        }

        try:
            result = subprocess.run(
                [python_cmd, bridge_path],
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                timeout=max(30, int(timeout_sec) + 20),
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"Playwright bridge Python not found: {python_cmd}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Playwright bridge timed out") from exc

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()

        try:
            payload = json.loads(stdout) if stdout else {}
        except json.JSONDecodeError:
            payload = {}

        if result.returncode == 0 and payload.get("ok") and payload.get("text"):
            return payload["text"]

        error_message = payload.get("error") or stderr or stdout or "Playwright bridge failed"
        raise RuntimeError(error_message)

    def get_bridge_path(self):
        resource_dir = os.environ.get("RESOURCEPATH") or os.path.dirname(os.path.abspath(__file__))
        bridge_path = os.path.join(resource_dir, "gemini_playwright_bridge.py")
        if not os.path.exists(bridge_path):
            raise RuntimeError(f"Playwright bridge not found at {bridge_path}")
        return bridge_path


class SmartTranslatorApp(rumps.App):
    def __init__(self):
        super().__init__(APP_TITLE_ONLINE, quit_button=None)
        self.clipboard_history = deque(maxlen=12)
        self.is_processing = False
        self.state_lock = threading.Lock()
        self.refresh_lock = threading.Lock()
        self._refreshing_models = False
        self._attempted_model_bootstrap = False
        self._last_menu_snapshot = None

        # Paths
        self.app_support_dir = os.path.expanduser("~/Library/Application Support/SmartTranslator/")
        self.models_file = os.path.join(self.app_support_dir, "models.json")
        self.config_file = os.path.join(self.app_support_dir, "config.json")

        os.makedirs(self.app_support_dir, exist_ok=True)

        # State
        self.config = self.load_config()
        self.client = OllamaClient(self.config["ollama_url"])
        self.gemini_client = GeminiClient()
        self.gemini_playwright_client = GeminiPlaywrightClient()
        self.available_models, self.model = self.load_models()
        self.online = False
        self.processing_menu_items = []
        self.correct_item = None
        self.status_item = None
        self.hint_item = None
        self.undo_item = None

        self.setup_menu()
        self.start_connection_poll()
        self.start_hotkey_listener()
        logging.info("App initialized")

    def load_config(self):
        default_config = build_default_config()
        if not os.path.exists(self.config_file):
            return default_config

        try:
            with open(self.config_file, "r") as file_handle:
                user_config = json.load(file_handle)
        except Exception as exc:
            logging.error(f"Config load error: {exc}")
            return default_config

        config = dict(default_config)
        for key, value in user_config.items():
            if key not in {"prompts", "use_cases", "gemini"}:
                config[key] = value

        prompts = dict(default_config["prompts"])
        prompts.update(user_config.get("prompts", {}))
        for prompt_name, legacy_prompt in LEGACY_DEFAULT_PROMPTS.items():
            if prompts.get(prompt_name) == legacy_prompt:
                prompts[prompt_name] = default_config["prompts"][prompt_name]
        config["prompts"] = prompts

        gemini_config = dict(default_config["gemini"])
        gemini_config.update(user_config.get("gemini", {}))
        if user_config.get("gemini_api_key") and not gemini_config.get("api_key"):
            gemini_config["api_key"] = user_config["gemini_api_key"]
        if user_config.get("gemini_model"):
            gemini_config["model"] = user_config["gemini_model"]
        if isinstance(user_config.get("gemini_models"), list):
            gemini_config["models"] = user_config["gemini_models"]
        config["gemini"] = gemini_config

        defaults_by_name = {uc["name"]: uc for uc in default_config["use_cases"]}
        merged_use_cases = []
        seen_names = set()

        for use_case in user_config.get("use_cases", []):
            current = dict(use_case)
            original_name = current.get("name")
            name = original_name
            legacy_use_case = LEGACY_DEFAULT_USE_CASES.get(original_name)
            if name == "Token Saver" and current.get("prompt") == LEGACY_DEFAULT_USE_CASES["Token Saver"]["prompt"]:
                current["name"] = "Token Saver (Aggressive)"
                name = current["name"]
            default_use_case = defaults_by_name.get(name)

            if default_use_case:
                if not current.get("emoji"):
                    current["emoji"] = default_use_case["emoji"]
                if default_use_case.get("processor") and not current.get("processor"):
                    current["processor"] = default_use_case["processor"]
                if default_use_case.get("profile") and not current.get("profile"):
                    current["profile"] = default_use_case["profile"]
                if legacy_use_case and current.get("prompt") == legacy_use_case["prompt"]:
                    current["prompt"] = default_use_case["prompt"]
                if legacy_use_case and current.get("description") == legacy_use_case["description"]:
                    current["description"] = default_use_case["description"]

            if "prompt" in current and "name" in current:
                merged_use_cases.append(current)
                seen_names.add(name)

        for default_use_case in default_config["use_cases"]:
            if default_use_case["name"] not in seen_names:
                merged_use_cases.append(default_use_case)

        config["use_cases"] = merged_use_cases
        return config

    def save_config(self):
        try:
            with open(self.config_file, "w") as file_handle:
                json.dump(self.config, file_handle, indent=2)
            self.setup_menu()
        except Exception as exc:
            logging.error(f"Config save error: {exc}")

    def load_models(self):
        available = []
        current = None
        if os.path.exists(self.models_file):
            try:
                with open(self.models_file, "r") as file_handle:
                    data = json.load(file_handle)
                    available = data.get("models", [])
                    current = data.get("default_model")
            except Exception as exc:
                logging.error(f"Models load error: {exc}")

        if not current and available:
            current = available[0]
        return available, current

    def save_models(self):
        try:
            with open(self.models_file, "w") as file_handle:
                json.dump(
                    {
                        "models": self.available_models,
                        "default_model": self.model,
                        "last_updated": datetime.now().isoformat(),
                    },
                    file_handle,
                    indent=2,
                )
        except Exception as exc:
            logging.error(f"Models save error: {exc}")

    def setup_menu(self):
        self.menu.clear()
        self.processing_menu_items = []

        self.status_item = rumps.MenuItem(self.build_status_line())
        self.status_item.set_callback(None)
        self.menu.add(self.status_item)

        self.hint_item = rumps.MenuItem(self.build_hint_line())
        self.hint_item.set_callback(None)
        self.menu.add(self.hint_item)

        self.menu.add(rumps.separator)

        correct_callback = self.make_action_callback("correct")
        self.correct_item = rumps.MenuItem("✨ Correct Clipboard", callback=correct_callback)
        self.processing_menu_items.append(
            {"item": self.correct_item, "callback": correct_callback, "availability": "selected_provider"}
        )
        self.menu.add(self.correct_item)

        translate_menu = rumps.MenuItem("🌐 Translate")
        targets = self.config.get("targets", [])
        if targets:
            for target in targets:
                label = f"{target.get('emoji', '🌐')} {target['name']}"
                callback = self.make_action_callback(target["name"])
                item = rumps.MenuItem(label, callback=callback)
                self.processing_menu_items.append(
                    {"item": item, "callback": callback, "availability": "selected_provider"}
                )
                translate_menu.add(item)
        else:
            empty_languages = rumps.MenuItem("No languages configured")
            empty_languages.set_callback(None)
            translate_menu.add(empty_languages)
        self.menu.add(translate_menu)

        skills_menu = rumps.MenuItem("⚡ Skills")
        use_cases = self.config.get("use_cases", [])
        if use_cases:
            for use_case in use_cases:
                label = f"{use_case.get('emoji', '⚡')} {use_case['name']}"
                callback = self.make_use_case_callback(use_case)
                item = rumps.MenuItem(label, callback=callback)
                self.processing_menu_items.append(
                    {
                        "item": item,
                        "callback": callback,
                        "availability": self.get_use_case_availability(use_case),
                    }
                )
                skills_menu.add(item)
        else:
            empty_skills = rumps.MenuItem("No skills yet")
            empty_skills.set_callback(None)
            skills_menu.add(empty_skills)
        self.menu.add(skills_menu)

        self.menu.add(rumps.separator)
        self.add_provider_submenu()
        self.add_models_submenu()
        self.add_settings_submenu()

        self.menu.add(rumps.separator)
        self.undo_item = rumps.MenuItem("↩ Undo Last", callback=self.undo_last)
        self.menu.add(self.undo_item)
        self.menu.add(rumps.MenuItem("Quit", callback=rumps.quit_application))

        self.refresh_menu_state(force=True)

    def add_provider_submenu(self):
        current_provider = self.get_selected_provider()
        provider_menu = rumps.MenuItem(f"🧠 Provider: {current_provider.title()}")
        for provider in ("ollama", "gemini"):
            prefix = "●" if provider == current_provider else "○"
            provider_menu.add(
                rumps.MenuItem(f"{prefix} {provider.title()}", callback=self.make_select_provider_callback(provider))
            )
        self.menu.add(provider_menu)

    def add_models_submenu(self):
        current_provider = self.get_selected_provider()
        if current_provider == "gemini":
            models_menu = rumps.MenuItem(f"🤖 Model: {self.short_model_name(self.get_gemini_model())}")
            current_model = self.get_gemini_model()
            cached_models = self.get_gemini_models()
            if cached_models:
                for model_name in cached_models:
                    callback = self.make_select_model_callback(model_name)
                    prefix = "●" if model_name == current_model else "○"
                    models_menu.add(rumps.MenuItem(f"{prefix} {model_name}", callback=callback))
            else:
                current_item = rumps.MenuItem(f"Current: {current_model}")
                current_item.set_callback(None)
                models_menu.add(current_item)
            models_menu.add(rumps.separator)
            models_menu.add(rumps.MenuItem("Change Gemini Model...", callback=self.change_gemini_model))
            models_menu.add(rumps.MenuItem("↻ Refresh Gemini Models", callback=self.refresh_models))
            models_menu.add(rumps.MenuItem("Reconnect Now", callback=self.reconnect_now))
            self.menu.add(models_menu)
            return

        models_menu = rumps.MenuItem(f"🤖 Model: {self.short_model_name(self.model)}")
        if self.available_models:
            for model_name in self.available_models:
                callback = self.make_select_model_callback(model_name)
                prefix = "●" if model_name == self.model else "○"
                models_menu.add(rumps.MenuItem(f"{prefix} {model_name}", callback=callback))
        else:
            none_found = rumps.MenuItem("No cached models")
            none_found.set_callback(None)
            models_menu.add(none_found)

        models_menu.add(rumps.separator)
        models_menu.add(rumps.MenuItem("↻ Refresh Models", callback=self.refresh_models))
        models_menu.add(rumps.MenuItem("Reconnect Now", callback=self.reconnect_now))
        self.menu.add(models_menu)

    def add_settings_submenu(self):
        settings = rumps.MenuItem("⚙️ Settings")
        settings.add(rumps.MenuItem("Change Ollama URL", callback=self.change_url))
        settings.add(rumps.MenuItem("Change Gemini API Key", callback=self.change_gemini_api_key))
        settings.add(rumps.MenuItem("Change Gemini Model", callback=self.change_gemini_model))
        settings.add(rumps.MenuItem("Change Gemini Transport", callback=self.change_gemini_transport))
        settings.add(rumps.MenuItem("Change Playwright Profile Path", callback=self.change_playwright_profile_dir))

        lang_menu = rumps.MenuItem("Manage Languages")
        lang_menu.add(rumps.MenuItem("Add Language...", callback=self.add_language))
        if self.config.get("targets"):
            lang_menu.add(rumps.separator)
            for target in self.config["targets"]:
                lang_menu.add(
                    rumps.MenuItem(
                        f"Remove {target['name']}",
                        callback=self.make_remove_language_callback(target["name"]),
                    )
                )
        settings.add(lang_menu)

        skill_menu = rumps.MenuItem("Manage Skills")
        skill_menu.add(rumps.MenuItem("Add Skill...", callback=self.add_use_case))
        if self.config.get("use_cases"):
            skill_menu.add(rumps.separator)
            for use_case in self.config["use_cases"]:
                skill_menu.add(
                    rumps.MenuItem(
                        f"Remove {use_case['name']}",
                        callback=self.make_remove_use_case_callback(use_case["name"]),
                    )
                )
        settings.add(skill_menu)

        settings.add(rumps.separator)
        settings.add(rumps.MenuItem("Edit Config File", callback=lambda _: self.open_in_text_editor(self.config_file)))
        settings.add(rumps.MenuItem("Open Logs", callback=lambda _: self.open_path(LOG_DIR)))
        settings.add(rumps.MenuItem("Open Config Folder", callback=lambda _: self.open_path(self.app_support_dir)))
        self.menu.add(settings)

    def make_action_callback(self, action):
        return lambda _: self.start_processing_task(self.process_task, action, availability="selected_provider")

    def make_use_case_callback(self, use_case):
        return lambda _: self.start_processing_task(
            self.process_use_case,
            dict(use_case),
            availability=self.get_use_case_availability(use_case),
        )

    def make_select_model_callback(self, model_name):
        return lambda _: self.select_model(model_name)

    def make_select_provider_callback(self, provider):
        return lambda _: self.select_provider(provider)

    def make_remove_language_callback(self, name):
        return lambda _: self.remove_language(name)

    def make_remove_use_case_callback(self, name):
        return lambda _: self.remove_use_case(name)

    def build_status_line(self):
        provider = self.get_selected_provider()
        model_label = self.short_model_name(self.get_selected_model_name())
        if self.is_processing:
            return f"Status: Working with {provider.title()} • {model_label}"
        if provider == "gemini":
            if self.is_gemini_ready():
                return f"Status: Gemini ready • {model_label}"
            return "Status: Gemini needs API key or Playwright session"
        if self.is_ollama_ready():
            return f"Status: Ollama ready • {model_label}"
        if self.online:
            return "Status: Ollama connected • refresh models"
        return "Status: Ollama offline • start server"

    def build_hint_line(self):
        provider = self.get_selected_provider()
        if provider == "gemini":
            return f"Provider: Gemini via {self.get_gemini_transport()}"
        if self.is_ollama_ready():
            return "Hotkey: Ctrl+Cmd+C for instant correction"
        return "Safe skills work without Ollama; switch provider to Gemini if needed"

    def get_selected_provider(self):
        provider = self.config.get("provider", "ollama")
        return provider if provider in SUPPORTED_PROVIDERS else "ollama"

    def get_selected_model_name(self):
        if self.get_selected_provider() == "gemini":
            return self.get_gemini_model()
        return self.model

    def is_ollama_ready(self):
        return self.online and bool(self.model)

    def is_gemini_ready(self):
        transport = self.get_gemini_transport()
        if transport == "api":
            return bool(self.get_gemini_api_key())
        return True

    def is_selected_provider_ready(self):
        if self.get_selected_provider() == "gemini":
            return self.is_gemini_ready()
        return self.is_ollama_ready()

    def get_use_case_availability(self, use_case):
        processor = use_case.get("processor")
        if processor == "deterministic":
            return "deterministic"
        if processor == "gemini":
            return "gemini"
        return "selected_provider"

    def is_availability_ready(self, availability):
        if availability == "deterministic":
            return True
        if availability == "gemini":
            return self.is_gemini_ready()
        return self.is_selected_provider_ready()

    def build_unavailable_message(self, availability):
        if availability == "gemini":
            transport = self.get_gemini_transport()
            if transport == "api":
                return ("Gemini unavailable", "Set GEMINI_API_KEY, GOOGLE_API_KEY, or a Gemini key in Settings")
            return ("Gemini unavailable", "Configure Playwright login or switch Gemini transport")

        if self.get_selected_provider() == "gemini":
            transport = self.get_gemini_transport()
            if transport == "api":
                return ("Gemini unavailable", "Set GEMINI_API_KEY, GOOGLE_API_KEY, or a Gemini key in Settings")
            return ("Gemini unavailable", "Configure Playwright login or switch Gemini transport")

        return ("Ollama unavailable", "Start Ollama and refresh models first")

    def get_gemini_transport(self):
        transport = self.config.get("gemini", {}).get("transport", "auto").strip().lower()
        return transport if transport in {"auto", "api", "playwright"} else "auto"

    def get_playwright_profile_dir(self):
        path = self.config.get("gemini", {}).get("playwright_profile_dir", "")
        return os.path.expanduser(path.strip()) if path else os.path.expanduser(
            "~/Library/Application Support/SmartTranslator/gemini-playwright-profile"
        )

    def get_playwright_url(self):
        return self.config.get("gemini", {}).get("playwright_url", "https://gemini.google.com/app").strip()

    def get_playwright_timeout_sec(self):
        value = self.config.get("gemini", {}).get("playwright_timeout_sec", 90)
        try:
            return max(15, int(value))
        except (TypeError, ValueError):
            return 90

    def refresh_menu_state(self, force=False):
        provider_ready = self.is_selected_provider_ready()
        undo_enabled = len(self.clipboard_history) > 1
        snapshot = (
            self.get_selected_provider(),
            self.get_selected_model_name(),
            provider_ready,
            self.is_processing,
            undo_enabled,
            self.build_status_line(),
            self.build_hint_line(),
        )

        if not force and snapshot == self._last_menu_snapshot:
            return

        self.status_item.title = snapshot[5]
        self.hint_item.title = snapshot[6]

        for entry in self.processing_menu_items:
            enabled = not self.is_processing and self.is_availability_ready(entry["availability"])
            entry["item"].set_callback(entry["callback"] if enabled else None)

        if self.undo_item:
            self.undo_item.set_callback(self.undo_last if undo_enabled else None)

        self.update_title()
        self._last_menu_snapshot = snapshot

    def update_title(self):
        if self.is_processing:
            self.title = APP_TITLE_BUSY
        elif self.is_selected_provider_ready():
            self.title = APP_TITLE_ONLINE
        else:
            self.title = APP_TITLE_OFFLINE

    def start_connection_poll(self):
        def poll():
            while True:
                previous_state = self.online
                self.online = self.client.check_connection()

                if self.online and (not previous_state or not self._attempted_model_bootstrap):
                    self._attempted_model_bootstrap = True
                    self.refresh_models_in_background(notify=False)
                else:
                    self.refresh_menu_state(force=self.online != previous_state)

                threading.Event().wait(6 if not self.online else 12)

        threading.Thread(target=poll, daemon=True).start()

    def start_hotkey_listener(self):
        """Starts a background thread to listen for global hotkeys."""
        kb_controller = keyboard.Controller()

        def on_hotkey():
            if not self.is_selected_provider_ready():
                return
            if not self.begin_processing():
                return

            logging.info("Hotkey Ctrl+Cmd+C pressed")

            def task():
                try:
                    with kb_controller.pressed(keyboard.Key.cmd):
                        kb_controller.tap("c")

                    threading.Event().wait(0.15)
                    self.process_task("correct")
                finally:
                    self.finish_processing()

            threading.Thread(target=task, daemon=True).start()

        def listener_thread():
            try:
                with keyboard.GlobalHotKeys({"<ctrl>+<cmd>+c": on_hotkey}) as hotkeys:
                    logging.info("Hotkey listener started for <ctrl>+<cmd>+c")
                    hotkeys.join()
            except Exception as exc:
                logging.error(f"Hotkey listener error: {exc}")
                if "trusted" in str(exc).lower() or "accessibility" in str(exc).lower():
                    logging.warning("Accessibility permissions missing for hotkey listener")

        threading.Thread(target=listener_thread, daemon=True).start()

    def begin_processing(self):
        with self.state_lock:
            if self.is_processing:
                return False
            self.is_processing = True
        self.refresh_menu_state(force=True)
        return True

    def finish_processing(self):
        with self.state_lock:
            self.is_processing = False
        self.refresh_menu_state(force=True)

    def start_processing_task(self, handler, *args, availability="selected_provider"):
        if not self.is_availability_ready(availability):
            title, message = self.build_unavailable_message(availability)
            rumps.notification(title, "Action unavailable", message)
            return
        if not self.begin_processing():
            return

        def task():
            try:
                handler(*args)
            finally:
                self.finish_processing()

        threading.Thread(target=task, daemon=True).start()

    def refresh_models_in_background(self, notify=True):
        with self.refresh_lock:
            if self._refreshing_models:
                return
            self._refreshing_models = True

        provider = self.get_selected_provider()

        def task():
            try:
                self.title = APP_TITLE_BUSY
                if provider == "gemini":
                    self.refresh_gemini_models(notify=notify)
                    return

                models = self.client.fetch_models()
                if models is None:
                    self.online = False
                    if notify:
                        rumps.notification("Models", "Unable to reach Ollama", "Check the URL and make sure Ollama is running")
                elif models:
                    self.online = True
                    models_changed = models != self.available_models
                    selected_model = self.model if self.model in models else models[0]
                    selection_changed = selected_model != self.model

                    self.available_models = models
                    self.model = selected_model
                    self.save_models()

                    if models_changed or selection_changed:
                        self.setup_menu()
                    else:
                        self.refresh_menu_state(force=True)

                    if notify:
                        rumps.notification("Models", f"Found {len(models)} model(s)", self.short_model_name(self.model))
                else:
                    self.online = True
                    self.available_models = []
                    self.model = None
                    self.save_models()
                    self.setup_menu()
                    if notify:
                        rumps.notification("Models", "No models found", "Check that Ollama has pulled at least one model")
            finally:
                with self.refresh_lock:
                    self._refreshing_models = False
                self.refresh_menu_state(force=True)

        threading.Thread(target=task, daemon=True).start()

    def refresh_gemini_models(self, notify=True):
        api_key = self.get_gemini_api_key()
        if not api_key:
            if notify:
                rumps.notification(
                    "Gemini Models",
                    "API key required",
                    "Set GEMINI_API_KEY, GOOGLE_API_KEY, or a Gemini key in Settings",
                )
            self.refresh_menu_state(force=True)
            return

        models = self.gemini_client.fetch_models(api_key)
        if models is None:
            if notify:
                rumps.notification("Gemini Models", "Unable to reach Gemini", "Check the API key and network")
            self.refresh_menu_state(force=True)
            return

        self.config.setdefault("gemini", {})
        self.config["gemini"]["models"] = models or DEFAULT_GEMINI_MODELS
        current_model = self.get_gemini_model()
        if models and current_model not in models:
            self.config["gemini"]["model"] = DEFAULT_GEMINI_MODEL if DEFAULT_GEMINI_MODEL in models else models[0]

        self.save_config()
        if notify:
            rumps.notification("Gemini Models", f"Found {len(models)} model(s)", self.short_model_name(self.get_gemini_model()))

    def reconnect_now(self, _):
        if self.get_selected_provider() == "gemini":
            api_key = self.get_gemini_api_key()
            transport = self.get_gemini_transport()
            if api_key and self.gemini_client.check_connection(api_key):
                self.refresh_models_in_background(notify=True)
                return
            if transport == "api":
                rumps.notification("Gemini", "Offline", "Check the API key and network")
            else:
                rumps.notification("Gemini", "Ready", "Playwright login is checked when an action runs")
            self.refresh_menu_state(force=True)
            return

        self._attempted_model_bootstrap = False
        self.online = self.client.check_connection()
        self.refresh_menu_state(force=True)
        if self.online:
            self.refresh_models_in_background(notify=True)
        else:
            rumps.notification("Ollama", "Offline", "Check the server URL and local Ollama process")

    def select_model(self, name):
        if self.get_selected_provider() == "gemini":
            self.config.setdefault("gemini", {})
            self.config["gemini"]["model"] = name
            cached_models = self.get_gemini_models()
            if name not in cached_models:
                self.config["gemini"]["models"] = cached_models + [name]
            self.save_config()
            rumps.notification("Model Changed", "", f"Using {name}")
            return

        self.model = name
        self.save_models()
        self.setup_menu()
        rumps.notification("Model Changed", "", f"Using {name}")

    def select_provider(self, provider):
        if provider not in SUPPORTED_PROVIDERS:
            return
        self.config["provider"] = provider
        self.save_config()
        self.refresh_menu_state(force=True)
        rumps.notification("Provider Changed", "", f"Using {provider.title()}")

    def refresh_models(self, _):
        self.refresh_models_in_background(notify=True)

    def read_clipboard_text(self):
        text = pyperclip.paste()
        if not text or not text.strip():
            rumps.notification("Clipboard Empty", "", "Copy some text first")
            return None
        return text

    def process_task(self, action):
        text = self.read_clipboard_text()
        if text is None:
            return

        logging.info(f"Processing action: {action}")
        prompt_template = self.config["prompts"]["correct"] if action == "correct" else self.config["prompts"]["translate"]
        prompt = prompt_template.format(text=text, action=action)
        result = self.generate_with_selected_provider(prompt)

        if not result:
            rumps.notification("Error", "Empty result", "")
            return

        emoji = "✏️" if action == "correct" else "🌐"
        if action != "correct":
            for target in self.config.get("targets", []):
                if target["name"] == action:
                    emoji = target.get("emoji", "🌐")
                    break

        self.copy_result(text, result)
        rumps.notification("Success", f"{emoji} {action} complete", self.preview_text(result))

    def process_use_case(self, use_case):
        text = self.read_clipboard_text()
        if text is None:
            return

        logging.info(f"Processing skill: {use_case['name']}")
        if use_case.get("processor") == "deterministic":
            result = self.run_deterministic_use_case(use_case, text)
        elif use_case.get("processor") == "gemini":
            result = self.run_gemini_use_case(use_case, text)
        else:
            prompt = use_case["prompt"].format(text=text)
            result = self.generate_with_selected_provider(prompt)
        if not result:
            rumps.notification("Error", "Empty result", "")
            return

        self.copy_result(text, result)
        rumps.notification(
            "Success",
            f"{use_case.get('emoji', '⚡')} {use_case['name']} complete",
            self.preview_text(result),
        )

    def run_deterministic_use_case(self, use_case, text):
        profile = use_case.get("profile")
        if profile == "token_saver_safe":
            return self.safe_token_saver_cleanup(text)
        return text

    def run_gemini_use_case(self, use_case, text):
        profile = use_case.get("profile")
        if profile == "token_saver_aggressive":
            return self.run_gemini_token_saver(text, use_case)

        prompt = use_case["prompt"].format(text=text)
        return self.generate_with_gemini(prompt)

    def run_gemini_token_saver(self, text, use_case):
        safe_result = self.safe_token_saver_cleanup(text)
        prompt = use_case["prompt"].format(text=safe_result)

        try:
            result = self.generate_with_gemini(prompt)
        except Exception as exc:
            logging.warning(f"Gemini token saver fallback triggered: {exc}")
            rumps.notification(
                "Gemini Fallback",
                "Used safe token saver instead",
                self.preview_text(str(exc), limit=96),
            )
            return safe_result

        if not result:
            rumps.notification("Gemini Fallback", "Used safe token saver instead", "Gemini returned an empty response")
            return safe_result

        return result

    def generate_with_selected_provider(self, prompt):
        if self.get_selected_provider() == "gemini":
            return self.generate_with_gemini(prompt)
        return self.client.generate(self.model, prompt)

    def generate_with_gemini(self, prompt):
        api_key = self.get_gemini_api_key()
        model = self.get_gemini_model()
        transport = self.get_gemini_transport()
        errors = []

        if transport in {"auto", "api"} and api_key:
            try:
                return self.gemini_client.generate(api_key, model, prompt)
            except requests.HTTPError as exc:
                errors.append(self.extract_http_error_message(exc))
                if transport == "api":
                    raise RuntimeError(errors[-1]) from exc
            except requests.RequestException as exc:
                errors.append("Gemini API request failed")
                if transport == "api":
                    raise RuntimeError(errors[-1]) from exc
        elif transport == "api":
            raise RuntimeError("Set GEMINI_API_KEY, GOOGLE_API_KEY, or configure a Gemini key in Settings")

        if transport in {"auto", "playwright"}:
            try:
                return self.gemini_playwright_client.generate(
                    prompt,
                    self.get_playwright_profile_dir(),
                    self.get_playwright_url(),
                    self.get_playwright_timeout_sec(),
                )
            except Exception as exc:
                errors.append(str(exc))
                if transport == "playwright":
                    raise RuntimeError(errors[-1]) from exc

        if errors:
            raise RuntimeError(" | ".join(errors))
        raise RuntimeError("No Gemini transport is configured")

    def get_gemini_api_key(self):
        return (
            os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or self.config.get("gemini", {}).get("api_key", "").strip()
        )

    def get_gemini_model(self):
        return self.config.get("gemini", {}).get("model", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL

    def get_gemini_models(self):
        models = self.config.get("gemini", {}).get("models", DEFAULT_GEMINI_MODELS)
        if not isinstance(models, list):
            return DEFAULT_GEMINI_MODELS
        return [model for model in models if isinstance(model, str) and model.strip()]

    def extract_http_error_message(self, error):
        response = getattr(error, "response", None)
        if response is None:
            return "Gemini returned an HTTP error"
        try:
            payload = response.json()
            return payload.get("error", {}).get("message") or f"Gemini HTTP {response.status_code}"
        except Exception:
            return f"Gemini HTTP {response.status_code}"

    def safe_token_saver_cleanup(self, text):
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        segments = re.split(r"(```.*?```)", normalized, flags=re.DOTALL)
        cleaned_segments = []

        for segment in segments:
            if not segment:
                continue
            if segment.startswith("```") and segment.endswith("```"):
                cleaned_segments.append(segment.strip())
            else:
                cleaned_segments.append(self.clean_non_code_segment(segment))

        result = "\n\n".join(part for part in cleaned_segments if part)
        return result.strip() or normalized.strip()

    def clean_non_code_segment(self, segment):
        cleaned_lines = []
        previous_blank = True

        for raw_line in segment.split("\n"):
            stripped = raw_line.strip()

            if not stripped:
                if cleaned_lines and not previous_blank:
                    cleaned_lines.append("")
                previous_blank = True
                continue

            if self.is_discardable_token_saver_line(stripped):
                continue

            normalized_line = self.normalize_plain_line(raw_line)
            if cleaned_lines and normalized_line == cleaned_lines[-1]:
                continue

            cleaned_lines.append(normalized_line)
            previous_blank = False

        while cleaned_lines and cleaned_lines[-1] == "":
            cleaned_lines.pop()

        return "\n".join(cleaned_lines)

    def is_discardable_token_saver_line(self, stripped_line):
        lower = stripped_line.lower().strip(".,!?:;")

        if stripped_line.startswith(">"):
            return True
        if re.match(r"^on .+wrote:$", lower):
            return True
        if re.match(r"^(from|sent|to|subject|cc|bcc):", lower):
            return True
        if lower in {
            "hi",
            "hello",
            "hey",
            "thanks",
            "thank you",
            "many thanks",
            "best",
            "best regards",
            "regards",
            "cheers",
            "sincerely",
        }:
            return True
        if lower.startswith("sent from my ") or lower == "please let me know":
            return True
        return False

    def normalize_plain_line(self, raw_line):
        stripped = raw_line.strip()
        bullet_match = re.match(r"^([-*]|\d+\.)\s+(.*)$", stripped)
        if bullet_match:
            bullet_text = re.sub(r"\s+", " ", bullet_match.group(2)).strip()
            return f"{bullet_match.group(1)} {bullet_text}"
        return re.sub(r"\s+", " ", stripped)

    def mask_secret(self, value):
        if not value:
            return ""
        if len(value) <= 8:
            return "*" * len(value)
        return f"{value[:4]}...{value[-4:]}"

    def copy_result(self, source_text, result_text):
        pyperclip.copy(result_text)
        if not self.clipboard_history or self.clipboard_history[-1] != source_text:
            self.clipboard_history.append(source_text)
        if not self.clipboard_history or self.clipboard_history[-1] != result_text:
            self.clipboard_history.append(result_text)
        self.refresh_menu_state(force=True)

    def preview_text(self, text, limit=72):
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3] + "..."

    def short_model_name(self, model_name):
        if not model_name:
            return "None"
        return model_name.split(":")[0]

    def change_url(self, _):
        window = rumps.Window(
            "Enter Ollama URL",
            "Settings",
            default_text=self.config["ollama_url"],
            ok="Save",
            cancel="Cancel",
        )
        result = window.run()
        if not result.clicked:
            return

        new_url = result.text.strip()
        if not new_url:
            rumps.notification("Settings", "URL not changed", "A valid Ollama URL is required")
            return

        self.config["ollama_url"] = new_url
        self.client.update_base_url(new_url)
        self._attempted_model_bootstrap = False
        self.online = False
        self.save_config()
        self.refresh_menu_state(force=True)
        self.reconnect_now(None)
        rumps.notification("Settings", "URL Updated", new_url)

    def change_gemini_api_key(self, _):
        current_key = self.config.get("gemini", {}).get("api_key", "")
        window = rumps.Window(
            message=(
                "Set a Gemini API key for the Gemini provider and Token Saver (Aggressive).\n"
                "Leave blank to use GEMINI_API_KEY or GOOGLE_API_KEY."
            ),
            title="Gemini API Key",
            default_text=current_key,
            ok="Save",
            cancel="Cancel",
            dimensions=(420, 120),
        )
        result = window.run()
        if not result.clicked:
            return

        self.config.setdefault("gemini", {})
        self.config["gemini"]["api_key"] = result.text.strip()
        self.save_config()

        summary = (
            "Using GEMINI_API_KEY / GOOGLE_API_KEY if set"
            if not self.config["gemini"]["api_key"]
            else self.mask_secret(self.config["gemini"]["api_key"])
        )
        rumps.notification("Settings", "Gemini key updated", summary)

    def change_gemini_model(self, _):
        window = rumps.Window(
            message="Set the Gemini model used by the Gemini provider and Token Saver (Aggressive).",
            title="Gemini Model",
            default_text=self.get_gemini_model(),
            ok="Save",
            cancel="Cancel",
        )
        result = window.run()
        if not result.clicked:
            return

        model_name = result.text.strip() or DEFAULT_GEMINI_MODEL
        self.config.setdefault("gemini", {})
        self.config["gemini"]["model"] = model_name
        self.save_config()
        rumps.notification("Settings", "Gemini model updated", model_name)

    def change_gemini_transport(self, _):
        window = rumps.Window(
            message="Set Gemini transport: auto, api, or playwright.",
            title="Gemini Transport",
            default_text=self.get_gemini_transport(),
            ok="Save",
            cancel="Cancel",
        )
        result = window.run()
        if not result.clicked:
            return

        transport = result.text.strip().lower() or "auto"
        if transport not in {"auto", "api", "playwright"}:
            rumps.notification("Settings", "Invalid Gemini transport", "Use auto, api, or playwright")
            return

        self.config.setdefault("gemini", {})
        self.config["gemini"]["transport"] = transport
        self.save_config()
        rumps.notification("Settings", "Gemini transport updated", transport)

    def change_playwright_profile_dir(self, _):
        window = rumps.Window(
            message="Set the persistent browser profile path used for Gemini Playwright login.",
            title="Playwright Profile Path",
            default_text=self.get_playwright_profile_dir(),
            ok="Save",
            cancel="Cancel",
            dimensions=(460, 120),
        )
        result = window.run()
        if not result.clicked:
            return

        profile_dir = result.text.strip() or "~/Library/Application Support/SmartTranslator/gemini-playwright-profile"
        self.config.setdefault("gemini", {})
        self.config["gemini"]["playwright_profile_dir"] = profile_dir
        self.save_config()
        rumps.notification("Settings", "Playwright profile updated", os.path.expanduser(profile_dir))

    def add_language(self, _):
        window = rumps.Window(
            message="Enter a language name for the Translate menu.",
            title="Add Language",
            default_text="",
            ok="Next",
            cancel="Cancel",
        )
        result = window.run()
        if not result.clicked or not result.text.strip():
            return

        language_name = result.text.strip()
        emoji_window = rumps.Window(
            message=f"Enter an emoji for {language_name} (optional)",
            title="Language Emoji",
            default_text="🌐",
            ok="Add",
            cancel="Cancel",
        )
        emoji_result = emoji_window.run()
        if not emoji_result.clicked:
            return

        emoji = emoji_result.text.strip() or "🌐"
        self.config["targets"].append({"name": language_name, "emoji": emoji})
        self.save_config()
        rumps.notification("Success", f"Added {language_name}", "")

    def remove_language(self, name):
        self.config["targets"] = [target for target in self.config["targets"] if target["name"] != name]
        self.save_config()
        rumps.notification("Success", f"Removed {name}", "")

    def add_use_case(self, _):
        description_window = rumps.Window(
            message=(
                "Describe the clipboard skill you want.\n\n"
                "Examples:\n"
                "• Remove filler while keeping technical detail\n"
                "• Turn meeting notes into crisp action items\n"
                "• Rewrite text in a firm but polite tone\n"
                "• Strip HTML and keep clean markdown"
            ),
            title="New Skill",
            default_text="",
            ok="Next",
            cancel="Cancel",
            dimensions=(340, 140),
        )
        description_result = description_window.run()
        if not description_result.clicked or not description_result.text.strip():
            return

        user_description = description_result.text.strip()

        name_window = rumps.Window(
            message="Give this skill a short menu name.",
            title="Skill Name",
            default_text="",
            ok="Next",
            cancel="Cancel",
        )
        name_result = name_window.run()
        if not name_result.clicked or not name_result.text.strip():
            return

        skill_name = name_result.text.strip()

        emoji_window = rumps.Window(
            message=f"Choose an emoji for '{skill_name}' (optional)",
            title="Skill Emoji",
            default_text="⚡",
            ok="Generate Prompt",
            cancel="Cancel",
        )
        emoji_result = emoji_window.run()
        if not emoji_result.clicked:
            return

        skill_emoji = emoji_result.text.strip() or "⚡"
        if not self.is_selected_provider_ready():
            title, message = self.build_unavailable_message("selected_provider")
            rumps.notification(title, "Prompt generation unavailable", message)
            return

        self.title = APP_TITLE_BUSY
        try:
            refined_prompt = self.generate_with_selected_provider(self.build_skill_meta_prompt(user_description))
            refined_prompt = self.normalize_generated_prompt(refined_prompt)
        except Exception as exc:
            logging.error(f"Prompt generation failed: {exc}")
            rumps.notification("Error", "Failed to generate prompt", str(exc))
            self.update_title()
            return

        validate_window = rumps.Window(
            message=(
                "Review the generated skill prompt.\n"
                "Keep the {text} placeholder so clipboard content can be inserted."
            ),
            title=f"Validate Prompt for '{skill_name}'",
            default_text=refined_prompt,
            ok="Save",
            cancel="Cancel",
            dimensions=(460, 220),
        )
        validate_result = validate_window.run()
        if not validate_result.clicked:
            self.update_title()
            return

        final_prompt = self.normalize_generated_prompt(validate_result.text.strip())
        if not final_prompt:
            rumps.notification("Error", "Prompt cannot be empty", "")
            self.update_title()
            return

        self.config.setdefault("use_cases", []).append(
            {
                "name": skill_name,
                "emoji": skill_emoji,
                "description": user_description,
                "prompt": final_prompt,
            }
        )
        self.save_config()
        self.update_title()
        rumps.notification("Success", f"Added skill: {skill_name}", "Available from the menu now")

    def remove_use_case(self, name):
        self.config["use_cases"] = [uc for uc in self.config.get("use_cases", []) if uc["name"] != name]
        self.save_config()
        rumps.notification("Success", f"Removed {name}", "")

    def build_skill_meta_prompt(self, user_description):
        return (
            "You are writing a reusable prompt template for a clipboard-powered text skill in a "
            "macOS menu bar app.\n"
            "Generate one prompt template that another LLM will execute later.\n\n"
            "Requirements:\n"
            "- Make the role and task explicit\n"
            "- Preserve formatting, lists, links, placeholders, code, and line breaks unless the "
            "user explicitly wants them changed\n"
            "- Tell the model to return only the transformed text with no commentary\n"
            "- Keep the prompt concise but specific\n"
            "- End with the exact block:\nInput:\n{text}\n\n"
            f"User goal:\n{user_description}\n\n"
            "Return only the prompt template."
        )

    def normalize_generated_prompt(self, prompt):
        cleaned = self.strip_code_fences(prompt).strip().strip('"')
        if "return only" not in cleaned.lower():
            cleaned = f"{cleaned.rstrip()}\n\nReturn only the transformed text."
        if "{text}" not in cleaned:
            cleaned = f"{cleaned.rstrip()}\n\nInput:\n{{text}}"
        return cleaned

    def strip_code_fences(self, text):
        if not text.startswith("```"):
            return text
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)

    def open_path(self, path):
        subprocess.run(["open", path], check=False)

    def open_in_text_editor(self, path):
        subprocess.run(["open", "-e", path], check=False)

    def undo_last(self, _):
        if len(self.clipboard_history) <= 1:
            rumps.notification("Undo", "Nothing to undo", "")
            return

        self.clipboard_history.pop()
        previous_value = self.clipboard_history[-1]
        pyperclip.copy(previous_value)
        self.refresh_menu_state(force=True)
        rumps.notification("Undone", "Restored previous clipboard", self.preview_text(previous_value))


if __name__ == "__main__":
    import AppKit

    info = AppKit.NSBundle.mainBundle().infoDictionary()
    info["LSUIElement"] = "1"

    app = SmartTranslatorApp()
    rumps.notification("Smart Translator", "Ready", "Click the 🌍 icon to run clipboard actions")
    app.run()

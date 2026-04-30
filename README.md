# Smart Translator for macOS

A privacy-focused macOS menu bar app that uses local LLMs (via [Ollama](https://ollama.com)) for instant text correction, translation, and **custom clipboard skills** — all from your clipboard.

## Screenshots

| Menu | Menu Bar | Processing | Settings |
|------|----------|------------|----------|
| ![Main Menu](assets/main.png) | ![Menu Bar](assets/main_menubar.png) | ![Processing](assets/processing_menubar.png) | ![Settings](assets/settings.png) |

## Key Features

- **Global Hotkey** — Press `Ctrl + Cmd + C` to instantly correct clipboard text.
- **Custom Skills** — Define your own text processing actions (token saving, text cleanup, summarization, tone conversion, etc.). The local LLM turns your description into a stronger reusable prompt, then you validate before saving.
- **Translation** — Translate clipboard text to any language. Add/remove languages on the fly.
- **Smart Correction** — Fix grammar, spelling, and clarity while preserving formatting.
- **Faster Feeling UI** — A cleaner, shorter menu bar state, grouped menu sections, quicker reconnect flow, and reduced polling churn keep the app snappier.
- **Async Processing** — Non-blocking background tasks and connection reuse keep the menu bar responsive.
- **Clipboard History & Undo** — Up to 12 clipboard states with one-click undo back to the previous value.
- **100% Local** — All processing stays on your machine. No data leaves your device.
- **Dynamic Model Selection** — Switch between available Ollama models at runtime.

## Custom Skills

The app goes beyond correction and translation. You can create any clipboard skill:

1. Click **Settings > Manage Skills > Add Skill...**
2. **Describe** what you want (e.g., "remove verbose filler words to save tokens", "strip HTML and clean up formatting")
3. The local LLM **generates a refined prompt** from your description with stronger output constraints
4. **Review and edit** the generated prompt before saving
5. Your new skill appears in the main menu, ready to use

Examples of custom use cases:
- **Token Saver (Safe)** — Deterministically remove quoted replies, greetings, and empty clutter
- **Token Saver (Aggressive)** — Use the model to shorten prose while preserving technical detail
- **HTML Cleaner** — Remove tags and extract clean text
- **Bullet Summarizer** — Condense long text into bullet points
- **Formal Rewriter** — Convert casual text to business tone

## Prerequisites

1. **macOS** (Apple Silicon or Intel)
2. **Ollama** installed and running — [ollama.com](https://ollama.com)
3. At least one local model pulled:
   ```bash
   ollama pull llama3.2   # Fast
   ollama pull mistral    # Higher quality
   ```

## Installation

### Build as macOS App (recommended)

```bash
chmod +x build_script.sh
./build_script.sh
```

Grant **Accessibility** and **Notifications** permissions when prompted.

### Run from Source

```bash
pip install rumps requests pyperclip py2app pynput
python3 smart_translator_dynamic.py
```

## Usage

1. **Copy** text to your clipboard
2. Press `Ctrl + Cmd + C` for instant correction, or click the menu bar icon and choose an action
3. Wait for the **Success** notification
4. **Paste** your processed text

## Configuration

Config is stored at `~/Library/Application Support/SmartTranslator/config.json`.

- **Ollama URL** — Connect to a remote Ollama instance via Settings
- **Prompts** — Edit correction/translation prompt templates in the config file
- **Languages** — Add/remove via Settings > Manage Languages
- **Skills** — Add/remove via Settings > Manage Skills
- **Logs** — View at Settings > Open Logs (`~/Library/Logs/SmartTranslator/`)

## Troubleshooting

- **Hotkey not working** — Add the app to *System Settings > Privacy & Security > Accessibility*
- **"Offline" status** — Verify Ollama is running (`ollama serve`)
- **UI issues** — Check logs via Settings > Open Logs

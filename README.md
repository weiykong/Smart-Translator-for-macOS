# 🌍 Smart Translator for macOS (v1.1.1)

A high-performance, privacy-focused macOS menu bar application that leverages local LLMs (via [Ollama](https://ollama.com)) to provide instant text correction and translation directly through your clipboard.

## ✨ Key Features

*   **⌨️ Global Hotkey:** Press `Ctrl + Cmd + C` to instantly correct the text in your clipboard without opening the menu.
*   **⚡ Asynchronous Engine:** Non-blocking UI ensures your menu bar stays responsive while the LLM processes text in the background.
*   **🛠️ Dynamic Configuration:** Fully customizable translation targets, emojis, and system prompts via a built-in Settings menu.
*   **🌐 Manage Languages:** Add or remove translation languages (e.g., Japanese, Spanish, German) directly from the app interface.
*   **✏️ Smart Correction:** Enhances grammar, spelling, and clarity while strictly preserving your original formatting and line breaks.
*   **🔄 History & Undo:** Maintains a clipboard history (up to 10 items), allowing you to quickly revert any accidental overwrites.
*   **🔒 Privacy First:** 100% local processing. Your data never leaves your machine.
*   **📝 Professional Logging:** Built-in logging system (`~/Library/Logs/SmartTranslator/`) for easy troubleshooting and status monitoring.

## 🛠️ Prerequisites

1.  **macOS** (Apple Silicon or Intel).
2.  **Ollama** must be installed and running.
    *   Download from [ollama.com](https://ollama.com)
    *   Ensure the server is running (`ollama serve`).
3.  **Local Models:** Pull at least one model to get started:
    ```bash
    ollama pull llama3.2  # Recommended for speed
    ollama pull mistral   # Recommended for quality
    ```

## 🚀 Installation & Setup

### Recommended: Build as a macOS App
Building the app creates a standalone `.app` bundle in your `/Applications` folder.

1.  **Clone the Repository**
2.  **Run the Build Script:**
    ```bash
    chmod +x build_script.sh
    ./build_script.sh
    ```
3.  **Grant Permissions:**
    *   **Accessibility:** Required for the app to read/write to your clipboard and listen for the global hotkey.
    *   **Notifications:** Required for the app to provide status updates on completion.

### Alternative: Run from Source
```bash
pip install rumps requests pyperclip py2app pynput
python3 smart_translator_dynamic.py
```

## ⚙️ Advanced Configuration

Smart Translator v1.1.1 introduces a robust configuration system located in:
`~/Library/Application Support/SmartTranslator/config.json`

*   **Change Ollama URL:** Connect to a remote Ollama instance by updating the URL in **Settings**.
*   **Custom Prompts:** Fine-tune how the AI behaves by editing the prompt templates in the config file.
*   **Language List:** Add your own languages with custom emojis via the **Manage Languages** menu.

## 🖥️ Usage

1.  **Copy** text to your clipboard.
2.  **Either:**
    *   Press `Ctrl + Cmd + C` for instant correction.
    *   Click the **🌍 icon** in your menu bar and choose an action.
3.  Wait for the **Success Notification**.
4.  **Paste** your improved or translated text!

## 🔧 Troubleshooting

*   **Hotkey not working:** Ensure "Smart Translator" is added to *System Settings > Privacy & Security > Accessibility*.
*   **"Offline" Status:** Verify Ollama is running and accessible at the configured URL (default: `http://localhost:11434`).
*   **UI Not Updating:** Check the logs via **Settings > Open Logs** to see real-time errors or API timeouts.

---
*Developed with focus on speed, privacy, and extensibility.*

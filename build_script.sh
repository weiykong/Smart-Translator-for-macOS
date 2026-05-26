#!/bin/bash

# Build and Install Smart Translator App
# Requires Apple Silicon (arm64) Python via Homebrew.
# On first run it creates .venv-arm64 and installs dependencies automatically.

set -e

VENV=".venv-arm64"
ARM64_PYTHON="/opt/homebrew/bin/python3"

echo "🔨 Building Smart Translator app (arm64)..."

# ── 1. Ensure the arm64 venv exists ──────────────────────────────────────────
if [ ! -f "$VENV/bin/python" ]; then
    if [ ! -x "$ARM64_PYTHON" ]; then
        echo "❌ Homebrew Python not found at $ARM64_PYTHON"
        echo "   Install it with: brew install python3"
        exit 1
    fi
    echo "📦 Creating arm64 virtual environment..."
    "$ARM64_PYTHON" -m venv "$VENV"
    echo "📦 Installing dependencies..."
    "$VENV/bin/pip" install --quiet rumps requests pyperclip pynput py2app
    echo "✅ Dependencies installed."
fi

# ── 2. Build ──────────────────────────────────────────────────────────────────
rm -rf build dist
"$VENV/bin/python" setup.py py2app

echo "✅ Build successful!"

# ── 3. Verify architecture ────────────────────────────────────────────────────
ARCH=$(file dist/SmartTranslator.app/Contents/MacOS/SmartTranslator | grep -o 'arm64\|x86_64\|universal')
echo "🏗  Binary architecture: $ARCH"

# ── 4. Install to /Applications ───────────────────────────────────────────────
echo "📦 Installing to /Applications..."
if [ -d "/Applications/Smart Translator.app" ]; then
    echo "🗑️  Removing old version..."
    rm -rf "/Applications/Smart Translator.app"
fi
cp -R "dist/SmartTranslator.app" "/Applications/Smart Translator.app"

echo "🎉 Installed: /Applications/Smart Translator.app"
echo ""
echo "⚠️  First launch — grant these permissions when prompted:"
echo "   • Accessibility  (System Settings → Privacy & Security → Accessibility)"
echo "   • Notifications"
echo ""

read -p "Launch Smart Translator now? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    open "/Applications/Smart Translator.app"
fi

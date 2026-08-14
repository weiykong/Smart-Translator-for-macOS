#!/usr/bin/env python3
"""
Helper script to generate models.json configuration file
Run this script to automatically create the models configuration from your Ollama installation
"""

import requests
import json
import os
from datetime import datetime

def fetch_ollama_models():
    """Fetch available models from Ollama API"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        response.raise_for_status()
        
        data = response.json()
        if "models" in data:
            models = [model["name"] for model in data["models"]]
            return models
        else:
            print("No models found in API response")
            return []
            
    except Exception as e:
        print(f"Error fetching models from Ollama: {e}")
        print("Make sure Ollama is running: ollama serve")
        return []

def create_models_config(models, default_model=None):
    """Create models configuration dictionary"""
    if not models:
        return None
    
    # Use first model as default if none specified
    if not default_model:
        default_model = models[0]
    elif default_model not in models:
        print(f"Warning: Default model '{default_model}' not found in available models")
        default_model = models[0]
    
    config = {
        "models": models,
        "default_model": default_model,
        "last_updated": datetime.now().isoformat()
    }
    
    return config

def save_config_file(config, file_path):
    """Save configuration to JSON file"""
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"✅ Configuration saved to: {file_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error saving configuration: {e}")
        return False

def main():
    """Main function"""
    print("🔍 Fetching available Ollama models...")
    
    models = fetch_ollama_models()
    
    if not models:
        print("❌ No models found. Please install some models first:")
        print("   ollama pull llama3.2")
        print("   ollama pull mistral")
        return
    
    print(f"✅ Found {len(models)} models:")
    for i, model in enumerate(models, 1):
        print(f"   {i}. {model}")
    
    # Ask user to select default model
    print(f"\n📝 Select default model (1-{len(models)}) or press Enter for '{models[0]}':")
    try:
        choice = input().strip()
        if choice:
            index = int(choice) - 1
            if 0 <= index < len(models):
                default_model = models[index]
            else:
                print("Invalid choice, using first model as default")
                default_model = models[0]
        else:
            default_model = models[0]
    except (ValueError, KeyboardInterrupt):
        default_model = models[0]
    
    print(f"🎯 Default model: {default_model}")
    
    # Create configuration
    config = create_models_config(models, default_model)
    
    # Save to the standard location
    config_path = os.path.expanduser("~/Library/Application Support/SmartTranslator/models.json")
    
    print(f"\n💾 Saving configuration to: {config_path}")
    
    if save_config_file(config, config_path):
        print("\n🎉 Configuration created successfully!")
        print("You can now start the SmartTranslator app.")
        
        # Also save a copy in current directory for reference
        local_path = "./models.json"
        save_config_file(config, local_path)
        print(f"📄 Copy also saved to: {local_path}")
    else:
        print("\n❌ Failed to create configuration")

if __name__ == "__main__":
    main()
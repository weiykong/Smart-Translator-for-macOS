"""
Setup script to package the SmartTranslator app as a proper macOS application.
This creates a standalone app that can be installed in the Applications folder.
"""

from setuptools import setup

APP = ['smart_translator_dynamic.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': False,
    'packages': ['rumps', 'requests', 'pyperclip'],
    'plist': {
        'LSUIElement': True,
        'CFBundleName': 'SmartTranslator',
        'CFBundleDisplayName': 'Smart Translator',
        'CFBundleIdentifier': 'com.smarttranslator.app',
        'CFBundleVersion': '1.1.0',
        'CFBundleShortVersionString': '1.1.0',
        'NSHumanReadableCopyright': 'Copyright © 2026',
        'NSUserNotificationAlertStyle': 'alert',
    },
    'iconfile': 'icon.icns',
    'includes': ['json', 'os', 'datetime', 'threading', 'logging'],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
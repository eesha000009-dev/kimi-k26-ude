"""
Kimi K2.6 UDE - Main Entry Point (p4a compatible)
====================================================
This is the primary entry point for the Android APK.
python-for-android (p4a) requires a main.py that starts the Kivy app.
"""

import os
import sys

# Ensure the app directory is in the Python path
app_dir = os.path.dirname(os.path.abspath(__file__))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

# Import and run the main Kivy app
from app import main

if __name__ == '__main__':
    main()

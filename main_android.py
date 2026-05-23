"""
Kimi K2.6 UDE - Android Entry Point
=====================================
This is the entry point for the Android APK.
Buildozer will use this as the main entry point.
"""

import os
import sys

# Ensure the app directory is in the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the main app
from app import main

if __name__ == '__main__':
    main()

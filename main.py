"""
Kimi K2.6 UDE - Main Entry Point
==================================
This file is required by python-for-android as the default entry point.
It delegates to main_android.py which contains the actual app startup logic.
"""

import os
import sys

# Ensure the app directory is in the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the main app
from app import main

if __name__ == '__main__':
    main()

#!/bin/bash

# This script builds the application using PyInstaller.

# Activate virtual environment
echo "--- Activating virtual environment ---"
source .venv/bin/activate

# Run PyInstaller
echo "--- Running PyInstaller build ---"
pyinstaller SmartAI.spec --noconfirm

# Deactivate virtual environment (optional)
deactivate

echo "--- Build finished ---"
echo "The executable is located in the 'dist/' directory."

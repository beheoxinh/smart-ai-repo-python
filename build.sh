#!/bin/bash

# Build the application
pipenv run pyinstaller SmartAI.spec

# Create .desktop file
cat > SmartAI.desktop << EOL
[Desktop Entry]
Name=SmartAI
Exec=/usr/local/bin/smart-ai
Icon=/home/WannaBeTheGuy/WwW/MyOwn/python_ai_sidebar/icon.svg
Type=Application
Categories=Development;
EOL

# Optional: copy to applications folder
sudo cp SmartAI.desktop /usr/share/applications/smart-ai.desktop
sudo cp dist/SmartAI /usr/local/bin/smart-ai

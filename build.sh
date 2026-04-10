#!/bin/bash

# --- Configuration ---
APP_NAME="smart-ai"
INSTALL_DIR="/usr/local/share/$APP_NAME"
BIN_DIR="/usr/local/bin"
ICON_NAME="smart-ai-icon.svg"

# --- Build Step ---
echo "Building the application with PyInstaller..."
pipenv run pyinstaller SmartAI.spec
if [ $? -ne 0 ]; then
    echo "PyInstaller build failed. Aborting."
    exit 1
fi

# --- Installation Steps ---
echo "Installing application to $INSTALL_DIR..."

# Clean up previous installation
echo "Removing old installation files..."
sudo rm -f "$BIN_DIR/$APP_NAME"
sudo rm -rf "$INSTALL_DIR"
sudo rm -f "/usr/share/applications/$APP_NAME.desktop"

# Create installation directory
sudo mkdir -p "$INSTALL_DIR"

# Copy application files
echo "Copying application files..."
sudo cp "dist/SmartAI" "$INSTALL_DIR/$APP_NAME"
sudo cp -r "images" "$INSTALL_DIR/"
sudo cp -r "config" "$INSTALL_DIR/"
sudo cp "icon.svg" "$INSTALL_DIR/$ICON_NAME"

# Create symbolic link in bin directory
echo "Creating symbolic link..."
sudo ln -s "$INSTALL_DIR/$APP_NAME" "$BIN_DIR/$APP_NAME"

# --- Create .desktop file ---
echo "Creating .desktop file..."
cat > "$APP_NAME.desktop" << EOL
[Desktop Entry]
Name=SmartAI
Exec=$APP_NAME
Icon=$INSTALL_DIR/$ICON_NAME
Type=Application
Categories=Development;
EOL

# Copy .desktop file to applications folder
echo "Installing .desktop file..."
sudo cp "$APP_NAME.desktop" "/usr/share/applications/"

# Clean up temporary desktop file
rm "$APP_NAME.desktop"

echo "Installation complete!"
echo "You can now run '$APP_NAME' from your terminal or find it in your applications menu."

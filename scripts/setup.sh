#!/bin/bash
# FL Studio MCP Setup Script
#
# This script:
# 1. Checks/guides virtual MIDI port setup (IAC Driver on Mac, loopMIDI on Windows)
# 2. Installs the FL Studio MIDI controller script
# 3. Installs the Piano Roll script (ComposeWithLLM)
# 4. Installs Python dependencies

set -e

echo "=========================================="
echo "FL Studio MCP Setup"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# FL Studio paths
FL_SETTINGS="$HOME/Documents/Image-Line/FL Studio/Settings"
FL_HARDWARE="$FL_SETTINGS/Hardware"
MCP_CONTROLLER_DIR="$FL_HARDWARE/FLStudioMCP"
FL_PIANO_SCRIPTS="$FL_SETTINGS/Piano roll scripts"

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="mac"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
    OS="windows"
else
    OS="linux"
fi

# Step 1: Virtual MIDI Setup
echo "Step 1: Checking Virtual MIDI Setup..."
echo "----------------------------------------------"

if [[ "$OS" == "mac" ]]; then
    # Check if IAC Driver is available
    if system_profiler SPAudioDataType 2>/dev/null | grep -q "IAC Driver"; then
        echo -e "${GREEN}✓ IAC Driver is available${NC}"
    else
        echo -e "${YELLOW}⚠ IAC Driver may not be enabled${NC}"
    fi

    echo ""
    echo "To enable IAC Driver (if not already enabled):"
    echo "  1. Open 'Audio MIDI Setup' (search in Spotlight)"
    echo "  2. Press Cmd+2 or go to Window > Show MIDI Studio"
    echo "  3. Double-click on 'IAC Driver'"
    echo "  4. Check 'Device is online'"
    echo "  5. Click 'Apply'"
    echo ""

    read -p "Press Enter to open Audio MIDI Setup, or 's' to skip: " choice
    if [[ "$choice" != "s" && "$choice" != "S" ]]; then
        open -a "Audio MIDI Setup"
        echo ""
        read -p "Press Enter when IAC Driver is configured..."
    fi
elif [[ "$OS" == "windows" ]]; then
    echo "Windows detected. Please ensure loopMIDI is installed and running."
    echo "Download from: https://www.tobias-erichsen.de/software/loopmidi.html"
    echo ""
    echo "Create a virtual MIDI port in loopMIDI (any name works)."
    echo ""
    read -p "Press Enter when loopMIDI is configured..."
fi

# Step 2: Install FL Studio MIDI Controller
echo ""
echo "Step 2: Installing FL Studio MIDI Controller..."
echo "----------------------------------------------"

# Create FL Studio Hardware directory if it doesn't exist
if [[ ! -d "$FL_HARDWARE" ]]; then
    echo "Creating FL Studio Hardware directory..."
    mkdir -p "$FL_HARDWARE"
fi

# Create MCP controller directory
if [[ ! -d "$MCP_CONTROLLER_DIR" ]]; then
    echo "Creating FLStudioMCP directory..."
    mkdir -p "$MCP_CONTROLLER_DIR"
fi

# Copy the controller script
CONTROLLER_SOURCE="$PROJECT_DIR/fl_controller/device_FLStudioMCP.py"
CONTROLLER_DEST="$MCP_CONTROLLER_DIR/device_FLStudioMCP.py"

if [[ -f "$CONTROLLER_SOURCE" ]]; then
    cp "$CONTROLLER_SOURCE" "$CONTROLLER_DEST"
    echo -e "${GREEN}✓ Copied device_FLStudioMCP.py to FL Studio${NC}"
    echo "  Location: $MCP_CONTROLLER_DIR"
else
    echo -e "${RED}✗ Controller script not found at: $CONTROLLER_SOURCE${NC}"
    exit 1
fi

# Step 3: Install Piano Roll Script
echo ""
echo "Step 3: Installing Piano Roll Script..."
echo "----------------------------------------------"

# Create Piano roll scripts directory if it doesn't exist
if [[ ! -d "$FL_PIANO_SCRIPTS" ]]; then
    echo "Creating Piano roll scripts directory..."
    mkdir -p "$FL_PIANO_SCRIPTS"
fi

# Copy the Piano Roll script
PIANO_SOURCE="$SCRIPT_DIR/ComposeWithLLM.pyscript"
PIANO_DEST="$FL_PIANO_SCRIPTS/ComposeWithLLM.pyscript"

if [[ -f "$PIANO_SOURCE" ]]; then
    cp "$PIANO_SOURCE" "$PIANO_DEST"
    echo -e "${GREEN}✓ Copied ComposeWithLLM.pyscript to FL Studio${NC}"
    echo "  Location: $FL_PIANO_SCRIPTS"
else
    echo -e "${YELLOW}⚠ Piano Roll script not found at: $PIANO_SOURCE${NC}"
    echo "  Piano Roll tools will not be available."
fi

# Step 4: Install Python dependencies
echo ""
echo "Step 4: Installing Python dependencies..."
echo "----------------------------------------------"

cd "$PROJECT_DIR"

# Check if uv is available, otherwise use pip
if command -v uv &> /dev/null; then
    echo "Using uv to install dependencies..."
    uv sync
    echo -e "${GREEN}✓ Dependencies installed with uv${NC}"
elif command -v pip &> /dev/null; then
    echo "Using pip to install dependencies..."
    pip install -e .
    echo -e "${GREEN}✓ Dependencies installed with pip${NC}"
else
    echo -e "${YELLOW}⚠ Neither uv nor pip found. Please install dependencies manually:${NC}"
    echo "  pip install -e ."
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. ${YELLOW}Restart FL Studio${NC} (if it's running)"
echo ""
echo "2. Enable the MIDI controller in FL Studio:"
echo "   - Go to Options > MIDI Settings"
if [[ "$OS" == "mac" ]]; then
    echo "   - Under 'Input', find 'IAC Driver Bus 1'"
else
    echo "   - Under 'Input', find your loopMIDI port"
fi
echo "   - Set the controller type to: ${GREEN}FLStudioMCP${NC}"
echo "   - Enable the port (click to highlight)"
echo ""
echo "3. For Piano Roll features, first run in FL Studio:"
echo "   ${GREEN}Tools > Scripting > ComposeWithLLM${NC}"
echo ""
echo "4. Start the MCP server:"
echo "   ${GREEN}uv run fl-studio-mcp${NC}"
echo ""
echo "For troubleshooting, check:"
echo "  - FL Studio's View > Script output (for controller logs)"
echo "  - MCP server terminal output"
echo ""

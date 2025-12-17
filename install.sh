#!/bin/bash
# FL Studio MCP Server - One-command Installation
#
# This script installs everything needed to control FL Studio from AI assistants.
# It sets up:
#   1. uv package manager (if not installed)
#   2. Python dependencies
#   3. Virtual MIDI ports (IAC Driver on Mac)
#   4. FLStudioMCP controller script
#   5. ComposeWithLLM piano roll script
#   6. Claude Desktop/Code MCP configuration

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  FL Studio MCP Server - Installation       ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"
echo ""

# Step 1: Install uv if not present
echo -e "${YELLOW}[1/5]${NC} Checking for uv package manager..."
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add uv to PATH for this session
    export PATH="$HOME/.local/bin:$PATH"

    if ! command -v uv &> /dev/null; then
        echo -e "${RED}Error: uv installation failed${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}✓${NC} uv is installed"

# Step 2: Install Python dependencies
echo ""
echo -e "${YELLOW}[2/5]${NC} Installing Python dependencies..."
uv sync
echo -e "${GREEN}✓${NC} Dependencies installed"

# Step 3: Set up virtual MIDI and FL Studio controller
echo ""
echo -e "${YELLOW}[3/5]${NC} Setting up FL Studio integration..."

if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS - Run the setup script
    bash "$SCRIPT_DIR/scripts/setup.sh"
else
    echo -e "${YELLOW}!${NC} Windows setup - Please follow manual installation steps:"
    echo "  1. Install loopMIDI: https://www.tobias-erichsen.de/software/loopmidi.html"
    echo "  2. Create a virtual MIDI port"
    echo "  3. Copy fl_controller/device_FLStudioMCP.py to FL Studio Hardware folder"
    echo "  4. Copy scripts/ComposeWithLLM.pyscript to FL Studio Piano roll scripts folder"
fi

# Step 4: Install Piano Roll script (if not already done by setup.sh)
echo ""
echo -e "${YELLOW}[4/5]${NC} Verifying Piano Roll script..."
FL_SCRIPTS="$HOME/Documents/Image-Line/FL Studio/Settings/Piano roll scripts"
if [[ -f "$FL_SCRIPTS/ComposeWithLLM.pyscript" ]]; then
    echo -e "${GREEN}✓${NC} Piano Roll script installed"
else
    if [[ -f "$SCRIPT_DIR/scripts/ComposeWithLLM.pyscript" ]]; then
        mkdir -p "$FL_SCRIPTS"
        cp "$SCRIPT_DIR/scripts/ComposeWithLLM.pyscript" "$FL_SCRIPTS/"
        echo -e "${GREEN}✓${NC} Piano Roll script installed"
    else
        echo -e "${YELLOW}!${NC} Piano Roll script not found - some features may be limited"
    fi
fi

# Step 5: Configure Claude
echo ""
echo -e "${YELLOW}[5/5]${NC} Configuring Claude MCP..."
bash "$SCRIPT_DIR/scripts/install_mcp_for_claude.sh"

# Done!
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Installation Complete!                    ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
echo ""
echo -e "Next steps:"
echo -e "  1. ${BLUE}Restart FL Studio${NC} to load the controller"
echo -e "  2. ${BLUE}Go to Options → MIDI Settings${NC} in FL Studio"
echo -e "  3. ${BLUE}Select IAC Driver Bus 1${NC} (or your virtual MIDI port)"
echo -e "  4. ${BLUE}Set Controller type to FLStudioMCP${NC}"
echo -e "  5. ${BLUE}Enable the port${NC} (click to highlight)"
echo -e "  6. ${BLUE}Restart Claude Desktop/Code${NC} to load the MCP server"
echo ""
echo -e "For manual testing, run:"
echo -e "  ${YELLOW}uv run fl-studio-mcp${NC}"
echo ""

# Platform-specific notes
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "${YELLOW}macOS Note:${NC}"
    echo "  For piano roll auto-triggering, grant Accessibility permissions to"
    echo "  Terminal and Claude Code in System Preferences → Privacy & Security"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    echo -e "${YELLOW}Windows Note:${NC}"
    echo "  Install loopMIDI and create a virtual MIDI port."
    echo "  Configure it in FL Studio MIDI Settings."
fi

#!/bin/bash
# Configure Claude Desktop/Code to use the FL Studio MCP server
#
# This script adds the FL Studio MCP server configuration to Claude's
# config file, enabling AI control of FL Studio via MIDI.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo ""
echo -e "${BLUE}FL Studio MCP - Claude Configuration${NC}"
echo "======================================"
echo ""
echo -e "Project directory: ${CYAN}$PROJECT_DIR${NC}"
echo ""

# Check for uv
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}Warning: uv is not installed.${NC}"
    echo "The MCP server requires uv to run. Install it with:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo ""
fi

# Determine Claude config locations based on OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    CLAUDE_DESKTOP_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
    CLAUDE_CODE_CONFIG="$HOME/.claude.json"
    OS_NAME="macOS"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
    # Windows
    CLAUDE_DESKTOP_CONFIG="$APPDATA/Claude/claude_desktop_config.json"
    CLAUDE_CODE_CONFIG="$USERPROFILE/.claude.json"
    OS_NAME="Windows"
else
    # Linux
    CLAUDE_DESKTOP_CONFIG="$HOME/.config/Claude/claude_desktop_config.json"
    CLAUDE_CODE_CONFIG="$HOME/.claude.json"
    OS_NAME="Linux"
fi

# Function to check if a config exists and show its status
check_config_status() {
    local config_file="$1"
    local config_name="$2"

    if [[ -f "$config_file" ]]; then
        if grep -q "fl-studio" "$config_file" 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} $config_name: Already configured"
            return 0
        else
            echo -e "  ${YELLOW}○${NC} $config_name: Not configured"
            return 1
        fi
    else
        echo -e "  ${YELLOW}○${NC} $config_name: Config file not found"
        return 1
    fi
}

# Function to add MCP server to a config file
add_mcp_to_config() {
    local config_file="$1"
    local config_name="$2"

    echo -e "Configuring ${CYAN}$config_name${NC}..."

    # Create config directory if needed
    mkdir -p "$(dirname "$config_file")"

    # If config doesn't exist, create it
    if [[ ! -f "$config_file" ]]; then
        echo '{}' > "$config_file"
        echo "  Created new config file"
    fi

    # Check if file has valid JSON
    if ! python3 -c "import json; json.load(open('$config_file'))" 2>/dev/null; then
        echo -e "  ${YELLOW}Warning: Invalid JSON in config. Creating backup and new config.${NC}"
        cp "$config_file" "${config_file}.backup"
        echo '{}' > "$config_file"
    fi

    # Add FL Studio MCP server using Python for reliable JSON manipulation
    python3 << EOF
import json

config_file = "$config_file"
project_dir = "$PROJECT_DIR"

# Read existing config
with open(config_file, 'r') as f:
    config = json.load(f)

# Ensure mcpServers exists
if 'mcpServers' not in config:
    config['mcpServers'] = {}

# Add fl-studio entry
config['mcpServers']['fl-studio'] = {
    "command": "uv",
    "args": ["run", "--directory", project_dir, "fl-studio-mcp"]
}

# Write back with pretty formatting
with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)
EOF

    echo -e "  ${GREEN}✓${NC} Added fl-studio MCP server"
}

# Show current status
echo "Current configuration status:"
check_config_status "$CLAUDE_DESKTOP_CONFIG" "Claude Desktop"
DESKTOP_CONFIGURED=$?
check_config_status "$CLAUDE_CODE_CONFIG" "Claude Code"
CODE_CONFIGURED=$?
echo ""

# Menu
echo "Select which Claude client(s) to configure:"
echo ""
echo "  1) Claude Desktop only"
echo "  2) Claude Code only"
echo "  3) Both Claude Desktop and Code"
echo "  4) Show manual configuration"
echo "  5) Skip / Exit"
echo ""
read -p "Enter choice [1-5]: " choice

case $choice in
    1)
        echo ""
        add_mcp_to_config "$CLAUDE_DESKTOP_CONFIG" "Claude Desktop"
        ;;
    2)
        echo ""
        add_mcp_to_config "$CLAUDE_CODE_CONFIG" "Claude Code"
        ;;
    3)
        echo ""
        add_mcp_to_config "$CLAUDE_DESKTOP_CONFIG" "Claude Desktop"
        echo ""
        add_mcp_to_config "$CLAUDE_CODE_CONFIG" "Claude Code"
        ;;
    4)
        echo ""
        echo -e "${CYAN}Manual Configuration${NC}"
        echo ""
        echo "Add the following to your Claude config file:"
        echo ""
        echo -e "${YELLOW}Config file locations:${NC}"
        echo "  Claude Desktop: $CLAUDE_DESKTOP_CONFIG"
        echo "  Claude Code:    $CLAUDE_CODE_CONFIG"
        echo ""
        echo -e "${YELLOW}Add this JSON to your config:${NC}"
        echo ""
        echo '{'
        echo '  "mcpServers": {'
        echo '    "fl-studio": {'
        echo '      "command": "uv",'
        echo "      \"args\": [\"run\", \"--directory\", \"$PROJECT_DIR\", \"fl-studio-mcp\"]"
        echo '    }'
        echo '  }'
        echo '}'
        echo ""
        exit 0
        ;;
    5)
        echo ""
        echo "Skipping configuration."
        exit 0
        ;;
    *)
        echo ""
        echo -e "${RED}Invalid choice. Exiting.${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}Configuration complete!${NC}"
echo ""
echo "Next steps:"
echo ""
echo -e "  1. ${YELLOW}Restart Claude Desktop/Code${NC} to load the new configuration"
echo ""
echo -e "  2. ${YELLOW}Open FL Studio${NC} and configure the MIDI controller:"
echo "     - Go to Options > MIDI Settings"
echo "     - Select your virtual MIDI port (IAC Driver on Mac)"
echo "     - Set Controller type to: FLStudioMCP"
echo "     - Enable the port (click to highlight)"
echo ""
echo -e "  3. ${YELLOW}Test the connection${NC} by asking Claude to get FL Studio status"
echo ""

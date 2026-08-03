# Configure Claude Desktop/Code to use the FL Studio MCP server (Windows)
#
# Adds the FL Studio MCP server configuration to Claude's config file.

$ErrorActionPreference = "Stop"

function Write-Color {
    param([string]$Message, [ConsoleColor]$Color = "Gray")
    Write-Host $Message -ForegroundColor $Color
}

$ScriptDir = $PSScriptRoot
$ProjectDir = Split-Path -Parent $ScriptDir

Write-Host ""
Write-Color "FL Studio MCP - Claude Configuration" "Cyan"
Write-Host "======================================"
Write-Host ""
Write-Host "Project directory: $ProjectDir"
Write-Host ""

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Color "Warning: uv is not installed or not on PATH." "Yellow"
    Write-Host "The MCP server requires uv to run. Install it with:"
    Write-Host '  powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"'
    Write-Host ""
}

$ClaudeDesktopConfig = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
$ClaudeCodeConfig = Join-Path $env:USERPROFILE ".claude.json"

function Test-ConfigHasFlStudio {
    param([string]$ConfigFile)
    if (-not (Test-Path -LiteralPath $ConfigFile)) { return $false }
    $raw = Get-Content -LiteralPath $ConfigFile -Raw -ErrorAction SilentlyContinue
    if (-not $raw) { return $false }
    return $raw -match "fl-studio"
}

function Add-McpToConfig {
    param(
        [string]$ConfigFile,
        [string]$ConfigName
    )

    Write-Host "Configuring $ConfigName..."

    $dir = [System.IO.Path]::GetDirectoryName($ConfigFile)
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    if (-not (Test-Path -LiteralPath $ConfigFile)) {
        "{}" | Set-Content -LiteralPath $ConfigFile -Encoding utf8
        Write-Host "  Created new config file"
    }

    $patchPy = @"
import json
import sys

config_file = sys.argv[1]
project_dir = sys.argv[2]

with open(config_file, "r", encoding="utf-8") as f:
    try:
        config = json.load(f)
    except json.JSONDecodeError:
        import shutil
        shutil.copy2(config_file, config_file + ".backup")
        config = {}

if "mcpServers" not in config or not isinstance(config["mcpServers"], dict):
    config["mcpServers"] = {}

config["mcpServers"]["fl-studio"] = {
    "command": "uv",
    "args": ["run", "--directory", project_dir, "fl-studio-mcp"],
}

with open(config_file, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)
"@

    $tmp = [System.IO.Path]::GetTempFileName() + ".py"
    try {
        Set-Content -LiteralPath $tmp -Value $patchPy -Encoding utf8
        Push-Location $ProjectDir
        try {
            & uv run python $tmp $ConfigFile $ProjectDir
            if ($LASTEXITCODE -ne 0) { throw "python patch failed with exit $LASTEXITCODE" }
        } finally {
            Pop-Location
        }
    } finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }

    Write-Color "  Added fl-studio MCP server" "Green"
}

Write-Host "Current configuration status:"
if (Test-ConfigHasFlStudio $ClaudeDesktopConfig) {
    Write-Color "  Claude Desktop: Already configured" "Green"
} else {
    Write-Color "  Claude Desktop: Not configured" "Yellow"
}
if (Test-ConfigHasFlStudio $ClaudeCodeConfig) {
    Write-Color "  Claude Code: Already configured" "Green"
} else {
    Write-Color "  Claude Code: Not configured" "Yellow"
}
Write-Host ""

Write-Host "Select which Claude client(s) to configure:"
Write-Host ""
Write-Host "  1) Claude Desktop only"
Write-Host "  2) Claude Code only"
Write-Host "  3) Both Claude Desktop and Code"
Write-Host "  4) Show manual configuration"
Write-Host "  5) Skip / Exit"
Write-Host ""
$choice = Read-Host "Enter choice [1-5]"

switch ($choice) {
    "1" {
        Write-Host ""
        Add-McpToConfig $ClaudeDesktopConfig "Claude Desktop"
    }
    "2" {
        Write-Host ""
        Add-McpToConfig $ClaudeCodeConfig "Claude Code"
    }
    "3" {
        Write-Host ""
        Add-McpToConfig $ClaudeDesktopConfig "Claude Desktop"
        Write-Host ""
        Add-McpToConfig $ClaudeCodeConfig "Claude Code"
    }
    "4" {
        Write-Host ""
        Write-Color "Manual Configuration" "Cyan"
        Write-Host ""
        Write-Host "Config file locations:"
        Write-Host "  Claude Desktop: $ClaudeDesktopConfig"
        Write-Host "  Claude Code:    $ClaudeCodeConfig"
        Write-Host ""
        Write-Host "Add this JSON to your config (merge mcpServers with existing content):"
        Write-Host ""
        Write-Host "{"
        Write-Host '  "mcpServers": {'
        Write-Host '    "fl-studio": {'
        Write-Host '      "command": "uv",'
        Write-Host "      `"args`": [`"run`", `"--directory`", `"$ProjectDir`", `"fl-studio-mcp`"]"
        Write-Host "    }"
        Write-Host "  }"
        Write-Host "}"
        Write-Host ""
        exit 0
    }
    "5" {
        Write-Host ""
        Write-Host "Skipping configuration."
        exit 0
    }
    default {
        Write-Host ""
        Write-Color "Invalid choice. Exiting." "Red"
        exit 1
    }
}

Write-Host ""
Write-Color "Configuration complete!" "Green"
Write-Host ""
Write-Host "Next steps:"
Write-Host ""
Write-Color "  1. Restart Claude Desktop/Code to load the new configuration" "Yellow"
Write-Host ""
Write-Color "  2. Open FL Studio and configure the MIDI controller:" "Yellow"
Write-Host "     - Go to Options > MIDI Settings"
Write-Host "     - Select your virtual MIDI port (loopMIDI on Windows)"
Write-Host "     - Set Controller type to: FLStudioMCP"
Write-Host "     - Enable the port (click to highlight)"
Write-Host ""
Write-Color "  3. Test the connection by asking Claude to get FL Studio status" "Yellow"
Write-Host ""

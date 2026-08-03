# FL Studio MCP Server - One-command Installation (Windows)
#
# Installs everything needed to control FL Studio from AI assistants:
#   1. uv package manager (if not installed)
#   2. Python dependencies (Python 3.12; required for python-rtmidi wheels on Windows)
#   3. Virtual MIDI (loopMIDI) guidance + FL Studio controller & piano roll scripts
#   4. Claude Desktop/Code MCP configuration
#
# Run from PowerShell:  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force  # once
#                       .\install.ps1

$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
Set-Location $ScriptDir

function Write-Color {
    param([string]$Message, [ConsoleColor]$Color = "Gray")
    Write-Host $Message -ForegroundColor $Color
}

Write-Color "============================================" "Blue"
Write-Color "  FL Studio MCP Server - Installation" "Blue"
Write-Color "============================================" "Blue"
Write-Host ""

# Step 1: Install uv if not present
Write-Color "[1/5] Checking for uv package manager..." "Yellow"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression

    $uvBin = Join-Path $env:USERPROFILE ".local\bin"
    if (Test-Path -LiteralPath $uvBin) {
        $env:Path = $uvBin + ";" + $env:Path
    }

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Color "Error: uv installation failed (restart this shell or add uv to PATH)." "Red"
        exit 1
    }
}
Write-Color "[OK] uv is installed" "Green"

# Step 2: Install Python dependencies (3.12 — matches PyPI wheels for python-rtmidi on Windows)
Write-Host ""
Write-Color "[2/5] Installing Python dependencies (Python 3.12)..." "Yellow"
& uv python install 3.12
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& uv sync --python 3.12
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Color "[OK] Dependencies installed" "Green"

# Step 3: FL Studio integration (Windows)
Write-Host ""
Write-Color "[3/5] Setting up FL Studio integration..." "Yellow"

Write-Host ""
Write-Host "Virtual MIDI (loopMIDI):"
Write-Host "  1. Install loopMIDI: https://www.tobias-erichsen.de/software/loopmidi.html"
Write-Host "  2. Create a virtual MIDI port and keep loopMIDI running while using FL Studio"
Write-Host ""
Write-Host "Copying controller and Piano Roll scripts into FL Studio Settings..."
Write-Host ""

$FlSettings = Join-Path $env:USERPROFILE "Documents\Image-Line\FL Studio\Settings"
$HardwareDir = Join-Path $FlSettings "Hardware\FLStudioMCP"
$PianoScriptsDir = Join-Path $FlSettings "Piano roll scripts"

$ControllerSrc = Join-Path $ScriptDir "fl_controller\device_FLStudioMCP.py"
$PianoSrc = Join-Path $ScriptDir "scripts\ComposeWithLLM.pyscript"

if (Test-Path -LiteralPath $ControllerSrc) {
    if (-not (Test-Path -LiteralPath $HardwareDir)) {
        New-Item -ItemType Directory -Path $HardwareDir -Force | Out-Null
    }
    Copy-Item -LiteralPath $ControllerSrc -Destination (Join-Path $HardwareDir "device_FLStudioMCP.py") -Force
    Write-Color "[OK] MIDI controller copied to FL Studio Hardware\FLStudioMCP" "Green"
} else {
    Write-Color "! device_FLStudioMCP.py not found - copy fl_controller\device_FLStudioMCP.py manually" "Yellow"
}

if (Test-Path -LiteralPath $PianoSrc) {
    if (-not (Test-Path -LiteralPath $PianoScriptsDir)) {
        New-Item -ItemType Directory -Path $PianoScriptsDir -Force | Out-Null
    }
    Copy-Item -LiteralPath $PianoSrc -Destination (Join-Path $PianoScriptsDir "ComposeWithLLM.pyscript") -Force
    Write-Color "[OK] Piano Roll script copied" "Green"
} else {
    Write-Color "! ComposeWithLLM.pyscript not found - some features may be limited" "Yellow"
}

# Step 4: Verify Piano Roll script (same check as install.sh)
Write-Host ""
Write-Color "[4/5] Verifying Piano Roll script..." "Yellow"
$PianoDest = Join-Path $PianoScriptsDir "ComposeWithLLM.pyscript"
if (Test-Path -LiteralPath $PianoDest) {
    Write-Color "[OK] Piano Roll script installed" "Green"
} else {
    Write-Color "! Piano Roll script missing at FL Studio path" "Yellow"
}

# Step 5: Configure Claude
Write-Host ""
Write-Color "[5/5] Configuring Claude MCP..." "Yellow"
$claudeInstaller = Join-Path $ScriptDir "scripts\install_mcp_for_claude.ps1"
& $claudeInstaller
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Done
Write-Host ""
Write-Color "============================================" "Green"
Write-Color "  Installation Complete!" "Green"
Write-Color "============================================" "Green"
Write-Host ""
Write-Host "Next steps:"
Write-Color "  1. Restart FL Studio to load the controller" "Blue"
Write-Color "  2. Go to Options -> MIDI Settings in FL Studio" "Blue"
Write-Color "  3. Select your loopMIDI port" "Blue"
Write-Color "  4. Set Controller type to FLStudioMCP" "Blue"
Write-Color "  5. Enable the port (click to highlight)" "Blue"
Write-Color "  6. Restart Claude Desktop/Code to load the MCP server" "Blue"
Write-Host ""
Write-Host "For manual testing, run:"
Write-Color "  uv run fl-studio-mcp" "Yellow"
Write-Host ""
Write-Color "Windows note:" "Yellow"
Write-Host "  Install loopMIDI, create a virtual port, and configure it in FL Studio MIDI Settings."
Write-Host "  For piano roll auto-triggering, FL Studio may need to be in focus; see README."
Write-Host ""

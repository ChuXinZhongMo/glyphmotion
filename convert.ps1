param(
  [Parameter(Mandatory = $true)]
  [string]$InputFile,
  [string]$OutputDir = "output",
  [string]$Formats = "txt,html,gif,png,dur,asciimation",
  [int]$Width = 100,
  [double]$Fps = 12,
  [int]$MaxFrames = 240,
  [switch]$Mono,
  [switch]$Invert
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$ArgsList = @(
  "-m", "ascii_oneclick.cli",
  $InputFile,
  "--output-dir", $OutputDir,
  "--formats", $Formats,
  "--width", $Width,
  "--fps", $Fps,
  "--max-frames", $MaxFrames
)
if ($Mono) { $ArgsList += "--mono" }
if ($Invert) { $ArgsList += "--invert" }
& $Python @ArgsList

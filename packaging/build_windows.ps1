[CmdletBinding()]
param(
    [switch]$SkipExe,
    [switch]$SkipMsi
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$DistDir = Join-Path $ProjectRoot "dist\windows"
$PyInstallerWorkDir = Join-Path $ProjectRoot "build\pyinstaller"
$WixWorkDir = Join-Path $ProjectRoot "build\wix"
$Launcher = Join-Path $PSScriptRoot "glyphmotion_gui.py"
$Wxs = Join-Path $PSScriptRoot "GlyphMotion.wxs"
$Readme = Join-Path $ProjectRoot "README.md"
$LicenseFile = Join-Path $ProjectRoot "LICENSE"
$NoticeFile = Join-Path $ProjectRoot "NOTICE"
$ThirdPartyNotice = Join-Path $ProjectRoot "THIRD_PARTY_NOTICES.md"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Find-Wix {
    $command = Get-Command "wix.exe" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        "C:\Program Files\WiX Toolset v7.0\bin\wix.exe",
        "C:\Program Files\WiX Toolset v6.0\bin\wix.exe",
        "C:\Program Files\WiX Toolset v5.0\bin\wix.exe",
        "C:\Program Files\WiX Toolset v4.0\bin\wix.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    throw "wix.exe was not found. Install it with: winget install --id WiXToolset.WiXCLI --source winget"
}

function Ensure-PyInstaller {
    & $Python -m PyInstaller --version *> $null
    if ($LASTEXITCODE -eq 0) {
        return
    }

    Write-Host "Installing PyInstaller into project venv..."
    $pipArgs = @("-m", "pip", "install", "pyinstaller")
    Invoke-Checked -FilePath $Python -Arguments $pipArgs
}

function Ensure-Wix {
    try {
        $wix = Find-Wix
    }
    catch {
        $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
        if (-not $winget) {
            throw
        }

        Write-Host "Installing WiX Toolset CLI..."
        $wingetArgs = @(
            "install",
            "--id", "WiXToolset.WiXCLI",
            "--source", "winget",
            "--accept-package-agreements",
            "--accept-source-agreements",
            "--disable-interactivity"
        )
        Invoke-Checked -FilePath $winget.Source -Arguments $wingetArgs
        $wix = Find-Wix
    }

    & $wix eula accept wix7 *> $null
    return $wix
}

function Find-Ffmpeg {
    $override = $env:ASCII_ONECLICK_FFMPEG
    if ($override -and (Test-Path -LiteralPath $override)) {
        return (Resolve-Path -LiteralPath $override).Path
    }

    $finder = "from ascii_oneclick.core import find_ffmpeg; print(find_ffmpeg() or '')"
    $found = (& $Python -c $finder).Trim()
    if ($LASTEXITCODE -eq 0 -and $found -and (Test-Path -LiteralPath $found)) {
        return (Resolve-Path -LiteralPath $found).Path
    }

    return $null
}

function Ensure-Ffmpeg {
    $ffmpeg = Find-Ffmpeg
    if (-not $ffmpeg) {
        $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
        if (-not $winget) {
            throw "ffmpeg.exe was not found and winget.exe is unavailable. Install FFmpeg with: winget install --id Gyan.FFmpeg --source winget"
        }

        Write-Host "Installing FFmpeg..."
        $wingetArgs = @(
            "install",
            "--id", "Gyan.FFmpeg",
            "--source", "winget",
            "--accept-package-agreements",
            "--accept-source-agreements",
            "--disable-interactivity"
        )
        Invoke-Checked -FilePath $winget.Source -Arguments $wingetArgs
        $ffmpeg = Find-Ffmpeg
    }

    if (-not $ffmpeg) {
        throw "ffmpeg.exe was not found after installation."
    }

    & $ffmpeg -version *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "ffmpeg.exe exists but could not run: $ffmpeg"
    }

    return $ffmpeg
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python venv was not found: $Python"
}

Ensure-PyInstaller
New-Item -ItemType Directory -Force -Path $DistDir, $PyInstallerWorkDir, $WixWorkDir | Out-Null

$Version = (& $Python -c "import ascii_oneclick; print(ascii_oneclick.__version__)").Trim()
if (-not $Version) {
    throw "Could not read package version."
}

$AppExe = Join-Path $DistDir "GlyphMotion.exe"

if (-not $SkipExe) {
    $Ffmpeg = Ensure-Ffmpeg
    Write-Host "Bundling FFmpeg: $Ffmpeg"

    $pyInstallerArgs = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", "GlyphMotion",
        "--distpath", $DistDir,
        "--workpath", $PyInstallerWorkDir,
        "--specpath", $PyInstallerWorkDir,
        "--hidden-import", "PIL._tkinter_finder",
        "--add-binary", "$Ffmpeg;.",
        $Launcher
    )
    Invoke-Checked -FilePath $Python -Arguments $pyInstallerArgs
}

if (-not (Test-Path -LiteralPath $AppExe)) {
    throw "Expected app executable was not created: $AppExe"
}

if (-not $SkipMsi) {
    $Wix = Ensure-Wix
    $MsiPath = Join-Path $DistDir "GlyphMotion-$Version-win64.msi"

    $wixArgs = @(
        "build", $Wxs,
        "-arch", "x64",
        "-intermediatefolder", $WixWorkDir,
        "-d", "ProductVersion=$Version",
        "-d", "AppExe=$AppExe",
        "-d", "ReadmeFile=$Readme",
        "-d", "LicenseFile=$LicenseFile",
        "-d", "NoticeFile=$NoticeFile",
        "-d", "ThirdPartyNoticeFile=$ThirdPartyNotice",
        "-out", $MsiPath
    )
    Invoke-Checked -FilePath $Wix -Arguments $wixArgs

    Write-Host "Built MSI: $MsiPath"
}

Write-Host "Built EXE: $AppExe"

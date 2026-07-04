param(
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$distPath = Join-Path $Root $OutputDir
$stagePath = Join-Path $distPath "kamery-lukow-package"
$zipPath = Join-Path $distPath "kamery-lukow-$stamp.zip"

if (Test-Path -LiteralPath $stagePath) {
    Remove-Item -LiteralPath $stagePath -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stagePath | Out-Null

$rootFiles = @(
    ".env.example",
    ".gitignore",
    "AGENTS.md",
    "cameras.example.yml",
    "docker-compose.yml",
    "go2rtc.example.yaml",
    "INSTALL_FFMPEG_LUKOW.bat",
    "INSTALL_LUKOW.bat",
    "LUKOW_README.md",
    "pyproject.toml",
    "README.md",
    "secrets.local.example.env",
    "START_PANEL_LUKOW.bat",
    "TEST_DIRECT_LUKOW.bat",
    "TEST_STREAMY_LUKOW.bat",
    "UPDATE_LUKOW.bat"
)

foreach ($file in $rootFiles) {
    $source = Join-Path $Root $file
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $stagePath $file) -Force
    }
}

foreach ($directory in @("apps", "docs", "scripts", "src", "tests")) {
    Copy-Item -LiteralPath (Join-Path $Root $directory) -Destination (Join-Path $stagePath $directory) -Recurse -Force
}

$removePatterns = @(
    "apps\web\node_modules",
    "apps\web\dist",
    "apps\web\.vite",
    ".pytest_cache",
    "__pycache__"
)
foreach ($relativePath in $removePatterns) {
    Get-ChildItem -LiteralPath $stagePath -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName.EndsWith($relativePath, [StringComparison]::OrdinalIgnoreCase) -or $_.Name -eq $relativePath } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
Get-ChildItem -LiteralPath $stagePath -Recurse -Force -File |
    Where-Object { $_.Extension -in @(".pyc", ".pyo", ".log") -or $_.Name.EndsWith(".tsbuildinfo", [StringComparison]::OrdinalIgnoreCase) } |
    ForEach-Object { [System.IO.File]::Delete($_.FullName) }

$forbidden = @(
    ".git",
    ".venv",
    ".env",
    "secrets.local.env",
    "cameras.local.yml",
    "cameras.local.yaml",
    "runtime",
    "probe-results",
    "snapshots"
)
$leaks = @()
foreach ($item in Get-ChildItem -LiteralPath $stagePath -Recurse -Force) {
    if ($forbidden -contains $item.Name) {
        $leaks += $item.FullName
    }
}
if ($leaks.Count) {
    $leaks | ForEach-Object { Write-Error "Forbidden file in package: $_" }
    throw "Package contains forbidden local/runtime files."
}

if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($stagePath, $zipPath)

Write-Host "Package created:"
Write-Host $zipPath

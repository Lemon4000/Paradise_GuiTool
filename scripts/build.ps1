param(
  [string]$Name = "UsartGUI",
  [switch]$OneFile = $false
)

$mode = "-D"
if ($OneFile) { $mode = "-F" }

if (Test-Path "$Name.spec") { Remove-Item "$Name.spec" -Force -ErrorAction SilentlyContinue }

python -m PyInstaller $mode --noconsole --icon "ICON.png" -n $Name gui/main.py --add-data "config;config" --hidden-import serial.tools.list_ports_windows --hidden-import serial.tools.list_ports --clean

if ($OneFile) {
  $distDir = "dist"
  # Rebuild with local runtime tmp dir to avoid embedded interpreter startup issues
  python -m PyInstaller -F --noconsole --icon "ICON.png" -n $Name gui/main.py --add-data "config;config" --hidden-import serial.tools.list_ports_windows --hidden-import serial.tools.list_ports --runtime-tmpdir . --clean
  if (Test-Path "config") { Copy-Item -Recurse -Force "config" (Join-Path $distDir "config") }
} else {
  $distDir = Join-Path "dist" $Name
  if (Test-Path "config") {
    New-Item -ItemType Directory -Force -Path $distDir | Out-Null
    Copy-Item -Recurse -Force "config" $distDir
  }
}
Write-Host "Build complete. Output: $distDir"

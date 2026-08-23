# Build the release binaries and refresh the deployed copies at the repo root.
# The Start Menu shortcut and the align-terminals Skill point at those copies,
# not at target\release, so a plain `cargo build` alone changes nothing they run.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
cargo build --release
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Copy-Item target\release\align-terminals.exe  .\align-terminals.exe  -Force
Copy-Item target\release\align-terminalsw.exe .\align-terminalsw.exe -Force
Write-Output "deployed align-terminals.exe and align-terminalsw.exe"

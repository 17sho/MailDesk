param(
    [string]$OutputPath = "artifacts\MailDesk-v0.3.9-onedir-update-launcher.exe"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Source = Join-Path $PSScriptRoot "Program.cs"
$Output = Join-Path $Root $OutputPath
$Compiler = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"

if (-not (Test-Path -LiteralPath $Compiler -PathType Leaf)) {
    throw "Windows .NET Framework C# compiler not found: $Compiler"
}

New-Item -ItemType Directory -Path (Split-Path -Parent $Output) -Force | Out-Null
& $Compiler `
    /nologo `
    /target:winexe `
    /platform:x64 `
    /optimize+ `
    /codepage:65001 `
    /reference:System.dll `
    /reference:System.Core.dll `
    /reference:System.Windows.Forms.dll `
    /out:$Output `
    $Source

if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Output -PathType Leaf)) {
    throw "Update recovery launcher compilation failed"
}

Get-Item -LiteralPath $Output | Select-Object FullName, Length, LastWriteTime

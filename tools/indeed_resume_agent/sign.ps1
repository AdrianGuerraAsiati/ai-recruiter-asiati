param(
    [Parameter(Mandatory = $true)]
    [string]$Executable,

    [Parameter(Mandatory = $true)]
    [string]$PfxPath,

    [Parameter(Mandatory = $true)]
    [string]$PfxPassword,

    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"

$Executable = (Resolve-Path $Executable).Path
$PfxPath = (Resolve-Path $PfxPath).Path

$WindowsKits = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
if (-not (Test-Path $WindowsKits)) {
    throw "Windows SDK no encontrado. No es posible firmar el ejecutable."
}

$SignTool = Get-ChildItem $WindowsKits -Filter "signtool.exe" -Recurse -File |
    Where-Object { $_.FullName -match "\\x64\\signtool\.exe$" } |
    Sort-Object FullName -Descending |
    Select-Object -First 1

if (-not $SignTool) {
    throw "signtool.exe x64 no encontrado en Windows SDK."
}

Write-Host "Firmando $Executable"
& $SignTool.FullName sign `
    /fd SHA256 `
    /f $PfxPath `
    /p $PfxPassword `
    /tr $TimestampUrl `
    /td SHA256 `
    $Executable

if ($LASTEXITCODE -ne 0) {
    throw "signtool sign fallo con exit code $LASTEXITCODE"
}

Write-Host "Verificando firma Authenticode..."
& $SignTool.FullName verify `
    /pa `
    /all `
    /v `
    $Executable

if ($LASTEXITCODE -ne 0) {
    throw "signtool verify fallo con exit code $LASTEXITCODE"
}

$Signature = Get-AuthenticodeSignature -FilePath $Executable
if ($Signature.Status -ne "Valid") {
    throw "La firma Authenticode no es valida. Estado: $($Signature.Status)"
}

if (-not $Signature.SignerCertificate) {
    throw "No se encontro certificado firmante en el ejecutable."
}

Write-Host "Firma valida."
Write-Host "Subject: $($Signature.SignerCertificate.Subject)"
Write-Host "Thumbprint: $($Signature.SignerCertificate.Thumbprint)"
Write-Host "Timestamp: $TimestampUrl"

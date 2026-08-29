<#
.SYNOPSIS
    Generic image downloader for JSON API responses (any shape, any endpoint).

.DESCRIPTION
    Recursively walks the ENTIRE JSON structure looking for string values that
    look like image paths (.png/.jpg/.jpeg/.webp/.svg/.bmp) - regardless of
    field name, nesting depth, or whether it's inside an array or object.
    .gif and .json are intentionally excluded. Downloads each one from
    <BaseUrl><relative-path>, preserving the folder structure under -OutDir so
    files never collide.

    Run with no arguments and it will interactively ask for the API URL,
    base/CDN URL, and auth token (press Enter to accept the shown default,
    the token has no default and is entered hidden). Or pass everything as
    flags for non-interactive / scripted use.

.EXAMPLE
    .\Download-Images.ps1
    (prompts for ApiUrl / BaseUrl / AuthToken)

.EXAMPLE
    .\Download-Images.ps1 -ApiUrl "https://api.dreamlived.com/admin/giftlisting/getGiftListing/undefined/undefined" -BaseUrl "https://dreamapp.b-cdn.net/" -AuthToken "eyJ..." -DryRun
#>

param(
    [string]$ApiUrl,
    [string]$BaseUrl,
    [string]$AuthToken,
    [string]$InputFile,
    [string]$OutDir = "img",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Shown as defaults in the prompts below - press Enter to accept, or type your own.
$DefaultApiUrl = "https://api.dreamlived.com/admin/giftlisting/getGiftListing/undefined/undefined"
$DefaultBaseUrl = "https://dreamapp.b-cdn.net/"

if (-not $InputFile) {
    if (-not $ApiUrl) {
        $typed = Read-Host "API URL [$DefaultApiUrl]"
        $ApiUrl = if ($typed) { $typed } else { $DefaultApiUrl }
    }
    if (-not $BaseUrl) {
        $typed = Read-Host "Base/CDN URL [$DefaultBaseUrl]"
        $BaseUrl = if ($typed) { $typed } else { $DefaultBaseUrl }
    }
    if (-not $AuthToken) {
        $secure = Read-Host "Auth token (Bearer, input hidden)" -AsSecureString
        $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        $AuthToken = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

if (-not $BaseUrl.EndsWith("/")) {
    $BaseUrl += "/"
}

$imageExtPattern = '\.(png|jpe?g|webp|svg|bmp)$'

function Find-ImagePaths {
    param($Obj, [System.Collections.Generic.HashSet[string]]$Found)

    if ($null -eq $Obj) { return }

    if ($Obj -is [System.Collections.IDictionary]) {
        foreach ($v in $Obj.Values) { Find-ImagePaths -Obj $v -Found $Found }
    }
    elseif ($Obj -is [System.Management.Automation.PSCustomObject]) {
        foreach ($p in $Obj.PSObject.Properties) { Find-ImagePaths -Obj $p.Value -Found $Found }
    }
    elseif ($Obj -is [System.Collections.IEnumerable] -and -not ($Obj -is [string])) {
        foreach ($item in $Obj) { Find-ImagePaths -Obj $item -Found $Found }
    }
    elseif ($Obj -is [string]) {
        if ($Obj -match $imageExtPattern) {
            [void]$Found.Add($Obj)
        }
    }
}

if ($InputFile) {
    $data = Get-Content -Raw -Path $InputFile | ConvertFrom-Json
}
else {
    $headers = @{}
    if ($AuthToken) { $headers["Authorization"] = "Bearer $AuthToken" }
    Write-Host "Fetching JSON from $ApiUrl ..."
    $resp = Invoke-WebRequest -Uri $ApiUrl -Headers $headers -UseBasicParsing -TimeoutSec 30
    $data = $resp.Content | ConvertFrom-Json
}

$found = [System.Collections.Generic.HashSet[string]]::new()
Find-ImagePaths -Obj $data -Found $found
$imagePaths = $found | Sort-Object

Write-Host "Found $($imagePaths.Count) image reference(s)."

if ($DryRun) {
    $imagePaths | ForEach-Object { Write-Host " - $_" }
    return
}

if ($imagePaths.Count -eq 0) {
    Write-Host "Nothing to download."
    return
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$ok = 0; $skipped = 0; $failed = 0

foreach ($relPath in $imagePaths) {
    $fullUrl = "$BaseUrl$($relPath.TrimStart('/'))"
    $destPath = Join-Path $OutDir ($relPath -replace '/', '\')
    $destDir = Split-Path $destPath -Parent
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null

    if (Test-Path $destPath) {
        Write-Host "[skipped] $relPath"
        $skipped++
        continue
    }

    try {
        Invoke-WebRequest -Uri $fullUrl -OutFile $destPath -UseBasicParsing -TimeoutSec 30
        Write-Host "[ok] $relPath"
        $ok++
    }
    catch {
        Write-Host "[FAILED] $relPath - $_"
        $failed++
    }
}

Write-Host ""
Write-Host "Done. Downloaded: $ok, skipped: $skipped, failed: $failed"
Write-Host "Images saved under: $(Resolve-Path $OutDir)"

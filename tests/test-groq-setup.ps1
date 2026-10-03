$ErrorActionPreference = 'Stop'
$source = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\scripts\configure-groq.ps1') -Raw
$tokens = $null
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseInput($source, [ref]$tokens, [ref]$parseErrors) | Out-Null
if ($parseErrors.Count) { throw 'Setup script has PowerShell syntax errors.' }
# Execute the actual script with mocked input and in-memory environment writes.
# No real API key or persistent Windows setting is used by these tests.
$source = $source.Replace("[Environment]::SetEnvironmentVariable('GROQ_API_KEY', `$key.Trim(), 'User')", "`$script:savedKey = `$key.Trim()")
$source = $source.Replace("[Environment]::SetEnvironmentVariable('GROQ_FREE_TIER_CONFIRMED', 'true', 'User')", "`$script:savedPlan = 'true'")
function Read-Host {
    param([string]$Prompt, [switch]$AsSecureString)
    if ($AsSecureString) { return (ConvertTo-SecureString 'test-only-not-a-real-key' -AsPlainText -Force) }
    return $script:confirmationInput
}
foreach ($inputValue in @('YES', 'yes', 'Yes', ' YES ')) {
    $script:confirmationInput = $inputValue
    $script:savedKey = $null
    $script:savedPlan = $null
    & ([scriptblock]::Create($source))
    if ($script:savedKey -ne 'test-only-not-a-real-key' -or $script:savedPlan -ne 'true') {
        throw 'Confirmation or secure-input flow failed.'
    }
}
Write-Host 'PASS: uppercase, lowercase, mixed case, whitespace, and hidden-key setup flow (mock settings).'

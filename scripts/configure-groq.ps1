$ErrorActionPreference = 'Stop'
$pointer = [IntPtr]::Zero
$key = $null
$stage = 'confirmation'
try {
    Write-Host 'Use a Groq Free Plan account only. Task data will be sent to Groq when users ask questions.'
    $confirmation = Read-Host 'Have you verified that this key belongs to a Free Plan account? Type YES'
    if ($confirmation.Trim() -ine 'YES') {
        Write-Host 'Setup cancelled. Run again and type YES without quotation marks to continue.'
        exit 1
    }
    $stage = 'key input'
    Write-Host 'Paste the API key at the next prompt, then press Enter. The key will be hidden.'
    $secureKey = Read-Host 'Groq API key' -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($key)) {
        Write-Host 'No API key was entered. No settings changed. Run setup again and paste the key before pressing Enter.' -ForegroundColor Yellow
        exit 1
    }
    $stage = 'saving settings'
    # User-scoped environment: never put the secret in the repository or browser.
    [Environment]::SetEnvironmentVariable('GROQ_API_KEY', $key.Trim(), 'User')
    [Environment]::SetEnvironmentVariable('GROQ_FREE_TIER_CONFIRMED', 'true', 'User')
    Write-Host 'Configured for this Windows user. Run start-app.cmd -Restart to activate.' -ForegroundColor Green
} catch {
    # Do not print exception details: configuration errors can include secrets.
    Write-Host "Setup failed during ${stage}." -ForegroundColor Red
    if ($stage -eq 'saving settings') {
        Write-Host 'Windows could not save the user settings. Run setup from a normal Windows PowerShell terminal under the account that starts the app.'
    } else {
        Write-Host 'Use an interactive Windows PowerShell terminal, not a task runner or redirected command. Enter YES, then paste the API key at the hidden prompt.'
    }
    Write-Host 'If this continues, share this stage and error type only (never your API key):'
    Write-Host $_.Exception.GetType().FullName
    exit 1
} finally {
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    if ($secureKey) { $secureKey.Dispose() }
    $key = $null
}

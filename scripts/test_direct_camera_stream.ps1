param(
    [int]$DurationSeconds = 120,
    [switch]$Quick,
    [switch]$VideoOnly
)

$Script = Join-Path $PSScriptRoot "root_cause_stream_lab.ps1"
$parameters = @{
    OnlyDirect = $true
    AllowDirectCameraRtsp = $true
}
if ($PSBoundParameters.ContainsKey("DurationSeconds")) {
    $parameters.DurationSeconds = $DurationSeconds
}
if ($Quick) {
    $parameters.Quick = $true
}
if ($VideoOnly) {
    $parameters.VideoOnly = $true
}
& $Script @parameters

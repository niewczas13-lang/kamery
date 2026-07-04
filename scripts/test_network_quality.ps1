param(
    [int]$PingCount = 200
)

$Script = Join-Path $PSScriptRoot "root_cause_stream_lab.ps1"
& $Script -OnlyNetwork -PingCount $PingCount

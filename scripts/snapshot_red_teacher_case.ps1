param([Parameter(Mandatory=$true)][string]$Specification,[Parameter(Mandatory=$true)][string]$SpecificationSha256)
$ErrorActionPreference='Stop'
if((Get-FileHash -LiteralPath $Specification -Algorithm SHA256).Hash.ToLowerInvariant() -ne $SpecificationSha256){throw 'Launch specification differs'}
$spec=Get-Content -LiteralPath $Specification -Raw|ConvertFrom-Json
$launch=Get-Content -LiteralPath (Join-Path $spec.windows_receipt_directory_windows ($spec.identity+'.windows-launch.json')) -Raw|ConvertFrom-Json
if($launch.specification_sha256 -ne $SpecificationSha256 -or $launch.resource_plan_sha256 -ne $spec.resource_plan_sha256){throw 'Original Windows launch differs'}
$original=$launch.actual_process
if(-not $original -or $original.ProcessId -ne $launch.launch_process_id){throw 'Original process identity unavailable'}
$actual=Get-CimInstance Win32_Process -Filter ('ProcessId = '+$original.ProcessId)|Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine
$same=$actual -and $actual.ProcessId -eq $original.ProcessId -and ([datetime]$actual.CreationDate) -eq ([datetime]$original.CreationDate) -and $actual.CommandLine -eq $original.CommandLine
[ordered]@{observed_at_utc=[datetime]::UtcNow.ToString('o');original_process=$original;actual_process=$actual;original_live=[bool]$same;original_absent=(-not [bool]$same);specification_sha256=$SpecificationSha256}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $spec.windows_receipt_directory_windows ($spec.identity+'.windows-current.json'))

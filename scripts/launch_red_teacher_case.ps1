param(
    [Parameter(Mandatory=$true)][string]$Specification,
    [Parameter(Mandatory=$true)][string]$SpecificationSha256,
    [Parameter(Mandatory=$true)][string]$ReceiptDirectory
)
$ErrorActionPreference='Stop'
if((Get-FileHash -LiteralPath $Specification -Algorithm SHA256).Hash.ToLowerInvariant() -ne $SpecificationSha256){throw 'Launch specification differs'}
$spec=Get-Content -LiteralPath $Specification -Raw|ConvertFrom-Json
if([System.IO.Path]::GetFullPath($ReceiptDirectory) -ne [System.IO.Path]::GetFullPath($spec.windows_receipt_directory_windows)){throw 'Declared Windows receipt directory differs'}
function Convert-LinuxPath([string]$p){
    if(-not $p.StartsWith('/')){throw 'Absolute declared Linux path required'}
    '\\wsl.localhost\'+$spec.distribution+$p.Replace('/','\')
}
foreach($key in @('worker','plan','package','supervisor','resource_plan','guard')){
    if((Get-FileHash -LiteralPath (Convert-LinuxPath $spec.$key) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $spec.($key+'_sha256')){throw ('Pin differs: '+$key)}
}
$resource=Get-Content -LiteralPath (Convert-LinuxPath $spec.resource_plan) -Raw|ConvertFrom-Json
if(($resource.command|ConvertTo-Json -Compress) -ne ($spec.worker_command|ConvertTo-Json -Compress)){throw 'Exact worker command differs'}
$receipt=Join-Path $ReceiptDirectory ($spec.identity+'.windows-launch.json')
if(Test-Path -LiteralPath $receipt){throw 'Consumed launch identity'}
$available=(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB
if($available -lt $spec.windows_minimum_free_GiB){throw 'Declared host memory reserve insufficient'}
# Guard is resolved only from the authenticated specification. No case-specific path.
$guardArgs=@('-d',$spec.distribution,'-u',$spec.linux_user,'--',$spec.python,'-I','-B',$spec.guard)+@($spec.guard_arguments)+@('--spec-sha256',$SpecificationSha256)
& $spec.wsl_executable @guardArgs
if($LASTEXITCODE -ne 0){throw 'Exclusive lifecycle guard failed; no dispatch'}
$taskArgs=@('-d',$spec.distribution,'-u','root','--cd',$spec.project_root,'--',$spec.python,'-I','-B',$spec.supervisor,'--plan',$spec.resource_plan,'--plan-sha256',$spec.resource_plan_sha256,'--expected-script',$spec.worker)
$proc=Start-Process -FilePath $spec.wsl_executable -ArgumentList $taskArgs -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $ReceiptDirectory ($spec.identity+'.stdout.log')) -RedirectStandardError (Join-Path $ReceiptDirectory ($spec.identity+'.stderr.log'))
$actual=Get-CimInstance Win32_Process -Filter ('ProcessId = '+$proc.Id)|Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine
[ordered]@{observed_at_utc=[datetime]::UtcNow.ToString('o');actual_process=$actual;launch_process_id=$proc.Id;expected_arguments=$taskArgs;resource_plan_sha256=$spec.resource_plan_sha256;specification_sha256=$SpecificationSha256;guard_path=$spec.guard;guard_sha256=$spec.guard_sha256;preflight_only=($spec.phase -eq 'preflight');diagnostic_only=$true;actual_actor=$false;host_available_GiB=$available}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $receipt
$actual|Select-Object ProcessId,CreationDate

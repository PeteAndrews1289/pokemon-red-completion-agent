param([Parameter(Mandatory=$true)][string]$Launcher,[Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
$global:teacherDigest='0'*64
$global:teacherSpec=@{
    identity='synthetic-direct';phase='direct';distribution='SyntheticDistro';linux_user='pokemon';project_root='/synthetic/project';python='/synthetic/python';
    worker='/synthetic/cap/shared/worker.py';plan='/synthetic/cap/case/PLAN.json';package='/synthetic/frozen/PLAYER-PACKAGE.json';
    supervisor='/synthetic/cap/supervisor.py';resource_plan='/synthetic/cap/case/RESOURCE.json';guard='/synthetic/cap/shared/pinned-new-guard.py';
    guard_arguments=@('--spec','/synthetic/cap/case/LAUNCH-SPECIFICATION.json');wsl_executable='Invoke-TeacherGuardMock';
    worker_command=@('/synthetic/python','-I','-B','/synthetic/cap/shared/worker.py','--case','/synthetic/cap/case','--plan-sha256',('0'*64),'--phase','direct');
    windows_minimum_free_GiB=6;windows_receipt_directory_windows=$PSScriptRoot
}
foreach($key in @('worker','plan','package','supervisor','resource_plan','guard')){$global:teacherSpec[$key+'_sha256']=$global:teacherDigest}
function Get-FileHash {param($LiteralPath,$Algorithm) [pscustomobject]@{Hash=$(if($global:teacherBadPin -and $LiteralPath -like '*pinned-new-guard.py'){'1'*64}else{$global:teacherDigest})}}
function Get-Content {param($LiteralPath,[switch]$Raw) if($LiteralPath -eq 'synthetic-spec'){$global:teacherSpec|ConvertTo-Json -Depth 7}else{@{command=$global:teacherSpec.worker_command}|ConvertTo-Json -Depth 7}}
function Test-Path {param($LiteralPath) $false}
function Get-CimInstance {param($ClassName,$Filter) if($ClassName -eq 'Win32_OperatingSystem'){[pscustomobject]@{FreePhysicalMemory=(8*1MB)}}else{[pscustomobject]@{ProcessId=314;ParentProcessId=1;CreationDate='synthetic';CommandLine='synthetic'}}}
function Invoke-TeacherGuardMock {$global:teacherGuardArgs=@($args);$global:LASTEXITCODE=$global:teacherGuardExit}
function Start-Process {param($FilePath,$ArgumentList,$WindowStyle,[switch]$PassThru,$RedirectStandardOutput,$RedirectStandardError) $global:teacherStarts+=1;$global:teacherStartArgs=@($ArgumentList);[pscustomobject]@{Id=314}}
function Set-Content {param($LiteralPath,[Parameter(ValueFromPipeline=$true)]$Value) process {$global:teacherReceipt=$Value}}
$checks=@()
foreach($case in @('pass','guard-rejection','guard-pin-mismatch')){
    $global:teacherStarts=0;$global:teacherGuardArgs=$null;$global:teacherReceipt=$null
    $global:teacherGuardExit=if($case -eq 'guard-rejection'){7}else{0}
    $global:teacherBadPin=$case -eq 'guard-pin-mismatch';$caught=$null
    try {& $Launcher -Specification synthetic-spec -SpecificationSha256 $global:teacherDigest -ReceiptDirectory $PSScriptRoot|Out-Null}catch{$caught=$_.Exception.Message}
    if($case -eq 'pass'){
        if($caught -or $global:teacherStarts -ne 1){throw ('Valid shared launcher failed: '+$caught+'; mock starts='+$global:teacherStarts+'; guard='+($global:teacherGuardArgs -join ' '))}
        if($global:teacherGuardArgs[8] -ne $global:teacherSpec.guard){throw 'Launcher used wrong or stale guard path'}
        if($global:teacherGuardArgs[-2] -ne '--spec-sha256' -or $global:teacherGuardArgs[-1] -ne $global:teacherDigest){throw 'Launcher did not pass authenticated spec digest'}
        $receipt=$global:teacherReceipt|ConvertFrom-Json
        if($receipt.guard_path -ne $global:teacherSpec.guard -or $receipt.guard_sha256 -ne $global:teacherDigest){throw 'Guard identity not retained'}
    }else{
        if(-not $caught -or $global:teacherStarts -ne 0){throw 'Failed guard/pin allowed dispatch'}
        if($case -eq 'guard-pin-mismatch' -and $global:teacherGuardArgs){throw 'Guard executed before its pin was verified'}
    }
    $checks+=@{name=$case;passed=$true;processes_started=0;mock_dispatches=$global:teacherStarts;failure=$caught}
}
$result=@{passed=$true;checks=$checks;real_processes_started=0;native_loads=0;new_fits=0;observed_at_utc=[datetime]::UtcNow.ToString('o')}|ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText($Output,$result+[Environment]::NewLine)
Write-Output $result

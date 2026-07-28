# Security Policy

## Supported version

Security, integrity, and reproducibility fixes are supported on `main`.

## Reporting

Use GitHub private vulnerability reporting for issues involving artifact validation, ROM identity,
checkpoint handling, command execution, or evaluator integrity.

Never attach a ROM, save, emulator snapshot, model checkpoint, credential, private filesystem path,
or unredacted gameplay trace. Reproduce the problem with the smallest synthetic fixture possible.

## Trust boundary

The emulator and training tools process user-supplied local files. Only use a lawfully obtained ROM
whose fingerprint matches the supported revision, and do not load untrusted model checkpoints or
serialized run artifacts.

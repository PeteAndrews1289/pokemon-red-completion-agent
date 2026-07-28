## What changed

<!-- Describe the implementation and its completion or reliability impact. -->

## Claim boundary

<!-- State what this proves and what it does not prove. -->

## Verification

- [ ] `python scripts/check_public_artifacts.py`
- [ ] `python scripts/check_docs.py`
- [ ] `ruff check .`
- [ ] `pytest -m "not integration"`

## Safety and provenance

- [ ] No ROM, save, snapshot, recording, dataset, checkpoint, credential, or private path is added.
- [ ] New raw-memory fields are tied to the supported ROM revision and attributed symbols.
- [ ] Actor and referee authority remain separate.
- [ ] Any training or runtime assistance is disclosed.

## What changed

<!-- Describe the implementation and its completion or reliability impact. -->

## Claim boundary

<!-- State what this proves and what it does not prove. -->

## Verification

- [ ] `python scripts/check_public_artifacts.py`
- [ ] `python scripts/check_docs.py`
- [ ] `python scripts/regenerate_collection_registry.py --check`
- [ ] `python scripts/regenerate_strategic_navigation_registry.py --check`
- [ ] `ruff check .`
- [ ] `python -m mypy`
- [ ] `pytest -m "not integration"`

## Safety and provenance

- [ ] No ROM, save, snapshot, recording, dataset, checkpoint, credential, or private path is added.
- [ ] New raw-memory fields are tied to the supported ROM revision and attributed symbols.
- [ ] Actor and referee authority remain separate.
- [ ] Any training or runtime assistance is disclosed.

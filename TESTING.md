# Testing

## Test Framework
- `pytest`
- test files under `tests/`

## Running Tests
### Full suite
```bat
.venv\Scripts\python.exe -m pytest -q
```

### Targeted suites
```bat
.venv\Scripts\python.exe -m pytest tests/test_web.py -q
.venv\Scripts\python.exe -m pytest tests/test_songs.py tests/test_urls.py -q
.venv\Scripts\python.exe -m pytest tests/test_player_manager.py tests/test_rotation.py -q
```

## What is Covered
- DB creation and persistence
- Session lifecycle and house code flows
- Queue operations and singer rotation
- User/song routes and Socket.IO event flows
- Local library indexing/search
- Player route/media behavior
- Link validation (YouTube/Apple Music/Spotify)
- Bulk import validation and duplicate handling

## External Provider Testing
- Unit/integration tests do not require live provider access.
- Metadata lookups are validated through route behavior and controlled inputs.
- Optional manual integration checks can be done with live URLs when network allows.

## Current Known Warnings
- Deprecation warnings from `datetime.utcnow()` paths remain and are tracked for future cleanup.

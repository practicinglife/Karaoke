# Changelog

## 2026-09-30

### Added
- Added Spotify as a first-class streaming service:
  - URL validation
  - metadata resolution via provider dispatch
  - single-song save support
  - bulk import support (guest and admin)
- Added bulk import safeguards:
  - CSV-style header row detection (`provider,url,artist,title`)
  - per-request duplicate URL detection
  - persisted duplicate song detection per singer
  - stricter per-line provider URL validation
- Added project-level documentation set:
  - `ARCHITECTURE.md`
  - `INSTALL.md`
  - `CONFIGURATION.md`
  - `IMPORTING_LINKS.md`
  - `SECURITY.md`
  - `TESTING.md`
  - `TROUBLESHOOTING.md`

### Changed
- Updated guest and admin templates/UI for Spotify service selection.
- Updated queue singer rotation ordering logic to restore expected fairness behavior.
- Updated player-manager tests to align test doubles with current player interface.

### Fixed
- Fixed failing rotation test (`test_singer_rotation_on`).
- Fixed failing player manager test (`test_player_manager_prepare_and_start_job`).

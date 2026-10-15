# Changelog

## v1.1.2 — 2026-10-15

### Fixed
- Apple Music songs on albums with an animated cover opened to a blank lyrics screen and
  never played, and stopped partway through when played by hand. The silent cover video was
  taken for the song; it's now ignored (`ignore_media` in `stage/selectors.json`).
- The stage no longer opens lyrics or full screen over a song that isn't playing, and clicks
  play once more if the song didn't start.
- Edge's "connect to devices on your local network" popup on YouTube is blocked in the
  stage window.

### Changed
- The log records each stage song: loading, each step, started, and why it ended. Web
  requests are no longer logged one per line, which had pushed the stage lines out of the log.

## v1.1.1 — 2026-10-14

### Changed
- **Singer rotation:** singers keep the place they first joined in for the whole night, one
  song per turn. A new singer joins at the start of the next round. A singer with nothing
  queued keeps their place and their turn is skipped; queueing again puts them back in that
  place (previously whoever queued most recently jumped to the top). Admin MOVE UP/DOWN swaps
  two singers' places in the rotation.
- **START HOUSE opens the stage screen** (intermission screen and break music) automatically.
- README rewritten around the self-running show.

### Fixed
- A singer who just finished could be called straight back up during the intermission.
- Songs could stop early after clicking in the stage window (restarting or switching the
  track).
- Finishing or cancelling Teach mode during a song dropped that song; it now plays again.

## v1.1.0 — 2026-10-11

### Added
- Stage screen: a dedicated Microsoft Edge window on a chosen monitor plays YouTube,
  YouTube Music, Spotify, Apple Music and built-in traditional karaoke fullscreen, detects
  when the song ends, and shows an intermission screen (next singer, countdown, break music)
  until the singer is ready.
- Ready triggers: START MY SONG on the singer's phone, a mic-stand iPad/iPhone page (QR code
  in the desktop app and admin page), a hotkey for foot pedals/presenter clickers, a network
  button URL, or the host. Admin PLAY works the same way.
- Per-service steps in `stage/selectors.json` (Apple Music: highlighted track row, lyrics,
  lyrics full screen) and Teach mode to record a service's steps by hand.
- Manual mode, and automatic hand-over when the host clicks in the stage window.
- Recently Played with PLAY AGAIN on the admin page; live admin updates.
- BACKUP USER DATA / IMPORT USER DATA in the desktop app.
- `KaraokeTicker.exe --self-test` install check for the stage screen.

### Changed
- The Windows build bundles Playwright (it drives the installed Edge) and no longer bundles
  the repo's `data` folder.
- Library status shows total and new songs; SQLite runs in WAL mode.
- The web server restarts automatically when the app reopens with a house running.

### Fixed
- Library rescans duplicated every MP3+CDG pair, growing the database until scans never
  finished. A one-time cleanup (with an automatic backup first) removes the duplicates.
- Desktop status froze at "Building local index" during scans.
- Stage sign-ins were lost when the window closed; no more "Open Spotify?" or Translate
  popups on the stage.

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

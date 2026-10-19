# Changelog

## v1.1.9 — 2026-10-19

### Changed
- **Saved songs are easier to find.** More than 10 saved songs show as a compact list (one
  slim row per song) instead of big tiles; a LIST / TILES switch lets each phone choose and
  remembers it. A **Find in my songs** box narrows the list as you type, and songs sort by
  newest added, title A–Z or artist A–Z. Songs queued tonight show first.
- **Songs already sung tonight** drop to the bottom with a green **✓ PLAYED TONIGHT** mark,
  updated live as soon as a song finishes (skipped songs don't count).
- **Song search merges spellings of the same song**: "The Change" / "Change, The",
  "&" / "and", "Goin'" / "Going", "Til" / "Till", "Long Neck" / "Longneck", one-letter
  typos ("Friends In Low Place") and short versions of a longer title ("Much Too Young").
  One-word titles stay apart ("Rodeo" / "Rodeo Or Mexico"). Artist names one letter off
  merge ("Kenny Rodgers"), and a pair is one group however it's credited ("Garth Brooks &
  Trisha Yearwood" = "Trisha Yearwood and Garth Brooks"). "Red Strokes, The" reads as
  "The Red Strokes".

### Fixed
- Duets by singers whose name contains a band word ("Garth **Brooks** & Trisha Yearwood",
  "Diana Ross & Lionel Richie") are labelled duets again; band names only count when they're
  the whole first part of the credit ("Brooks & Dunn", "Simon & Garfunkel").
- **REFRESH KARAOKE LIBRARY repairs saved songs**: a saved song whose file moved (for example
  from D:\Karaoke to C:\Users\Public\Downloads\Karaoke) is pointed at the current file with the
  same name, so it plays again; songs saved from disc-code files ("CBD-105262 - …") get the
  real artist and title. Click REFRESH KARAOKE LIBRARY once after upgrading.

## v1.1.8 — 2026-10-19

### Changed
- **Song search groups results** (traditional karaoke). While typing, matching **artists**
  show with how many songs they have, and matching **song titles** below. Tap an artist to
  see their songs A–Z; tap a song to see its versions: Karaoke (vocals removed) and Sing
  Along (with vocals) videos, other videos, and CD+G discs by brand. Every song and version
  has a one-tap **ADD**; a song's ADD picks the best version (a vocals-removed video first,
  Sing Along never by default). Duets show under each singer and as the pair. Type an
  artist and a title together ("dolly jolene") to go straight to the song; "duets" and
  "kids" still work. Search now counts the whole library instead of stopping at 120 files.
- Songs added from disc-code files ("CBD-105262 - Dolly Parton - …") are saved with the
  real artist and title. Disc codes, track numbers, "Last, First" names and tags like (MPX)
  are tidied for search only; your files are never renamed.

## v1.1.7 — 2026-10-19

### Added
- The stage's break screen shows **NOW PLAYING** with the name of the break song that's
  playing (taken from its file name, e.g. "Johnny Cash - Hurt"). It hides when the music
  fades out for the next singer. Name break songs "Artist - Title" for the best result.

## v1.1.6 — 2026-10-19

### Added
- **Duet and Kids labels** on library songs, searchable: type **duets** (or duet) or **kids**
  (kid, children) in the song search to list every song with that label, or add a name to narrow
  it down ("duets dolly", "kids frozen"). Results show [DUET] / [KIDS]. Duets come from discs
  marked "(Duet)" and two singers credited together (not bands like "Tom Petty & The
  Heartbreakers"); kids songs from Disney/kids discs, kids' films, artists and nursery songs. The
  keyword lists are in `karaoke/song_tags.py`. The existing library is labelled once when the
  app starts (after a backup); later refreshes keep it current.

### Fixed
- Karaoke videos and MP3s whose file name is only the song title ("Can I Come Over.mp4") now
  get their artist (and title) from the file's own tags, so they show the artist in search
  instead of asking for it. Files already indexed without an artist are re-read on the next
  REFRESH KARAOKE LIBRARY.

## v1.1.5 — 2026-10-15

### Added
- App icon and logo: KaraokeTicker.exe, the desktop app's window and taskbar, browser tabs,
  phone and iPad home-screen icons (web app manifest), and the page headers.

## v1.1.4 — 2026-10-15

### Changed
- The build compiles its own copy of PyInstaller's launcher instead of using the prebuilt one.
  The prebuilt launcher is shared by many programs, malware included, so a few antivirus
  scanners flagged KaraokeTicker.exe (1 of 63 on VirusTotal for v1.1.3: Bkav Pro, generic
  detection). Building it needs the Visual Studio C++ build tools.
- KaraokeTicker.exe now carries file details (product name, version, publisher) under
  Properties > Details.
- `build.bat` can sign the exe when a code-signing certificate is set up (`KT_SIGN_ARGS`).

## v1.1.3 — 2026-10-15

### Fixed
- The database's write-ahead log (`karaoke.db-wal`) stayed at about 540 MB after the
  one-time library cleanup. SQLite never shrinks that file on its own; it's now capped at
  64 MB and emptied at startup, after a library scan and on exit.

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

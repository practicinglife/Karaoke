# Configuration

## Primary Settings
Configured from Settings page or persisted in `settings` table.

- `house_name`
- `karaoke_folder`
- `karaoke_manifest_path`
- `playback_mode` (`built_in`, `system_default`, `external_application`)
- `external_application_path`
- `traditional_karaoke_server_url`
- `web_server_port`
- `ticker_upcoming_count`
- `singer_rotation_on`

## Environment Variables
- `KARAOKE_TICKER_PORT`
- `KARAOKE_TICKER_SECRET`

## Playback Modes
- **built_in**: uses in-app player routes/surfaces.
- **system_default**: opens selected media/url via OS associations.
- **external_application**: launches configured external executable path. Rarely needed (the built-in player plays MP3+CDG and video on the stage screen). Tested with Kanto, which loads MP3+CDG directly; other players are untested.

## Library Indexing
- Configure karaoke folder.
- Run **Refresh Karaoke Library** in GUI.
- CDG+MP3 pairing is indexed as a single traditional track entry.

## Stage Screen
A dedicated Edge window (started normally, then controlled over its DevTools port) on the audience screen that plays
YouTube, YouTube Music, Spotify, Apple Music and built-in traditional karaoke songs,
pressing play / lyrics / fullscreen for you. Between songs it shows the next singer
with a countdown and intermission music until that singer presses **ready**.

Settings (Settings page → Stage Screen):

- `stage_auto_steps` — `1` (default): the app presses play/lyrics/full screen; `0`: manual mode (AUTOMATIC STEPS switch on the admin Stage card)
- `stage_monitor` — which screen the window opens on (dropdown of detected screens; MOVE STAGE TO THIS SCREEN on the admin page moves an open window)
- `stage_fullscreen` — open the window full screen
- `intermission_folder` — music played between songs (mp3, m4a, aac, wav, ogg, flac)
- `countdown_seconds` — countdown shown for the next singer
- `countdown_expiry_action` — `wait` (keep waiting), `start` (start anyway), `bump` (move them down one)
- `ready_hotkey` — key sent by a mic-stand button (foot pedal, presenter clicker, Bluetooth remote)
- `stage_button_secret` — key in the network button URL shown on the Settings page

Ready triggers: START MY SONG on the singer's phone, the ready hotkey, the network
button URL (`/api/stage/ready?key=...`, GET or POST), or START NEXT SINGER NOW on the admin page.

First-time setup:

1. `pip install -r requirements.txt` (Playwright uses the installed Microsoft Edge; no browser download needed).
2. Start the house, click **OPEN STAGE**, and sign in to Apple Music, Spotify and YouTube
   in that window once. Sign-ins are kept in `data/stage-profile/`. Press F11 to leave full screen while signing in.

### Teach mode (recommended for Apple Music and Spotify)
On the admin page, under **Teach a service**, pick the service, paste a song link and click
**START TEACHING**. The stage window opens that song on the main screen; do exactly what you
would do by hand (play, lyrics, maximize, full screen). Each click is recorded with several
ways to find that button again; clicks that start playback are only repeated when the song is
paused, and clicks that go full screen are skipped when it already is. Click **SAVE WHAT I DID**.
Taught steps are stored in `data/stage_selectors.json` and override the built-in ones in
`stage/selectors.json`; **USE BUILT-IN STEPS FOR THIS SERVICE** removes them.

Besides steps, each service in `stage/selectors.json` can list `ignore_media`: selectors for
decorative video or audio that isn't the song. Apple Music's animated album covers are
listed there, so a silent cover video can't make the app think the song is already playing
or has ended.

With a song on the stage screen, **TEST SELECTORS ON CURRENT SONG PAGE** shows which buttons
the app can currently find.

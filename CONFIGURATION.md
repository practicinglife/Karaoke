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
- **external_application**: launches configured external executable path.

## Library Indexing
- Configure karaoke folder.
- Run **Refresh Karaoke Library** in GUI.
- CDG+MP3 pairing is indexed as a single traditional track entry.

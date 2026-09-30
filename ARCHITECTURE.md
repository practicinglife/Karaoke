# Architecture

## Selected Foundation
- Base application: `Karaoke Ticker` (Python/Flask/Socket.IO/SQLite).
- Reused concepts:
  - `cdgraphics`: frame-accurate CDG rendering model for browser playback design.
  - `Karaoke Eternal`: responsive player/queue UX and room/queue synchronization patterns.

## Runtime Components
- **Desktop host**: `main.py` + `gui.py` for operator controls.
- **Web server**: `app.py` (Flask + Flask-SocketIO, threading mode).
- **Persistence**: SQLAlchemy models over SQLite (`karaoke/models.py`).
- **Queue engine**: `karaoke/queue_manager.py`.
- **Indexing/search**: `karaoke/library_indexer.py` and `karaoke/index_service.py`.
- **Playback**: `playback/*` manager and players; built-in player routes for local media.

## Data Domains
- Users and saved songs
- Sessions and house codes
- Queue items and playback states
- Indexed traditional karaoke library entries
- Settings and event logs

## Link Provider Model
- Services currently supported in-app:
  - `youtube`
  - `apple_music`
  - `spotify`
- Provider flow in routes:
  - URL validation (allow-list)
  - metadata resolve (provider dispatch)
  - duplicate checks (request + persisted)
  - save via `create_song`

## Live Update Model
- Queue/ticker/admin/user surfaces synchronize through Socket.IO events (`queue_updated`).
- Admin actions mutate queue state and emit updates to all connected clients.

## Security Controls
- CSRF protection for state-changing form routes.
- Admin/ticker token authorization guards.
- Local file path constraints and path traversal checks for media routes.
- URL validation allow-lists for streaming providers.

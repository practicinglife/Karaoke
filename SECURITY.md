# Security

## Current Controls
- CSRF validation on POST/state-changing endpoints.
- Admin/ticker token checks for privileged routes.
- URL allow-list validation for YouTube, Apple Music, Spotify, and remote server URL setting.
- Local media path protection with base-path checks for player media routes.
- SQLAlchemy parameterized access patterns (no user-built raw SQL).

## Operational Recommendations
- Set `KARAOKE_TICKER_SECRET` per environment.
- Keep app on trusted LAN unless reverse proxy/TLS/auth hardening is added.
- Back up `data/karaoke.db` regularly.
- Restrict filesystem permissions for app/data folders.
- Review logs for destructive admin actions and unusual request patterns.

## Known Limits
- Full account/password admin login flow is not implemented yet; admin access uses session-scoped admin token URLs.
- Rate limiting is limited; add reverse-proxy or middleware enforcement for internet-exposed deployments.

# Importing Links

## Supported Providers
- YouTube
- Apple Music
- Spotify

## Single Add
From guest user page:
1. Select service.
2. Paste provider URL.
3. Enter or auto-resolve title/artist.
4. Save song.

## Bulk Add (Guest/Admin)
Accepted line patterns:
- `URL | Artist | Title`
- `URL,Artist,Title`
- `service|URL|Artist|Title` where service is `youtube`, `apple_music`, or `spotify`
- URL-only or URL+Title lines are accepted; metadata resolution is attempted.

Optional CSV-style header row is skipped when detected:
- `provider,url,artist,title`

## Validation and Duplicate Handling
- Provider URL allow-list validation per service.
- Rejects unsupported services and malformed URLs.
- De-duplicates duplicate URLs within the same bulk request.
- Rejects songs already saved for the same singer (URL/service or matching title/artist/service).
- Reports line-level errors while continuing other rows.

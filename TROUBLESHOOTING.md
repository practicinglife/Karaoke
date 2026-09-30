# Troubleshooting

## App fails to start
- Ensure Python 3.11+ is installed.
- Recreate virtual environment and reinstall dependencies.
- Check `logs/karaoke-ticker.log` for startup exceptions.

## Guests cannot join
- Confirm house is running and join code is active.
- Verify host IP/port and LAN reachability.
- Check local firewall rules.

## Library search returns no results
- Confirm karaoke folder path is valid.
- Re-run library refresh/index.
- Verify files are present and readable.

## Bulk import fails for some lines
- Use one song per line.
- Verify provider URL format is valid for selected service.
- Remove duplicate links from same submission.
- Ensure title/artist exists or metadata can be resolved.

## Player media route errors
- Ensure indexed item is still available on disk.
- Check that file path remains under configured media root.
- Re-index library after file moves/renames.

## Admin/ticker access denied
- Verify current session admin/ticker token.
- Tokens change with new sessions.

#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# VEAU Backup Script
# Downloads a backup of the database + uploads from any host.
#
# Usage:
#   ./backup.sh
#
# Environment variables (set in .env or export them):
#   BACKUP_URL    - Your app URL (e.g. https://web-production-76788.up.railway.app)
#   BACKUP_SECRET - The secret token matching BACKUP_SECRET on the server
#
# Or create a .env file in the project root:
#   BACKUP_URL=https://web-production-76788.up.railway.app
#   BACKUP_SECRET=your-secret-here
#
# To set up as a daily cron job:
#   crontab -e
#   0 3 * * * cd /Users/arthurwagemans/Desktop/Bier_Strava && ./backup.sh >> backups/cron.log 2>&1
# ─────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="$SCRIPT_DIR/backups"
MAX_BACKUPS=10

# Load .env if it exists
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# Validate required vars
if [ -z "${BACKUP_URL:-}" ]; then
    echo "ERROR: BACKUP_URL is not set."
    echo "  Export it or add to .env: BACKUP_URL=https://your-app.up.railway.app"
    exit 1
fi

if [ -z "${BACKUP_SECRET:-}" ]; then
    echo "ERROR: BACKUP_SECRET is not set."
    echo "  Export it or add to .env: BACKUP_SECRET=your-secret"
    exit 1
fi

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Generate filename with timestamp
TIMESTAMP=$(date +%Y-%m-%d-%H%M%S)
FILENAME="veau-${TIMESTAMP}.tar.gz"
FILEPATH="$BACKUP_DIR/$FILENAME"

echo "VEAU Backup"
echo "  Source: $BACKUP_URL"
echo "  Time:   $(date)"
echo ""

# Download backup
echo "Downloading backup..."
HTTP_CODE=$(curl -s -w "%{http_code}" -o "$FILEPATH" \
    "${BACKUP_URL}/api/backup?secret=${BACKUP_SECRET}")

if [ "$HTTP_CODE" != "200" ]; then
    echo "ERROR: Server returned HTTP $HTTP_CODE"
    rm -f "$FILEPATH"
    if [ "$HTTP_CODE" = "403" ]; then
        echo "  Check your BACKUP_SECRET — it doesn't match the server."
    elif [ "$HTTP_CODE" = "404" ]; then
        echo "  BACKUP_SECRET is not configured on the server."
    fi
    exit 1
fi

# Verify it's a valid tar.gz
if ! tar -tzf "$FILEPATH" > /dev/null 2>&1; then
    echo "ERROR: Downloaded file is not a valid tar.gz archive."
    rm -f "$FILEPATH"
    exit 1
fi

# Show summary
SIZE=$(du -h "$FILEPATH" | cut -f1)
FILE_COUNT=$(tar -tzf "$FILEPATH" | wc -l | tr -d ' ')
echo ""
echo "Backup saved!"
echo "  File:   $FILEPATH"
echo "  Size:   $SIZE"
echo "  Files:  $FILE_COUNT"

# Cleanup old backups (keep last MAX_BACKUPS)
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/veau-*.tar.gz 2>/dev/null | wc -l | tr -d ' ')
if [ "$BACKUP_COUNT" -gt "$MAX_BACKUPS" ]; then
    DELETE_COUNT=$((BACKUP_COUNT - MAX_BACKUPS))
    echo ""
    echo "Cleaning up $DELETE_COUNT old backup(s) (keeping last $MAX_BACKUPS)..."
    ls -1t "$BACKUP_DIR"/veau-*.tar.gz | tail -n "$DELETE_COUNT" | xargs rm -f
fi

echo ""
echo "Done! To restore: flask restore $FILEPATH"

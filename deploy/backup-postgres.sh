#!/usr/bin/env bash
set -Eeuo pipefail

project_dir="${NICOPTION_PROJECT_DIR:-/opt/nicoption}"
backup_dir="${NICOPTION_BACKUP_DIR:-/var/backups/nicoption/postgres}"
retention_days="${NICOPTION_BACKUP_RETENTION_DAYS:-14}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
final_path="$backup_dir/nicoption-$timestamp.dump"
temporary_path="$final_path.partial"

cleanup() { rm -f "$temporary_path"; }
trap cleanup EXIT
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
find "$backup_dir" -maxdepth 1 -type f -name 'nicoption-*.dump' -exec chmod 600 {} +
cd "$project_dir"
docker compose --env-file .env.production -f compose.production.yml exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$temporary_path"
test -s "$temporary_path"
docker compose --env-file .env.production -f compose.production.yml exec -T db pg_restore --list < "$temporary_path" > /dev/null
mv "$temporary_path" "$final_path"
chmod 600 "$final_path"
find "$backup_dir" -type f -name 'nicoption-*.dump' -mtime "+$retention_days" -delete
printf 'Backup created and verified: %s\n' "$final_path"

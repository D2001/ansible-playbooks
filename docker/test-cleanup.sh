#!/bin/bash

# Test OneDrive cleanup logic
SERVICE_NAME="paperless"
MAX_ONEDRIVE_BACKUPS=7
RCLONE_REMOTE="onedrive:paperless_backups"

echo "=== Testing OneDrive Cleanup Logic ==="

# Check if OneDrive remote exists and has files
if ! rclone lsf "$RCLONE_REMOTE" >/dev/null 2>&1; then
  echo "OneDrive remote not accessible or empty, skipping cleanup"
  exit 0
fi

# Get list of backup files from OneDrive, sorted by date (newest first)
files_to_delete=$(rclone lsf "$RCLONE_REMOTE" | \
  grep "^${SERVICE_NAME}_backup_.*\.tar\.gz$" | \
  sort -r | \
  tail -n +$((MAX_ONEDRIVE_BACKUPS + 1)))

if [ -z "$files_to_delete" ]; then
  echo "No old backups to delete from OneDrive"
  exit 0
fi

echo "Files that would be deleted from OneDrive:"
echo "$files_to_delete"
echo ""
echo "Total files to delete: $(echo "$files_to_delete" | wc -l)"

# Show files that would be kept
files_to_keep=$(rclone lsf "$RCLONE_REMOTE" | \
  grep "^${SERVICE_NAME}_backup_.*\.tar\.gz$" | \
  sort -r | \
  head -n $MAX_ONEDRIVE_BACKUPS)

echo ""
echo "Files that would be kept (newest $MAX_ONEDRIVE_BACKUPS):"
echo "$files_to_keep"

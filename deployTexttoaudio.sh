#!/bin/bash
set -e

LOG_FILE=~/TexttoAudio/deploy.log
DATE=$(date '+%Y-%m-%d %H:%M:%S')

log() {
    echo "[$DATE] $1" | tee -a $LOG_FILE
}

log "==============================================="
log "🚀 Bắt đầu deployment..."
log "📥 Pulling latest code from GitHub..."
cd ~/TexttoAudio
git fetch --all -p        2>&1 | tee -a "$LOG_FILE"
git reset --hard origin/main 2>&1 | tee -a "$LOG_FILE"
log "🔧 Running deployment steps..."
# Thêm các bước deploy của bạn ở đây
log "✅ Deployment hoàn tất!"
log "==============================================="
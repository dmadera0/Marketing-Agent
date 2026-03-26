#!/usr/bin/env bash
# deploy.sh — Deploy or update BuenaVista AI Content Engine on EC2
# Usage:
#   ./scripts/deploy.sh               # Deploy with defaults
#   ./scripts/deploy.sh --env prod    # Explicit environment
#   ./scripts/deploy.sh --update      # Pull latest code + restart (no infra changes)

set -euo pipefail

# ── Config ─────────────────────────────────────────────────────────────────
ENV="${DEPLOY_ENV:-prod}"
EC2_USER="ec2-user"
APP_DIR="/opt/buenavistaai"
KEY_PATH="${EC2_KEY_PATH:-~/.ssh/buenavistaai.pem}"

# Parse args
UPDATE_ONLY=false
for arg in "$@"; do
  case $arg in
    --update) UPDATE_ONLY=true ;;
    --env=*) ENV="${arg#*=}" ;;
  esac
done

# ── Helpers ────────────────────────────────────────────────────────────────
log() { echo -e "\033[0;36m▶  $1\033[0m"; }
success() { echo -e "\033[0;32m✓  $1\033[0m"; }
fail() { echo -e "\033[0;31m✗  $1\033[0m"; exit 1; }

require() { command -v "$1" >/dev/null 2>&1 || fail "$1 is required but not installed"; }
require terraform
require ssh
require rsync

# ── Get EC2 IP from Terraform output ──────────────────────────────────────
log "Reading EC2 IP from Terraform state..."
cd "$(dirname "$0")/../terraform"

if [ "$UPDATE_ONLY" = false ]; then
  log "Running terraform apply..."
  terraform init -upgrade
  terraform apply -auto-approve -var="environment=$ENV"
fi

EC2_IP=$(terraform output -raw public_ip 2>/dev/null) || fail "Could not read public_ip from Terraform output. Run a full deploy first."
success "EC2 IP: $EC2_IP"

# ── Copy files to EC2 ─────────────────────────────────────────────────────
cd "$(dirname "$0")/.."
log "Syncing application files to EC2..."
rsync -az --delete \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.env' \
  -e "ssh -i $KEY_PATH -o StrictHostKeyChecking=no" \
  ./ "$EC2_USER@$EC2_IP:$APP_DIR/"

# ── Copy .env file ────────────────────────────────────────────────────────
if [ -f .env ]; then
  log "Uploading .env..."
  scp -i "$KEY_PATH" -o StrictHostKeyChecking=no .env "$EC2_USER@$EC2_IP:$APP_DIR/.env"
  success ".env uploaded"
else
  echo "⚠  No .env file found locally. Make sure it exists on the server at $APP_DIR/.env"
fi

# ── Restart Docker containers ──────────────────────────────────────────────
log "Rebuilding and restarting containers..."
ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no "$EC2_USER@$EC2_IP" << 'REMOTE'
  set -e
  cd /opt/buenavistaai
  docker compose -f docker/docker-compose.yml pull 2>/dev/null || true
  docker compose -f docker/docker-compose.yml up -d --build
  docker compose -f docker/docker-compose.yml ps
REMOTE

success "Deployment complete!"
echo ""
echo "  API URL : http://$EC2_IP:8000"
echo "  Docs    : http://$EC2_IP:8000/docs"
echo "  Drafts  : http://$EC2_IP:8000/drafts"
echo ""
echo "SSH in:  ssh -i $KEY_PATH $EC2_USER@$EC2_IP"

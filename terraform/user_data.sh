#!/bin/bash
set -euo pipefail

# Injected by Terraform templatefile()
ENVIRONMENT="${environment}"
AWS_REGION="${aws_region}"
SSM_PREFIX="${ssm_prefix}"

# ── System updates ─────────────────────────────────────────────────────────
yum update -y
yum install -y git curl unzip jq

# ── Docker ────────────────────────────────────────────────────────────────
yum install -y docker
systemctl enable --now docker
usermod -aG docker ec2-user

# ── Docker Compose v2 ─────────────────────────────────────────────────────
COMPOSE_VERSION="2.27.0"
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/download/v$${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# ── Clone repo (update URL to your actual repo) ───────────────────────────
APP_DIR="/opt/buenavistaai"
git clone https://github.com/YOUR_ORG/buenavistaai-content-engine.git "$APP_DIR" 2>/dev/null || true
mkdir -p "$APP_DIR"
chown -R ec2-user:ec2-user "$APP_DIR"

# ── Build .env from SSM Parameter Store ───────────────────────────────────
# All secrets are stored in SSM SecureString params under $SSM_PREFIX/
# The EC2 IAM role has read access (granted by Terraform).
ENV_FILE="$APP_DIR/.env"

fetch_param() {
  local name="$1"
  aws ssm get-parameter \
    --name "$SSM_PREFIX/$name" \
    --with-decryption \
    --query "Parameter.Value" \
    --output text \
    --region "$AWS_REGION" 2>/dev/null || echo ""
}

cat > "$ENV_FILE" <<ENVEOF
# Auto-generated at boot from AWS SSM Parameter Store
# Do not edit — rerun user_data or update SSM params and restart

ANTHROPIC_API_KEY=$(fetch_param ANTHROPIC_API_KEY)
REVIEW_TOKEN_SECRET=$(fetch_param REVIEW_TOKEN_SECRET)

MEDIUM_INTEGRATION_TOKEN=$(fetch_param MEDIUM_INTEGRATION_TOKEN)
MEDIUM_PUBLICATION_ID=$(fetch_param MEDIUM_PUBLICATION_ID)

SITE_TYPE=$(fetch_param SITE_TYPE)
WP_URL=$(fetch_param WP_URL)
WP_USER=$(fetch_param WP_USER)
WP_APP_PASSWORD=$(fetch_param WP_APP_PASSWORD)
SITE_WEBHOOK_URL=$(fetch_param SITE_WEBHOOK_URL)
SITE_WEBHOOK_SECRET=$(fetch_param SITE_WEBHOOK_SECRET)

LINKEDIN_ACCESS_TOKEN=$(fetch_param LINKEDIN_ACCESS_TOKEN)
LINKEDIN_PERSON_URN=$(fetch_param LINKEDIN_PERSON_URN)

TWITTER_API_KEY=$(fetch_param TWITTER_API_KEY)
TWITTER_API_SECRET=$(fetch_param TWITTER_API_SECRET)
TWITTER_ACCESS_TOKEN=$(fetch_param TWITTER_ACCESS_TOKEN)
TWITTER_ACCESS_TOKEN_SECRET=$(fetch_param TWITTER_ACCESS_TOKEN_SECRET)

FACEBOOK_PAGE_ID=$(fetch_param FACEBOOK_PAGE_ID)
FACEBOOK_PAGE_TOKEN=$(fetch_param FACEBOOK_PAGE_TOKEN)
INSTAGRAM_USER_ID=$(fetch_param INSTAGRAM_USER_ID)
INSTAGRAM_ACCESS_TOKEN=$(fetch_param INSTAGRAM_ACCESS_TOKEN)
INSTAGRAM_IMAGE_URL=$(fetch_param INSTAGRAM_IMAGE_URL)
BLOG_BASE_URL=$(fetch_param BLOG_BASE_URL)

REVIEW_EMAIL=$(fetch_param REVIEW_EMAIL)
SMTP_HOST=$(fetch_param SMTP_HOST)
SMTP_PORT=$(fetch_param SMTP_PORT)
SMTP_USER=$(fetch_param SMTP_USER)
SMTP_PASS=$(fetch_param SMTP_PASS)
APP_BASE_URL=$(fetch_param APP_BASE_URL)

CONTENT_STORE_DIR=/data/content
ENVEOF

chmod 600 "$ENV_FILE"
chown ec2-user:ec2-user "$ENV_FILE"

# ── Start service ─────────────────────────────────────────────────────────
cd "$APP_DIR"
if [ -f docker/docker-compose.yml ] && [ -f .env ]; then
  docker compose -f docker/docker-compose.yml up -d --build
fi

# ── Systemd service (auto-restart on reboot) ──────────────────────────────
cat > /etc/systemd/system/buenavistaai.service <<'SVCEOF'
[Unit]
Description=BuenaVista AI Content Engine
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/buenavistaai
ExecStart=/usr/local/lib/docker/cli-plugins/docker-compose -f docker/docker-compose.yml up -d
ExecStop=/usr/local/lib/docker/cli-plugins/docker-compose -f docker/docker-compose.yml down
User=ec2-user

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl enable buenavistaai
systemctl daemon-reload

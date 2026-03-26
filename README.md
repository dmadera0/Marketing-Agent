# BuenaVista AI Solutions — Content Engine

Automated content pipeline that generates SEO-optimised blog posts and platform-specific social media content using the Claude API, then publishes or queues them for human review.

---

## Architecture

```
Topic + Sources
      │
      ▼
 FastAPI Server (EC2 + Docker)
      │
      ├─► Content Generation Agent (Claude)
      │         Produces: blog, LinkedIn, Twitter, Facebook/IG
      │
      ├─► SEO Enrichment Agent (Claude)
      │         Keyword density, meta, slug, readability
      │
      ├─► AUTO-PUBLISH ──► Medium API
      │                ──► Company Site (WordPress / Webhook)
      │
      └─► DRAFT + EMAIL ──► LinkedIn (review queue)
                        ──► Twitter/X (review queue)
                        ──► Facebook/Instagram (review queue)
```

**Infrastructure:** AWS EC2 t3.small + Docker Compose, deployed via Terraform.  
**AI model:** Claude claude-opus-4-5 (Anthropic API).

---

## Quick Start

### 1. Prerequisites

- AWS CLI configured (`aws configure`)
- Terraform ≥ 1.6 installed
- An EC2 key pair created in your target region
- An Anthropic API key

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys and credentials
```

### 3. Deploy to AWS

```bash
chmod +x scripts/deploy.sh
EC2_KEY_PATH=~/.ssh/your-key.pem ./scripts/deploy.sh
```

This runs `terraform apply`, provisions the EC2 instance, copies your app files, and starts the Docker containers. The full deploy takes ~3 minutes.

### 4. Verify it's running

```bash
curl http://<YOUR_EC2_IP>:8000/health
# {"status":"ok","service":"BuenaVista Content Engine"}
```

Interactive API docs: `http://<YOUR_EC2_IP>:8000/docs`

---

## Generating Content

### One-off (manual trigger via API)

```bash
curl -X POST http://<EC2_IP>:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "How AI is transforming small business operations in 2025",
    "target_keyword": "AI for small business",
    "sources": ["https://example.com/article1"],
    "tone": "professional yet approachable"
  }'

# Returns: {"content_id": "abc-123", "status": "processing"}
```

### Check status

```bash
curl http://<EC2_IP>:8000/content/abc-123
```

### Schedule automatic runs

**Option A — cron job (simplest):**

SSH into the EC2 instance and add a crontab entry:

```bash
ssh -i ~/.ssh/your-key.pem ec2-user@<EC2_IP>
crontab -e
```

Add (runs Mon/Wed/Fri at 9am PT):
```
0 16 * * 1,3,5 APP_BASE_URL=http://localhost:8000 python3 /opt/buenavistaai/scripts/scheduler.py >> /var/log/buenavistaai-scheduler.log 2>&1
```

**Option B — daemon mode (runs inside the container):**

Uncomment the scheduler service in `docker/docker-compose.yml` and set `SCHEDULER_ENABLED=true` in `.env`.

**Option C — one-off topic:**

```bash
python3 scripts/scheduler.py --topic "AI trends 2025" --keyword "AI trends"
```

---

## Reviewing & Approving Drafts

When a generation run completes, you'll receive an email for each draft platform (LinkedIn, Twitter, Facebook/Instagram) with the content preview and approve/reject commands.

### List all pending drafts

```bash
curl http://<EC2_IP>:8000/drafts
```

### Approve a draft

```bash
curl -X POST http://<EC2_IP>:8000/approve \
  -H "Content-Type: application/json" \
  -d '{
    "content_id": "abc-123",
    "platform": "linkedin",
    "action": "approve"
  }'
```

### Reject with feedback (triggers regeneration)

```bash
curl -X POST http://<EC2_IP>:8000/approve \
  -H "Content-Type: application/json" \
  -d '{
    "content_id": "abc-123",
    "platform": "twitter",
    "action": "reject",
    "feedback": "Make the hook punchier and reduce to 10 tweets max"
  }'
```

---

## Adding a New Platform Publisher

1. Create `app/publishers/your_platform_publisher.py`
2. Implement an `async def publish(self, variants: dict, content_id: str) -> dict` method
3. Register it in `app/publishers/router.py`
4. Add the relevant env vars to `.env.example`

---

## Content Calendar

Edit `scripts/scheduler.py` → `CONTENT_CALENDAR` list to manage your planned topics. The scheduler cycles through them in order, repeating when the list is exhausted. Each entry supports:

| Field | Description |
|---|---|
| `topic` | The content brief — be specific |
| `target_keyword` | Primary SEO keyword |
| `sources` | URLs for reference material (optional) |
| `extra_instructions` | Brand/angle direction for Claude |

---

## Updating the Deployment

Pull latest code and restart containers without re-provisioning infrastructure:

```bash
EC2_KEY_PATH=~/.ssh/your-key.pem ./scripts/deploy.sh --update
```

---

## Infrastructure Details

| Resource | Value |
|---|---|
| EC2 instance | t3.small (upgradeable via `var.instance_type`) |
| OS | Amazon Linux 2023 |
| Storage | 20 GB gp3 EBS (encrypted) |
| Elastic IP | Yes — stable IP for DNS |
| Security | IMDSv2, non-root container user, SSH restricted |
| State | Terraform (local by default — enable S3 backend for teams) |

**Estimated AWS cost:** ~$18–22/month for t3.small + EIP + storage.

---

## Environment Variables Reference

See `.env.example` for all variables with inline documentation.

---

## Project Structure

```
buenavistaai/
├── app/
│   ├── main.py                    # FastAPI app + endpoints
│   ├── agents/
│   │   ├── content_agent.py       # Claude content generation
│   │   └── seo_agent.py           # SEO enrichment
│   ├── publishers/
│   │   ├── router.py              # Routes to correct publisher
│   │   ├── medium_publisher.py    # Medium API (auto-publish)
│   │   ├── company_site_publisher.py  # WordPress / webhook (auto-publish)
│   │   └── draft_publisher.py     # Email review queue
│   └── utils/
│       └── storage.py             # File-based content store
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── nginx.conf                 # HTTPS reverse proxy
├── terraform/
│   ├── main.tf                    # EC2, SG, IAM, CloudWatch
│   ├── variables.tf
│   ├── outputs.tf
│   └── user_data.sh               # EC2 bootstrap script
├── scripts/
│   ├── scheduler.py               # Content calendar + cron trigger
│   └── deploy.sh                  # One-command deploy/update
├── requirements.txt
└── .env.example
```

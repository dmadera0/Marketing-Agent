"""
BuenaVista AI Solutions — Content Engine
Main FastAPI application. Exposes REST endpoints to trigger
content generation and manage draft approval workflows.
"""

import os
import hmac
import hashlib
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from app.agents.content_agent import ContentAgent
from app.agents.seo_agent import SEOAgent
from app.publishers.router import PublisherRouter
from app.utils.storage import ContentStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

store = ContentStore()
publisher = PublisherRouter()

# HMAC secret for signing one-click review links — set REVIEW_TOKEN_SECRET in .env
_TOKEN_SECRET = os.environ.get("REVIEW_TOKEN_SECRET", "change-me-in-production")


def _make_review_token(content_id: str, platform: str, action: str) -> str:
    """Generate an HMAC token for a one-click review link."""
    msg = f"{content_id}:{platform}:{action}"
    return hmac.new(_TOKEN_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()[:16]


def _verify_review_token(content_id: str, platform: str, action: str, token: str) -> bool:
    expected = _make_review_token(content_id, platform, action)
    return hmac.compare_digest(expected, token)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("BuenaVista Content Engine starting up...")
    yield
    logger.info("Shutting down.")

app = FastAPI(
    title="BuenaVista AI Content Engine",
    description="Automated blog and social media content pipeline",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response schemas ─────────────────────────────────────────────

class ContentRequest(BaseModel):
    topic: str
    sources: list[str] = []
    target_keyword: Optional[str] = None
    tone: Optional[str] = "professional yet approachable"
    extra_instructions: Optional[str] = None


class ApprovalRequest(BaseModel):
    content_id: str
    platform: str          # linkedin | twitter | facebook_instagram
    action: str            # approve | reject
    feedback: Optional[str] = None


# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "BuenaVista Content Engine"}


@app.post("/generate", status_code=202)
async def generate_content(req: ContentRequest, background_tasks: BackgroundTasks):
    """
    Kick off a full content generation run.
    Returns a content_id immediately; generation runs in background.
    """
    import uuid
    content_id = str(uuid.uuid4())
    background_tasks.add_task(_run_pipeline, content_id, req)
    return {"content_id": content_id, "status": "processing"}


@app.get("/content/{content_id}")
async def get_content(content_id: str):
    """Retrieve generated content and its current status."""
    data = store.get(content_id)
    if not data:
        raise HTTPException(status_code=404, detail="Content not found")
    return data


@app.get("/drafts")
async def list_drafts():
    """List all content items pending human review."""
    return store.list_by_status("pending_review")


@app.post("/approve")
async def approve_content(req: ApprovalRequest, background_tasks: BackgroundTasks):
    """
    Approve or reject a draft for a specific platform.
    Approved drafts are published immediately in the background.
    """
    data = store.get(req.content_id)
    if not data:
        raise HTTPException(status_code=404, detail="Content not found")

    if req.action == "approve":
        background_tasks.add_task(_publish_single, req.content_id, req.platform, data)
        store.update_status(req.content_id, req.platform, "publishing")
        return {"message": f"Publishing to {req.platform} queued"}

    elif req.action == "reject":
        store.update_status(req.content_id, req.platform, "rejected", notes=req.feedback)
        if req.feedback:
            background_tasks.add_task(_regenerate_platform, req.content_id, req.platform, req.feedback, data)
        return {"message": f"Draft rejected. {'Regenerating with feedback.' if req.feedback else ''}"}

    raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")


@app.get("/review", response_class=HTMLResponse)
async def one_click_review(
    background_tasks: BackgroundTasks,
    content_id: str = Query(...),
    platform: str = Query(...),
    action: str = Query(...),
    token: str = Query(...),
):
    """
    One-click approve/reject link sent in review emails.
    Validates HMAC token so only the email recipient can trigger actions.
    """
    if action not in ("approve", "reject"):
        return _review_page("Invalid action.", success=False)

    if not _verify_review_token(content_id, platform, action, token):
        return _review_page("Invalid or expired link.", success=False)

    data = store.get(content_id)
    if not data:
        return _review_page("Content not found.", success=False)

    platform_label = platform.replace("_", " ").title()

    if action == "approve":
        current = data.get("platform_statuses", {}).get(platform)
        if current == "published":
            return _review_page(f"Already published to {platform_label}.", success=True)
        background_tasks.add_task(_publish_single, content_id, platform, data)
        store.update_status(content_id, platform, "publishing")
        return _review_page(f"Approved! Publishing to {platform_label}…", success=True)

    else:  # reject
        store.update_status(content_id, platform, "rejected")
        return _review_page(
            f"{platform_label} draft rejected. Log in to the dashboard to regenerate with feedback.",
            success=True,
        )


def _review_page(message: str, success: bool) -> str:
    color = "#2e7d32" if success else "#c62828"
    icon = "✓" if success else "✗"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>BuenaVista AI — Review</title>
<style>body{{font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;
min-height:100vh;margin:0;background:#f5f5f5}}
.card{{background:#fff;border-radius:12px;padding:40px 48px;max-width:460px;text-align:center;
box-shadow:0 4px 20px rgba(0,0,0,.1)}}
h1{{color:{color};font-size:2rem;margin:0 0 12px}}p{{color:#555;font-size:1rem;margin:0}}
a{{display:inline-block;margin-top:24px;color:#1565c0;font-size:.9rem}}</style></head>
<body><div class="card">
<h1>{icon}</h1>
<p>{message}</p>
<a href="javascript:window.close()">Close this tab</a>
</div></body></html>"""


# ── Background pipeline ────────────────────────────────────────────────────

async def _run_pipeline(content_id: str, req: ContentRequest):
    """Full pipeline: generate → SEO → auto-publish blog channels → queue social drafts."""
    try:
        logger.info(f"[{content_id}] Starting pipeline for topic: {req.topic}")
        store.save(content_id, {"status": "generating", "topic": req.topic})

        # 1. Generate all content variants
        agent = ContentAgent()
        variants = await agent.generate(
            topic=req.topic,
            sources=req.sources,
            keyword=req.target_keyword,
            tone=req.tone,
            extra=req.extra_instructions,
        )

        # 2. SEO enrichment on the blog post
        seo = SEOAgent()
        variants["blog"] = await seo.enrich(variants["blog"], keyword=req.target_keyword)

        # 3. Save full content bundle
        store.save(content_id, {
            "status": "pending_review",
            "topic": req.topic,
            "variants": variants,
            "platform_statuses": {
                "medium": "auto_publish",
                "company_site": "auto_publish",
                "linkedin": "pending_review",
                "twitter": "pending_review",
                "facebook_instagram": "pending_review",
            }
        })

        # 4. Auto-publish to Medium + Company site (no review needed)
        for platform in ["medium", "company_site"]:
            await publisher.publish(platform, variants, content_id)
            store.update_status(content_id, platform, "published")
            logger.info(f"[{content_id}] Auto-published to {platform}")

        # 5. Queue social drafts for review — sends email with one-click links
        for platform in ["linkedin", "twitter", "facebook_instagram"]:
            await publisher.draft(platform, variants, content_id, _make_review_token)
            logger.info(f"[{content_id}] Draft queued for review: {platform}")

        logger.info(f"[{content_id}] Pipeline complete. Social drafts ready for review.")

    except Exception as e:
        logger.error(f"[{content_id}] Pipeline failed: {e}", exc_info=True)
        store.update_status(content_id, "all", "failed", notes=str(e))


async def _publish_single(content_id: str, platform: str, data: dict):
    """Publish an approved draft to the live platform."""
    try:
        await publisher.publish(platform, data["variants"], content_id)
        store.update_status(content_id, platform, "published")
        logger.info(f"[{content_id}] Published to {platform}")
    except Exception as e:
        logger.error(f"[{content_id}] Publish to {platform} failed: {e}")
        store.update_status(content_id, platform, "failed", notes=str(e))


async def _regenerate_platform(content_id: str, platform: str, feedback: str, data: dict):
    try:
        agent = ContentAgent()
        new_variant = await agent.regenerate_platform(
            platform=platform,
            original=data["variants"],
            feedback=feedback,
        )
        data["variants"][platform] = new_variant
        store.save(content_id, data)
        store.update_status(content_id, platform, "pending_review")
        # Re-send review email with updated draft
        await publisher.draft(platform, data["variants"], content_id, _make_review_token)
        logger.info(f"[{content_id}] Regenerated {platform} with feedback")
    except Exception as e:
        logger.error(f"[{content_id}] Regeneration failed: {e}")

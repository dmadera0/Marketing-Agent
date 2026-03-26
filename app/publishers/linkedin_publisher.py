"""
LinkedInPublisher — publishes to LinkedIn via the UGC Posts API (v2).

Required env vars:
  LINKEDIN_ACCESS_TOKEN  — OAuth 2.0 access token (openid, profile, w_member_social scopes)
  LINKEDIN_PERSON_URN    — e.g. "urn:li:person:XXXXXXXX"
                           Get it from GET https://api.linkedin.com/v2/userinfo

Docs: https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/ugc-post-api
"""

import os
import logging
import httpx

logger = logging.getLogger(__name__)

LINKEDIN_API = "https://api.linkedin.com/v2"


class LinkedInPublisher:
    def __init__(self):
        self.token      = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
        self.person_urn = os.environ.get("LINKEDIN_PERSON_URN", "")

    async def publish(self, variants: dict, content_id: str) -> dict:
        if not self.token or not self.person_urn:
            logger.warning("LINKEDIN_ACCESS_TOKEN or LINKEDIN_PERSON_URN not set — skipping")
            return {"platform": "linkedin", "status": "skipped", "reason": "missing credentials"}

        post_text = variants.get("linkedin", "")
        if not post_text:
            logger.warning(f"[{content_id}] No LinkedIn variant found")
            return {"platform": "linkedin", "status": "skipped", "reason": "no content"}

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type":  "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        # UGC Post payload — text-only article-style post
        payload = {
            "author":          self.person_urn,
            "lifecycleState":  "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": post_text[:3000],   # LinkedIn max
                    },
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{LINKEDIN_API}/ugcPosts",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            post_id = resp.headers.get("x-restli-id", resp.json().get("id", ""))
            post_url = f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else ""
            logger.info(f"[{content_id}] LinkedIn post published: {post_url}")
            return {
                "platform": "linkedin",
                "status":   "published",
                "post_id":  post_id,
                "url":      post_url,
            }

"""
FacebookInstagramPublisher — publishes to Facebook Page and Instagram Business
account via the Meta Graph API.

The ContentAgent produces a single variant with two sections:
  FACEBOOK POST: ...
  INSTAGRAM CAPTION: ...

This publisher parses each section and posts independently.

Required env vars:
  FACEBOOK_PAGE_ID      — Numeric Page ID
  FACEBOOK_PAGE_TOKEN   — Page Access Token (pages_manage_posts, pages_read_engagement)
  INSTAGRAM_USER_ID     — Instagram Business Account ID (linked to the FB Page)
  INSTAGRAM_ACCESS_TOKEN — Same Page Access Token works if IG account is linked

Docs:
  FB:  https://developers.facebook.com/docs/graph-api/reference/page/feed
  IG:  https://developers.facebook.com/docs/instagram-api/guides/content-publishing
"""

import os
import re
import logging
import httpx

logger = logging.getLogger(__name__)

GRAPH_API = "https://graph.facebook.com/v21.0"


class FacebookInstagramPublisher:
    def __init__(self):
        self.fb_page_id    = os.environ.get("FACEBOOK_PAGE_ID", "")
        self.fb_page_token = os.environ.get("FACEBOOK_PAGE_TOKEN", "")
        self.ig_user_id    = os.environ.get("INSTAGRAM_USER_ID", "")
        self.ig_token      = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")

    async def publish(self, variants: dict, content_id: str) -> dict:
        raw = variants.get("facebook_instagram", "")
        if not raw:
            logger.warning(f"[{content_id}] No Facebook/Instagram variant found")
            return {"platform": "facebook_instagram", "status": "skipped", "reason": "no content"}

        fb_text, ig_caption = self._parse_variant(raw)
        results = {}

        async with httpx.AsyncClient(timeout=30) as client:
            if self.fb_page_id and self.fb_page_token and fb_text:
                results["facebook"] = await self._post_facebook(client, fb_text, content_id)
            else:
                logger.warning(f"[{content_id}] Facebook credentials missing — skipping FB")
                results["facebook"] = {"status": "skipped", "reason": "missing credentials"}

            if self.ig_user_id and self.ig_token and ig_caption:
                results["instagram"] = await self._post_instagram(client, ig_caption, content_id)
            else:
                logger.warning(f"[{content_id}] Instagram credentials missing — skipping IG")
                results["instagram"] = {"status": "skipped", "reason": "missing credentials"}

        combined_status = (
            "published" if any(r.get("status") == "published" for r in results.values())
            else "skipped"
        )
        return {
            "platform": "facebook_instagram",
            "status":   combined_status,
            "results":  results,
        }

    async def _post_facebook(self, client: httpx.AsyncClient, text: str, content_id: str) -> dict:
        """Post to a Facebook Page feed."""
        # Replace [LINK] placeholder with a real URL if set
        blog_url = os.environ.get("BLOG_BASE_URL", "https://www.buenavistaaisolutions.com/blog")
        text = text.replace("[LINK]", blog_url)

        payload = {
            "message":      text[:63_206],   # FB page post character limit
            "access_token": self.fb_page_token,
        }
        resp = await client.post(f"{GRAPH_API}/{self.fb_page_id}/feed", data=payload)
        resp.raise_for_status()
        post_id  = resp.json().get("id", "")
        post_url = f"https://www.facebook.com/{post_id.replace('_', '/posts/')}" if post_id else ""
        logger.info(f"[{content_id}] Facebook post published: {post_url}")
        return {"status": "published", "post_id": post_id, "url": post_url}

    async def _post_instagram(
        self, client: httpx.AsyncClient, caption: str, content_id: str
    ) -> dict:
        """
        Publish a text-only Instagram post (carousel or reel require media).
        For image posts, set INSTAGRAM_IMAGE_URL in env to attach a photo.
        """
        image_url = os.environ.get("INSTAGRAM_IMAGE_URL", "")

        if image_url:
            # Step 1: create media container with image
            container_payload = {
                "image_url":    image_url,
                "caption":      caption[:2200],
                "access_token": self.ig_token,
            }
            c_resp = await client.post(
                f"{GRAPH_API}/{self.ig_user_id}/media", data=container_payload
            )
            c_resp.raise_for_status()
            container_id = c_resp.json().get("id")
        else:
            # Step 1b: text-only via REELS container (most permissive for text posts)
            container_payload = {
                "media_type":   "REELS",
                "caption":      caption[:2200],
                "access_token": self.ig_token,
                # text-only reels still need a video_url in practice;
                # without media IG will reject — caller should set INSTAGRAM_IMAGE_URL
            }
            logger.warning(
                f"[{content_id}] INSTAGRAM_IMAGE_URL not set. "
                "Instagram requires media. Post will likely fail without an image/video URL."
            )
            c_resp = await client.post(
                f"{GRAPH_API}/{self.ig_user_id}/media", data=container_payload
            )
            c_resp.raise_for_status()
            container_id = c_resp.json().get("id")

        # Step 2: publish the container
        p_resp = await client.post(
            f"{GRAPH_API}/{self.ig_user_id}/media_publish",
            data={"creation_id": container_id, "access_token": self.ig_token},
        )
        p_resp.raise_for_status()
        media_id  = p_resp.json().get("id", "")
        media_url = f"https://www.instagram.com/p/{media_id}/" if media_id else ""
        logger.info(f"[{content_id}] Instagram post published: {media_url}")
        return {"status": "published", "media_id": media_id, "url": media_url}

    @staticmethod
    def _parse_variant(text: str) -> tuple[str, str]:
        """
        Split the combined Facebook/Instagram variant into two sections.
        ContentAgent produces:
          FACEBOOK POST (...):\n...\n\nINSTAGRAM CAPTION (...):\n...
        """
        fb_match  = re.search(r"FACEBOOK POST[^\n]*\n([\s\S]+?)(?=INSTAGRAM CAPTION|$)", text, re.I)
        ig_match  = re.search(r"INSTAGRAM CAPTION[^\n]*\n([\s\S]+)", text, re.I)
        fb_text   = fb_match.group(1).strip()  if fb_match  else text.strip()
        ig_caption = ig_match.group(1).strip() if ig_match  else ""
        return fb_text, ig_caption

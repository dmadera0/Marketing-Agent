"""
CompanySitePublisher — publishes to the BuenaVista company website
via WordPress REST API (or a generic webhook for headless CMS).

Set SITE_TYPE=wordpress or SITE_TYPE=webhook in your .env.
"""

import os
import re
import json
import base64
import logging
import httpx

logger = logging.getLogger(__name__)


class CompanySitePublisher:
    def __init__(self):
        self.site_type = os.environ.get("SITE_TYPE", "wordpress").lower()
        # WordPress
        self.wp_url = os.environ.get("WP_URL", "").rstrip("/")
        self.wp_user = os.environ.get("WP_USER", "")
        self.wp_app_password = os.environ.get("WP_APP_PASSWORD", "")
        # Generic webhook (headless CMS / custom site)
        self.webhook_url = os.environ.get("SITE_WEBHOOK_URL", "")
        self.webhook_secret = os.environ.get("SITE_WEBHOOK_SECRET", "")

    async def publish(self, variants: dict, content_id: str) -> dict:
        blog = variants.get("blog", "")
        title_match = re.search(r"^#\s+(.+)$", blog, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else "New Post"

        # Extract SEO meta from HTML comment appended by SEOAgent
        meta_desc = ""
        seo_match = re.search(r"<!-- SEO: ({.+?}) -->", blog, re.DOTALL)
        if seo_match:
            try:
                seo = json.loads(seo_match.group(1))
                meta_desc = seo.get("meta_description", "")
                slug = seo.get("slug", "")
            except Exception:
                slug = ""
        else:
            slug = ""

        # Strip the SEO comment from body before publishing
        clean_blog = re.sub(r"\n*<!-- SEO: .+? -->", "", blog, flags=re.DOTALL).strip()

        if self.site_type == "wordpress":
            return await self._publish_wordpress(clean_blog, title, slug, meta_desc, content_id)
        else:
            return await self._publish_webhook(clean_blog, title, slug, meta_desc, content_id)

    async def _publish_wordpress(self, body, title, slug, meta_desc, content_id):
        if not self.wp_url:
            logger.warning("WP_URL not set — skipping company site publish")
            return {"platform": "company_site", "status": "skipped", "reason": "no wp_url"}

        credentials = base64.b64encode(
            f"{self.wp_user}:{self.wp_app_password}".encode()
        ).decode()

        headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        }

        payload = {
            "title": title,
            "content": body,   # WordPress accepts markdown with Gutenberg or a plugin
            "status": "publish",
            "categories": [],
            "tags": [],
            "meta": {"_yoast_wpseo_metadesc": meta_desc} if meta_desc else {},
        }
        if slug:
            payload["slug"] = slug

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.wp_url}/wp-json/wp/v2/posts",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            post = resp.json()
            logger.info(f"WordPress post published: {post.get('link')}")
            return {
                "platform": "company_site",
                "status": "published",
                "url": post.get("link"),
                "wp_id": post.get("id"),
            }

    async def _publish_webhook(self, body, title, slug, meta_desc, content_id):
        if not self.webhook_url:
            logger.warning("SITE_WEBHOOK_URL not set — skipping company site publish")
            return {"platform": "company_site", "status": "skipped", "reason": "no webhook"}

        payload = {
            "content_id": content_id,
            "title": title,
            "slug": slug,
            "body": body,
            "meta_description": meta_desc,
            "source": "buenavistaai-content-engine",
        }
        headers = {"Content-Type": "application/json"}
        if self.webhook_secret:
            headers["X-Webhook-Secret"] = self.webhook_secret

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.webhook_url, headers=headers, json=payload)
            resp.raise_for_status()
            logger.info(f"Company site webhook delivered: {resp.status_code}")
            return {
                "platform": "company_site",
                "status": "published",
                "webhook_response": resp.json() if resp.content else {},
            }

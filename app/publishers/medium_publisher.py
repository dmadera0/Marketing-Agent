"""
MediumPublisher — publishes blog content to Medium via their REST API.
Docs: https://github.com/Medium/medium-api-docs
"""

import os
import re
import logging
import httpx

logger = logging.getLogger(__name__)

MEDIUM_API = "https://api.medium.com/v1"


class MediumPublisher:
    def __init__(self):
        self.token = os.environ.get("MEDIUM_INTEGRATION_TOKEN", "")
        self.publication_id = os.environ.get("MEDIUM_PUBLICATION_ID", "")

    async def publish(self, variants: dict, content_id: str) -> dict:
        if not self.token:
            logger.warning("MEDIUM_INTEGRATION_TOKEN not set — skipping Medium publish")
            return {"platform": "medium", "status": "skipped", "reason": "no token"}

        blog = variants.get("blog", "")

        # Extract title from first H1 in markdown
        title_match = re.search(r"^#\s+(.+)$", blog, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else "BuenaVista AI — New Post"

        # Extract meta description comment if present
        tags = ["AI", "Artificial Intelligence", "Business", "Marketing", "Technology"]

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            # Get user ID
            me = await client.get(f"{MEDIUM_API}/me", headers=headers)
            me.raise_for_status()
            user_id = me.json()["data"]["id"]

            # Build post payload
            payload = {
                "title": title,
                "contentFormat": "markdown",
                "content": blog,
                "tags": tags,
                "publishStatus": "public",
                "notifyFollowers": True,
            }

            # Post to publication if configured, else to user profile
            if self.publication_id:
                url = f"{MEDIUM_API}/publications/{self.publication_id}/posts"
            else:
                url = f"{MEDIUM_API}/users/{user_id}/posts"

            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            post_data = resp.json()["data"]

            logger.info(f"Medium post published: {post_data.get('url')}")
            return {
                "platform": "medium",
                "status": "published",
                "url": post_data.get("url"),
                "medium_id": post_data.get("id"),
            }

"""
PublisherRouter — routes content to the correct publishing integration.

Two distinct paths:
  draft()   — save + send review email (LinkedIn, Twitter, Facebook/Instagram)
  publish() — actually post to the platform (all five channels)

Auto-publishers (no review): Medium, Company Site
Draft-then-approve:           LinkedIn, Twitter, Facebook/Instagram
"""

import logging
from app.publishers.medium_publisher import MediumPublisher
from app.publishers.company_site_publisher import CompanySitePublisher
from app.publishers.draft_publisher import DraftPublisher
from app.publishers.linkedin_publisher import LinkedInPublisher
from app.publishers.twitter_publisher import TwitterPublisher
from app.publishers.facebook_instagram_publisher import FacebookInstagramPublisher

logger = logging.getLogger(__name__)


class PublisherRouter:
    def __init__(self):
        # Auto-publish channels
        self._auto = {
            "medium":       MediumPublisher(),
            "company_site": CompanySitePublisher(),
        }
        # Social channels — draft for review, then live on approval
        self._draft = {
            "linkedin":           DraftPublisher("linkedin"),
            "twitter":            DraftPublisher("twitter"),
            "facebook_instagram": DraftPublisher("facebook_instagram"),
        }
        self._live = {
            "linkedin":           LinkedInPublisher(),
            "twitter":            TwitterPublisher(),
            "facebook_instagram": FacebookInstagramPublisher(),
        }

    async def draft(self, platform: str, variants: dict, content_id: str, token_fn) -> dict:
        """Save as draft and send review email with one-click approve/reject links."""
        publisher = self._draft.get(platform)
        if not publisher:
            raise ValueError(f"No draft publisher for: {platform}")
        logger.info(f"[{content_id}] Sending draft for review: {platform}")
        return await publisher.publish(variants, content_id, token_fn)

    async def publish(self, platform: str, variants: dict, content_id: str) -> dict:
        """Publish live. Used for auto-channels and for approved social drafts."""
        publisher = self._auto.get(platform) or self._live.get(platform)
        if not publisher:
            raise ValueError(f"Unknown platform: {platform}")
        logger.info(f"[{content_id}] Publishing live to: {platform}")
        return await publisher.publish(variants, content_id)

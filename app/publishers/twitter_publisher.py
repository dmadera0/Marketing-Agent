"""
TwitterPublisher — publishes a Twitter/X thread via API v2.

The ContentAgent generates a numbered thread (1/ 2/ 3/ …).
This publisher splits the text into individual tweets and posts them
as a reply chain so they appear as a connected thread.

Required env vars:
  TWITTER_API_KEY             — Consumer key
  TWITTER_API_SECRET          — Consumer secret
  TWITTER_ACCESS_TOKEN        — OAuth 1.0a access token
  TWITTER_ACCESS_TOKEN_SECRET — OAuth 1.0a access token secret

Docs: https://developer.x.com/en/docs/x-api/tweets/manage-tweets/api-reference/post-tweets
"""

import os
import re
import time
import hmac
import hashlib
import base64
import urllib.parse
import logging
import httpx

logger = logging.getLogger(__name__)

TWITTER_API = "https://api.twitter.com/2/tweets"


class TwitterPublisher:
    def __init__(self):
        self.api_key              = os.environ.get("TWITTER_API_KEY", "")
        self.api_secret           = os.environ.get("TWITTER_API_SECRET", "")
        self.access_token         = os.environ.get("TWITTER_ACCESS_TOKEN", "")
        self.access_token_secret  = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", "")

    def _oauth_header(self, method: str, url: str, body_params: dict) -> str:
        """Build OAuth 1.0a Authorization header."""
        nonce     = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
        timestamp = str(int(time.time()))

        oauth_params = {
            "oauth_consumer_key":     self.api_key,
            "oauth_nonce":            nonce,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp":        timestamp,
            "oauth_token":            self.access_token,
            "oauth_version":          "1.0",
        }

        # Signature base string
        all_params = {**oauth_params, **body_params}
        sorted_params = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted(all_params.items())
        )
        base_string = "&".join([
            method.upper(),
            urllib.parse.quote(url, safe=""),
            urllib.parse.quote(sorted_params, safe=""),
        ])

        signing_key = (
            urllib.parse.quote(self.api_secret, safe="") + "&" +
            urllib.parse.quote(self.access_token_secret, safe="")
        )
        signature = base64.b64encode(
            hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
        ).decode()
        oauth_params["oauth_signature"] = signature

        header_parts = ", ".join(
            f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"'
            for k, v in sorted(oauth_params.items())
        )
        return f"OAuth {header_parts}"

    async def publish(self, variants: dict, content_id: str) -> dict:
        if not all([self.api_key, self.api_secret, self.access_token, self.access_token_secret]):
            logger.warning("Twitter credentials not set — skipping")
            return {"platform": "twitter", "status": "skipped", "reason": "missing credentials"}

        thread_text = variants.get("twitter", "")
        if not thread_text:
            logger.warning(f"[{content_id}] No Twitter variant found")
            return {"platform": "twitter", "status": "skipped", "reason": "no content"}

        tweets = self._split_thread(thread_text)
        if not tweets:
            return {"platform": "twitter", "status": "skipped", "reason": "no tweets parsed"}

        async with httpx.AsyncClient(timeout=30) as client:
            reply_to_id = None
            tweet_ids   = []

            for i, tweet in enumerate(tweets):
                payload = {"text": tweet}
                if reply_to_id:
                    payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}

                auth_header = self._oauth_header("POST", TWITTER_API, {})
                resp = await client.post(
                    TWITTER_API,
                    headers={
                        "Authorization": auth_header,
                        "Content-Type":  "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                tweet_id    = resp.json()["data"]["id"]
                reply_to_id = tweet_id
                tweet_ids.append(tweet_id)
                logger.info(f"[{content_id}] Tweet {i+1}/{len(tweets)} posted: {tweet_id}")

        first_id  = tweet_ids[0] if tweet_ids else ""
        thread_url = f"https://twitter.com/i/web/status/{first_id}" if first_id else ""
        logger.info(f"[{content_id}] Twitter thread published: {thread_url}")
        return {
            "platform":  "twitter",
            "status":    "published",
            "tweet_ids": tweet_ids,
            "url":       thread_url,
        }

    @staticmethod
    def _split_thread(text: str) -> list[str]:
        """
        Split thread text into individual tweets (≤280 chars each).
        Expects tweets numbered as  1/  2/  3/ … or separated by blank lines.
        """
        # Try numbered format first: lines starting with  N/
        numbered = re.split(r"\n(?=\d+\/)", text.strip())
        tweets = [t.strip() for t in numbered if t.strip()]

        # Fallback: split on double newlines
        if len(tweets) <= 1:
            tweets = [t.strip() for t in re.split(r"\n\s*\n", text.strip()) if t.strip()]

        # Hard-trim any tweet that still exceeds 280 chars
        trimmed = []
        for t in tweets:
            if len(t) <= 280:
                trimmed.append(t)
            else:
                # Split long tweet on sentence boundary
                sentences = re.split(r"(?<=\.)\s+", t)
                chunk = ""
                for s in sentences:
                    if len(chunk) + len(s) + 1 <= 277:
                        chunk = (chunk + " " + s).strip()
                    else:
                        if chunk:
                            trimmed.append(chunk)
                        chunk = s[:277] + "…"
                if chunk:
                    trimmed.append(chunk)
        return trimmed

"""
DraftPublisher — saves content as a draft and sends a review notification
with one-click Approve / Reject buttons.

Used for LinkedIn, Twitter/X, and Facebook/Instagram.
When approved via the /review link, the PublisherRouter routes to the
actual platform publisher.
"""

import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

PLATFORM_LABELS = {
    "linkedin":           "LinkedIn",
    "twitter":            "Twitter / X",
    "facebook_instagram": "Facebook & Instagram",
}


class DraftPublisher:
    def __init__(self, platform: str):
        self.platform = platform
        self.review_email = os.environ.get("REVIEW_EMAIL", "")
        self.smtp_host    = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port    = int(os.environ.get("SMTP_PORT", "587"))
        self.smtp_user    = os.environ.get("SMTP_USER", "")
        self.smtp_pass    = os.environ.get("SMTP_PASS", "")
        self.base_url     = os.environ.get("APP_BASE_URL", "http://localhost:8000")

    async def publish(self, variants: dict, content_id: str, token_fn=None) -> dict:
        """Save as draft and notify the reviewer with one-click action links."""
        label   = PLATFORM_LABELS.get(self.platform, self.platform)
        snippet = variants.get(self.platform, "")[:600]

        if self.review_email and token_fn:
            approve_token = token_fn(content_id, self.platform, "approve")
            reject_token  = token_fn(content_id, self.platform, "reject")
            self._send_review_email(content_id, label, snippet, approve_token, reject_token)
        elif self.review_email:
            logger.warning("token_fn not provided — sending email without one-click links")
            self._send_review_email(content_id, label, snippet, None, None)

        return {
            "platform":   self.platform,
            "status":     "pending_review",
            "content_id": content_id,
        }

    def _send_review_email(
        self,
        content_id: str,
        label: str,
        snippet: str,
        approve_token: str | None,
        reject_token: str | None,
    ):
        subject = f"[BuenaVista AI] {label} draft ready for review"
        base    = self.base_url

        if approve_token and reject_token:
            approve_url = (
                f"{base}/review?content_id={content_id}"
                f"&platform={self.platform}&action=approve&token={approve_token}"
            )
            reject_url = (
                f"{base}/review?content_id={content_id}"
                f"&platform={self.platform}&action=reject&token={reject_token}"
            )
            action_block = f"""
  <h3 style="color:#1a1a2e">Actions</h3>
  <table style="border-collapse:collapse">
    <tr>
      <td style="padding:0 12px 0 0">
        <a href="{approve_url}"
           style="display:inline-block;padding:12px 28px;background:#2e7d32;color:#fff;
                  text-decoration:none;border-radius:6px;font-weight:bold;font-size:15px">
          ✓ Approve &amp; Publish
        </a>
      </td>
      <td>
        <a href="{reject_url}"
           style="display:inline-block;padding:12px 28px;background:#c62828;color:#fff;
                  text-decoration:none;border-radius:6px;font-weight:bold;font-size:15px">
          ✗ Reject
        </a>
      </td>
    </tr>
  </table>
  <p style="color:#888;font-size:12px;margin-top:12px">
    To reject with written feedback and trigger a rewrite, use the API:<br>
    <code>POST {base}/approve</code> with
    <code>{{"content_id":"{content_id}","platform":"{self.platform}",
"action":"reject","feedback":"your notes here"}}</code>
  </p>"""
        else:
            action_block = f"""
  <h3>Actions (API)</h3>
  <pre style="background:#1a1a2e;color:#e0e0e0;padding:12px;border-radius:8px;font-size:12px">
curl -X POST {base}/approve \\
  -H "Content-Type: application/json" \\
  -d '{{"content_id":"{content_id}","platform":"{self.platform}","action":"approve"}}'
  </pre>"""

        html = f"""
<html><body style="font-family:Arial,sans-serif;max-width:620px;margin:auto;padding:20px">
  <h2 style="color:#1a1a2e">BuenaVista AI — Content Review</h2>
  <p>A new <strong>{label}</strong> draft is ready for your review.</p>
  <p style="color:#666;font-size:13px"><strong>Content ID:</strong> <code>{content_id}</code></p>

  <h3 style="color:#1a1a2e">Draft Preview</h3>
  <div style="background:#f5f5f5;padding:16px;border-radius:8px;
              white-space:pre-wrap;font-size:13px;line-height:1.6;
              border-left:4px solid #1565c0">{snippet}…</div>

  {action_block}

  <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
  <p style="color:#aaa;font-size:11px">BuenaVista AI Solutions — Content Engine</p>
</body></html>
"""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = self.smtp_user
            msg["To"]      = self.review_email
            msg.attach(MIMEText(html, "html"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.sendmail(self.smtp_user, self.review_email, msg.as_string())
            logger.info(f"Review email sent to {self.review_email} for {self.platform}")
        except Exception as e:
            logger.error(f"Failed to send review email: {e}")

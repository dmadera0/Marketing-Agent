"""
ContentAgent — calls Claude to generate all content variants
from a topic + sources in a single structured pass.
"""

import os
import json
import logging
import anthropic

logger = logging.getLogger(__name__)

BRAND_VOICE = """
You are the content strategist for BuenaVista AI Solutions, an AI agency that helps
businesses leverage artificial intelligence to streamline operations, boost growth,
and stay ahead of the curve.

Brand voice:
- Professional yet approachable — expert without being jargon-heavy
- Forward-thinking and optimistic about AI's practical benefits
- Story-driven: open with a hook, anchor ideas in real-world impact
- Never salesy. Educate first, inspire action second.
- Tagline: "Intelligent solutions. Real results."

Company info:
- Services: AI strategy consulting, custom AI integrations, automation workflows,
  LLM-powered products, data analytics
- Target audience: SMB owners, operations leaders, marketing directors,
  forward-thinking executives
- Location: Los Angeles, CA (but serves clients nationally)
"""

BLOG_TEMPLATE = """
Write a full SEO-optimised blog post with this structure:

# [Compelling H1 Title — include target keyword]

**Meta description (155 chars max):** [Write this first, clearly]

## Introduction (150–200 words)
Hook the reader with a surprising stat, bold claim, or relatable scenario.
Introduce the topic and promise what they'll learn.

## [H2 Section 1] (200–250 words)
## [H2 Section 2] (200–250 words)
## [H2 Section 3] (200–250 words)

## Key takeaways
- Bullet 1
- Bullet 2
- Bullet 3

## How BuenaVista AI Solutions can help (100 words)
Soft CTA — no hard sell. Invite them to learn more or book a free consultation.

---
Total target: 900–1200 words. Use markdown formatting throughout.
"""

SOCIAL_TEMPLATES = {
    "linkedin": """
Write a LinkedIn article post (600–800 words).
- Open with a bold single-sentence hook (no "I'm excited to share…")
- Use short paragraphs (2–3 sentences max)
- Include 3–5 practical insights
- End with a genuine discussion question
- Add 5 relevant hashtags at the bottom
- Tone: thought-leader, warm, direct
""",
    "twitter": """
Write a Twitter/X thread (8–12 tweets).
- Tweet 1: Punchy hook that makes people stop scrolling
- Tweets 2–10: One insight per tweet, numbered (2/ 3/ etc.)
- Final tweet: CTA — follow BuenaVista AI, link to blog
- Each tweet ≤ 280 characters
- Use line breaks for readability, no hashtag spam (max 2 per thread)
""",
    "facebook_instagram": """
Write TWO versions:

FACEBOOK POST (150–250 words):
- Conversational, story-driven
- Ask a question to drive comments
- Include a link preview placeholder: [LINK]
- 3 relevant hashtags

INSTAGRAM CAPTION (125–150 words + hashtags):
- Hook in first line (before "more" cutoff — under 125 chars)
- Emojis used sparingly but effectively
- End with a clear CTA (save this, visit bio link, comment below)
- 15–20 targeted hashtags in a block at the end
""",
}


class ContentAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = "claude-opus-4-6"

    async def generate(
        self,
        topic: str,
        sources: list[str],
        keyword: str | None,
        tone: str,
        extra: str | None,
    ) -> dict:
        """Generate blog + all social variants. Returns dict keyed by platform."""
        sources_text = "\n".join(f"- {s}" for s in sources) if sources else "No specific sources provided."
        kw_line = f"Primary SEO keyword: **{keyword}**" if keyword else ""
        extra_line = f"Additional instructions: {extra}" if extra else ""

        variants = {}

        # ── Blog post ──────────────────────────────────────────────────────
        logger.info(f"Generating blog post for: {topic}")
        blog_prompt = f"""
{BRAND_VOICE}

Topic: {topic}
{kw_line}
Sources / reference material:
{sources_text}
Tone override: {tone}
{extra_line}

{BLOG_TEMPLATE}
"""
        variants["blog"] = self._call(blog_prompt)

        # ── Social variants ────────────────────────────────────────────────
        blog_summary = variants["blog"][:2000]  # Feed context to social posts

        for platform, template in SOCIAL_TEMPLATES.items():
            logger.info(f"Generating {platform} variant")
            prompt = f"""
{BRAND_VOICE}

You are adapting a blog post for {platform}. Here is a summary of the blog:

---
{blog_summary}
---

Original topic: {topic}
{kw_line}
{extra_line}

{template}
"""
            variants[platform] = self._call(prompt)

        return variants

    async def regenerate_platform(
        self,
        platform: str,
        original: dict,
        feedback: str,
    ) -> str:
        """Regenerate a single platform variant based on reviewer feedback."""
        template = SOCIAL_TEMPLATES.get(platform, BLOG_TEMPLATE)
        prompt = f"""
{BRAND_VOICE}

Rewrite the following {platform} content based on this reviewer feedback:

FEEDBACK: {feedback}

ORIGINAL CONTENT:
{original.get(platform, '')}

BLOG CONTEXT:
{original.get('blog', '')[:1500]}

{template}

Incorporate the feedback while maintaining brand voice.
"""
        return self._call(prompt)

    def _call(self, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

"""
SEOAgent — enriches a blog post with SEO metadata,
readability analysis, and keyword optimisation suggestions.
"""

import os
import re
import logging
import anthropic

logger = logging.getLogger(__name__)


class SEOAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = "claude-opus-4-6"

    async def enrich(self, blog_content: str, keyword: str | None) -> str:
        """
        Analyse and enrich a blog post for SEO.
        Returns the enriched markdown string with an appended SEO report block.
        """
        kw_line = f"Primary keyword to optimise for: **{keyword}**" if keyword else "No specific keyword provided — suggest one."

        prompt = f"""
You are an expert SEO analyst. Analyse and improve this blog post for search engines.

{kw_line}

BLOG POST:
{blog_content}

Perform these tasks and return the FULL improved blog post followed by a JSON SEO report:

TASKS:
1. Ensure the primary keyword appears in: H1 title, first 100 words, at least 2 H2 subheadings, and naturally throughout (density 1–2%).
2. Improve the meta description if needed (max 155 chars, includes keyword, has a CTA hook).
3. Add internal link placeholders where relevant: [INTERNAL LINK: topic]
4. Suggest 3 related long-tail keywords in the SEO report.
5. Flag any readability issues (sentences over 25 words, passive voice overuse).
6. Suggest a URL slug.

Return format:
---BLOG---
[Full improved blog post in markdown]
---SEO_REPORT---
{{
  "slug": "...",
  "meta_description": "...",
  "primary_keyword": "...",
  "keyword_density": "...",
  "long_tail_keywords": ["...", "...", "..."],
  "readability_score": "Good/Fair/Needs work",
  "readability_notes": "...",
  "word_count": 0
}}
"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text

        # Parse out blog vs report
        if "---SEO_REPORT---" in raw:
            blog_part, seo_part = raw.split("---SEO_REPORT---", 1)
            blog_part = blog_part.replace("---BLOG---", "").strip()
            try:
                # Extract JSON block
                json_match = re.search(r"\{[\s\S]+\}", seo_part)
                if json_match:
                    import json
                    seo_data = json.loads(json_match.group())
                    logger.info(f"SEO report: slug={seo_data.get('slug')}, "
                                f"readability={seo_data.get('readability_score')}, "
                                f"words={seo_data.get('word_count')}")
                    # Append lightweight SEO block to content for storage
                    return blog_part + f"\n\n<!-- SEO: {json_match.group()} -->"
            except Exception as e:
                logger.warning(f"Could not parse SEO report JSON: {e}")
            return blog_part

        logger.warning("SEO enrichment response missing expected delimiters — returning as-is")
        return raw

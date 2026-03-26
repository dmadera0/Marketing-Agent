#!/usr/bin/env python3
"""
scheduler.py — Run this as a cron job or standalone process to automatically
trigger content generation on a schedule.

Cron example (3x per week, Monday/Wednesday/Friday at 9am PT):
  0 16 * * 1,3,5 /usr/bin/python3 /opt/buenavistaai/scripts/scheduler.py

Or run continuously with APScheduler (pip install apscheduler):
  python3 scheduler.py --daemon
"""

import os
import sys
import json
import logging
import argparse
import httpx
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8000")

# ── Content calendar ───────────────────────────────────────────────────────
# Add your planned topics here. The scheduler will work through them in order,
# cycling back to the start when the list is exhausted.
CONTENT_CALENDAR = [
    {
        "topic": "How small businesses can use AI to automate customer support in 2025",
        "target_keyword": "AI customer support automation",
        "sources": [
            "https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-state-of-ai",
        ],
        "extra_instructions": "Include a section on ROI and time-to-value for SMBs.",
    },
    {
        "topic": "5 AI tools that replace 10 hours of manual marketing work per week",
        "target_keyword": "AI marketing automation tools",
        "sources": [],
        "extra_instructions": "Focus on tools accessible to non-technical marketing teams.",
    },
    {
        "topic": "What is an AI agent and why every operations team needs one",
        "target_keyword": "AI agents for business operations",
        "sources": [],
        "extra_instructions": "Use plain language, avoid academic definitions.",
    },
    {
        "topic": "How to evaluate an AI vendor: 7 questions to ask before signing",
        "target_keyword": "how to choose an AI vendor",
        "sources": [],
        "extra_instructions": "Position BuenaVista as a trusted advisor in the CTA section.",
    },
    {
        "topic": "Generative AI in professional services: trends shaping 2025",
        "target_keyword": "generative AI professional services 2025",
        "sources": [],
        "extra_instructions": None,
    },
    {
        "topic": "Real-world ROI: 3 companies that saved 20+ hours per week with AI workflows",
        "target_keyword": "AI workflow automation ROI",
        "sources": [],
        "extra_instructions": "Use anonymised / composite case studies. Make them feel real.",
    },
]

CALENDAR_INDEX_FILE = Path(os.environ.get("CONTENT_STORE_DIR", "/data/content")) / ".calendar_index"


def get_next_topic() -> dict:
    """Return the next topic from the calendar, cycling through in order."""
    CALENDAR_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        idx = int(CALENDAR_INDEX_FILE.read_text().strip())
    except Exception:
        idx = 0

    topic = CONTENT_CALENDAR[idx % len(CONTENT_CALENDAR)]
    CALENDAR_INDEX_FILE.write_text(str((idx + 1) % len(CONTENT_CALENDAR)))
    return topic


def trigger_generation(topic_config: dict) -> dict:
    """POST to /generate and return the response."""
    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{BASE_URL}/generate", json=topic_config)
        resp.raise_for_status()
        return resp.json()


def run_once():
    topic_config = get_next_topic()
    logger.info(f"Triggering generation for: {topic_config['topic']}")
    try:
        result = trigger_generation(topic_config)
        logger.info(f"Generation queued. content_id={result.get('content_id')}")
        return result
    except Exception as e:
        logger.error(f"Failed to trigger generation: {e}")
        raise


def run_daemon():
    """Run as a long-lived process using APScheduler."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        logger.error("APScheduler not installed. Run: pip install apscheduler")
        sys.exit(1)

    scheduler = BlockingScheduler(timezone="America/Los_Angeles")

    # Mon / Wed / Fri at 9:00 AM PT
    scheduler.add_job(run_once, "cron", day_of_week="mon,wed,fri", hour=9, minute=0)

    logger.info("Scheduler started. Running Mon/Wed/Fri at 09:00 PT. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BuenaVista AI Content Scheduler")
    parser.add_argument("--daemon", action="store_true", help="Run as a long-lived scheduled process")
    parser.add_argument("--once", action="store_true", help="Trigger one generation run immediately")
    parser.add_argument("--topic", type=str, help="Override topic for a one-off run")
    parser.add_argument("--keyword", type=str, help="Override target keyword")
    args = parser.parse_args()

    if args.topic:
        config = {"topic": args.topic, "target_keyword": args.keyword, "sources": []}
        result = trigger_generation(config)
        print(json.dumps(result, indent=2))
    elif args.daemon:
        run_daemon()
    else:
        result = run_once()
        print(json.dumps(result, indent=2))

"""
ContentStore — lightweight file-based persistence.
In production this swaps out for DynamoDB / RDS with a one-line change.
"""

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

STORE_DIR = Path(os.environ.get("CONTENT_STORE_DIR", "/data/content"))


class ContentStore:
    def __init__(self):
        STORE_DIR.mkdir(parents=True, exist_ok=True)

    def _path(self, content_id: str) -> Path:
        return STORE_DIR / f"{content_id}.json"

    def save(self, content_id: str, data: dict):
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        if "created_at" not in data:
            data["created_at"] = data["updated_at"]
        with open(self._path(content_id), "w") as f:
            json.dump(data, f, indent=2)

    def get(self, content_id: str) -> dict | None:
        p = self._path(content_id)
        if not p.exists():
            return None
        with open(p) as f:
            return json.load(f)

    def update_status(self, content_id: str, platform: str, status: str, notes: str = ""):
        data = self.get(content_id) or {}
        if platform == "all":
            for k in data.get("platform_statuses", {}):
                data["platform_statuses"][k] = status
        else:
            data.setdefault("platform_statuses", {})[platform] = status
        if notes:
            data.setdefault("notes", {})[platform] = notes
        self.save(content_id, data)

    def list_by_status(self, status: str) -> list[dict]:
        results = []
        for p in STORE_DIR.glob("*.json"):
            try:
                with open(p) as f:
                    d = json.load(f)
                statuses = d.get("platform_statuses", {})
                if any(v == status for v in statuses.values()):
                    results.append({
                        "content_id": p.stem,
                        "topic": d.get("topic"),
                        "created_at": d.get("created_at"),
                        "platform_statuses": statuses,
                    })
            except Exception:
                pass
        return sorted(results, key=lambda x: x.get("created_at", ""), reverse=True)

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.config import AUDIT_LOG_PATH


def append_audit_event(event: Dict[str, Any]) -> None:
    """
    Append-only JSONL audit log for confidentiality + traceability.
    Each line is one JSON object.
    """
    os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)

    event_out = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        **event,
    }

    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event_out, ensure_ascii=False) + "\n")

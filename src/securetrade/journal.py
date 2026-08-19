from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections import deque
from typing import Any

from securetrade.models import JournalEntry


class DecisionJournal:
    """Immutable-style decision journal. Each entry hashes the previous one."""

    def __init__(self) -> None:
        self.entries: deque[JournalEntry] = deque(maxlen=500)
        self._last_hash = "0" * 64

    def record(
        self,
        action: str,
        opportunity_id: str,
        decision: str,
        sources: list[str],
        expected_profit: float,
        actual_result: float | None,
        risk_score: int,
        security_decision: str,
        details: dict[str, Any],
        ts: float | None = None,
    ) -> JournalEntry:
        payload = {
            "action": action,
            "opportunity_id": opportunity_id,
            "decision": decision,
            "sources": sources,
            "expected_profit": expected_profit,
            "actual_result": actual_result,
            "risk_score": risk_score,
            "security_decision": security_decision,
            "details": details,
            "prev": self._last_hash,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        entry = JournalEntry(
            id=uuid.uuid4().hex[:12],
            ts=ts or time.time(),
            action=action,
            opportunity_id=opportunity_id,
            decision=decision,
            sources=sources,
            expected_profit=expected_profit,
            actual_result=actual_result,
            risk_score=risk_score,
            security_decision=security_decision,
            details=details,
            hash=digest,
            prev_hash=self._last_hash,
        )
        self.entries.appendleft(entry)
        self._last_hash = digest
        return entry

    def verify_chain(self) -> bool:
        prev = "0" * 64
        for entry in reversed(list(self.entries)):
            payload = {
                "action": entry.action,
                "opportunity_id": entry.opportunity_id,
                "decision": entry.decision,
                "sources": entry.sources,
                "expected_profit": entry.expected_profit,
                "actual_result": entry.actual_result,
                "risk_score": entry.risk_score,
                "security_decision": entry.security_decision,
                "details": entry.details,
                "prev": prev,
            }
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
            if digest != entry.hash or entry.prev_hash != prev:
                return False
            prev = entry.hash
        return True

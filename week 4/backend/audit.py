"""
backend/audit.py
Append-only, hash-chained audit trail — one JSONL file per analysis.

Every event carries the hash of the event before it, so editing, deleting or
reordering any past line breaks verify(). That is what lets a reviewer show an
examiner *why* a transaction was flagged, by which rule version, which model
said what with what confidence, and what the human decided — after the fact.

Reviewer names are self-asserted in this demo; production would take them from SSO.
"""
import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64
DOC_ID_RE = re.compile(r"^[0-9a-f]{8}$")


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def valid_doc_id(doc_id: str) -> bool:
    return bool(DOC_ID_RE.match(doc_id or ""))


class AuditLog:
    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, doc_id: str) -> Path:
        # doc_id reaches the filesystem, so it must never be free-form.
        if not valid_doc_id(doc_id):
            raise ValueError(f"invalid document id: {doc_id!r}")
        return self.dir / f"{doc_id}.jsonl"

    def events(self, doc_id: str) -> list[dict]:
        path = self._path(doc_id)
        if not path.exists():
            return []
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def append(self, doc_id: str, event_type: str, payload: dict, actor: str = "system") -> dict:
        with self._lock:
            existing = self.events(doc_id)
            body = {
                "seq":       len(existing) + 1,
                "doc_id":    doc_id,
                "ts":        datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "type":      event_type,
                "actor":     actor,
                "payload":   payload,
                "prev_hash": existing[-1]["hash"] if existing else GENESIS,
            }
            event = {**body, "hash": sha256_text(canonical(body))}
            with open(self._path(doc_id), "a", encoding="utf-8") as f:
                f.write(canonical(event) + "\n")
            return event

    def verify(self, doc_id: str) -> dict:
        events = self.events(doc_id)
        prev = GENESIS
        for i, e in enumerate(events, start=1):
            body = {k: v for k, v in e.items() if k != "hash"}
            if e.get("seq") != i or e.get("prev_hash") != prev or sha256_text(canonical(body)) != e.get("hash"):
                return {"valid": False, "events": len(events), "broken_at": i, "head": None}
            prev = e["hash"]
        return {"valid": True, "events": len(events), "broken_at": None, "head": prev if events else None}

    def reviews(self, doc_id: str) -> dict:
        """Latest human decision per transaction id."""
        latest = {}
        for e in self.events(doc_id):
            if e["type"] == "human_review":
                latest[e["payload"]["txn_id"]] = {**e["payload"], "reviewer": e["actor"],
                                                  "ts": e["ts"], "event_hash": e["hash"]}
        return latest

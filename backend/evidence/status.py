"""Reviewer-facing OpenAlex progress, derived from recorded query outcomes."""
from typing import Any


def openalex_status(snapshot: dict | None, *, reused: bool = False) -> dict[str, Any]:
    if snapshot is None:
        return {"state": "unavailable", "reused": reused, "message": ("Reusing saved extraction; no new OpenAlex connection was made. " if reused else "") + "No OpenAlex search results were recorded. The research engine can continue its own search."}
    records = [q for q in snapshot.get("queries", []) if q.get("source") == "openalex"]
    completed = sum(not q.get("error") for q in records)
    failed = sum(bool(q.get("error")) for q in records)
    truncated = any(q.get("source") == "retrieval" and q.get("error") for q in snapshot.get("queries", []))
    matches = sum(q.get("returned", 0) for q in records if not q.get("error"))
    state = "partial" if completed and (failed or truncated) else "complete" if completed else "unavailable"
    message = (
        f"{completed} searches completed · {matches} matches before deduplication."
        if completed else "OpenAlex search did not complete. The research engine can continue its own search."
    )
    if failed or truncated:
        message += " Some source requests failed or exceeded the search time limit."
    if reused:
        message = "Reusing a saved OpenAlex snapshot; no new connection was made. " + message
    return {"state": state, "message": message, "reused": reused,
            "queries_completed": completed, "queries_failed": failed,
            "matches": matches, "retrieved_at": snapshot.get("retrieved_at", "")}

"""In-process pub/sub broker for live agent activity.

When an external agent (Claude Code, Codex, Copilot) drives the workbench via
the MCP server, the MCP server forwards each tool call to this backend's
``/api/agent/invoke-tool`` endpoint. That endpoint publishes activity events
here; the React UI subscribes via ``/api/agent-activity/stream`` (SSE) and
renders them live — e.g. the CAD build animation.

Design:
- One uvicorn worker process owns all UI subscribers, so a simple in-memory
  fan-out over thread-safe queues is sufficient. (If we ever scale to multiple
  workers we'll swap this for Redis pub/sub behind the same interface.)
- Publishers are sync (tool handlers run in worker threads via FastAPI's sync
  endpoint pool); subscribers are sync generators feeding StreamingResponse.
"""

from __future__ import annotations

import collections
import queue
import threading
import time
from typing import Any

# Bounded so a stalled browser tab can't grow memory without limit; on
# overflow we drop the oldest events for that subscriber rather than block
# the publisher (the agent's tool call must never hang on a slow UI).
_MAX_QUEUE = 1000

# Bounded ring buffer of recent events. Live subscribers (the web viewer) get a
# real-time fan-out, but a headless agent (#227) that wasn't subscribed when an
# event fired would otherwise see nothing — this lets `aieng.recent_activity`
# return the recent build/activity history for a project without the web UI.
_RECENT_MAX = 500

_subscribers: set["queue.Queue[dict[str, Any]]"] = set()
_recent: "collections.deque[dict[str, Any]]" = collections.deque(maxlen=_RECENT_MAX)
_lock = threading.Lock()


def subscribe() -> "queue.Queue[dict[str, Any]]":
    q: "queue.Queue[dict[str, Any]]" = queue.Queue(maxsize=_MAX_QUEUE)
    with _lock:
        _subscribers.add(q)
    return q


def unsubscribe(q: "queue.Queue[dict[str, Any]]") -> None:
    with _lock:
        _subscribers.discard(q)


def subscriber_count() -> int:
    with _lock:
        return len(_subscribers)


def publish(event: dict[str, Any]) -> None:
    """Fan out an event to every current subscriber.

    Never blocks: if a subscriber's queue is full, the oldest event is dropped
    to make room. A monotonic ``ts`` is stamped if absent so the UI can order
    events deterministically.
    """
    event.setdefault("ts", time.time())
    with _lock:
        subs = list(_subscribers)
        _recent.append(event)
    for q in subs:
        try:
            q.put_nowait(event)
        except queue.Full:
            try:
                q.get_nowait()  # drop oldest
                q.put_nowait(event)
            except queue.Empty:
                pass


def recent(
    project_id: str | None = None,
    *,
    limit: int = 50,
    since_ts: float | None = None,
) -> list[dict[str, Any]]:
    """Return recent activity events, newest last (chronological).

    Filters to ``project_id`` when given (events without a matching
    ``project_id`` are excluded from a project-scoped query). ``since_ts`` returns
    only events strictly newer than that monotonic ``ts`` (poll-for-new
    pagination); ``limit`` caps the result to the most recent N. Pure read.
    """
    capped = max(1, min(int(limit), _RECENT_MAX))
    with _lock:
        items = list(_recent)
    if project_id is not None:
        pid = str(project_id)
        items = [e for e in items if str(e.get("project_id") or "") == pid]
    if since_ts is not None:
        items = [e for e in items if float(e.get("ts") or 0.0) > float(since_ts)]
    return items[-capped:]


def reset() -> None:
    """Drop all subscribers and buffered events — test hook only."""
    with _lock:
        _subscribers.clear()
        _recent.clear()

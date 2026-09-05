"""FinGuard AI backend package (Week 3)."""
import sys

# The pipeline prints rupee signs and LLM-rewritten queries to stdout. On
# Windows that stream defaults to cp1252, which raises UnicodeEncodeError on
# characters like ₹ (U+20B9) and non-breaking hyphens (U+2011) — inside the
# SSE generator that surfaces as a bogus "analysis failed" event. Force UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass  # stream already detached or not reconfigurable

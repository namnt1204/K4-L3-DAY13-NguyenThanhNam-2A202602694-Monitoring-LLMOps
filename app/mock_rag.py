from __future__ import annotations

import time

from .incidents import STATE
from .tracing import get_langfuse_client, observe

CORPUS = {
    "refund": ["Refunds are available within 7 days with proof of purchase."],
    "monitoring": ["Metrics detect incidents, logs identify affected requests, traces localize the root cause."],
    "policy": ["Do not expose PII in logs. Use sanitized summaries only."],
}


@observe(name="retrieval", as_type="retriever", capture_input=False, capture_output=False)
def retrieve(message: str) -> list[str]:
    if STATE["tool_fail"]:
        get_langfuse_client().update_current_span(
            metadata={
                "tool_success": False,
                "error": "Vector store timeout",
            },
            level="ERROR",
            status_message="Vector store timeout",
        )
        raise RuntimeError("Vector store timeout")
    if STATE["rag_slow"]:
        time.sleep(2.5)
    lowered = message.lower()
    for key, docs in CORPUS.items():
        if key in lowered:
            get_langfuse_client().update_current_span(
                metadata={
                    "top_k": len(docs),
                    "document_count": len(docs),
                    "tool_success": True,
                }
            )
            return docs
    fallback_docs = ["No domain document matched. Use general fallback answer."]
    get_langfuse_client().update_current_span(
        metadata={
            "top_k": len(fallback_docs),
            "document_count": len(fallback_docs),
            "tool_success": True,
        }
    )
    return fallback_docs

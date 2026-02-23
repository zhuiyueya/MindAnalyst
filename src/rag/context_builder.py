from __future__ import annotations

from typing import List, Tuple

from src.rag.types import Citation, RagDoc


def build_context_and_citations(docs: List[RagDoc]) -> Tuple[str, List[Citation]]:
    context_parts: List[str] = []
    citations: List[Citation] = []

    for i, doc in enumerate(docs, start=1):
        tag = (doc.tag or "").strip() if doc.source_type == "summary_chunk" else ""

        prefix = f"[{i}]"
        if tag:
            prefix += f" [{tag}]"
        prefix += f" 《{doc.title}》"

        context_text = doc.text or ""
        context_parts.append(f"{prefix}: {context_text}")

        citations.append(
            Citation(
                index=i,
                rag_id=doc.rag_id,
                source_type=doc.source_type,
                summary_id=doc.summary_id,
                content_id=doc.content_id,
                title=doc.title,
                url=doc.url,
                tag=tag or None,
                text=context_text,
            )
        )

    return "\n\n".join(context_parts).strip(), citations

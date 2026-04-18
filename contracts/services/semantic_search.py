"""Lightweight semantic ranking helpers for clause search."""

from __future__ import annotations

import re
from typing import Iterable

from contracts.models import ClauseTemplate


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SYNONYM_GROUPS = (
    {"nda", "nondisclosure", "non", "disclosure", "confidentiality", "confidential", "secret"},
    {"indemnity", "indemnification", "liability", "damages"},
    {"privacy", "gdpr", "dpa", "data", "protection"},
    {"termination", "exit", "winddown", "expiry", "expiration"},
    {"governing", "law", "jurisdiction", "venue"},
)


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    return {token for token in _TOKEN_RE.findall(text.lower()) if token}


def _expand_tokens(tokens: set[str]) -> set[str]:
    if not tokens:
        return set()
    expanded = set(tokens)
    for group in _SYNONYM_GROUPS:
        if expanded.intersection(group):
            expanded.update(group)
    return expanded


def _field_tokens(clause: ClauseTemplate) -> tuple[set[str], set[str], set[str], set[str]]:
    title_tokens = _expand_tokens(_tokenize(clause.title or ""))
    tags_tokens = _expand_tokens(_tokenize(clause.tags or ""))
    content_tokens = _expand_tokens(_tokenize(clause.content or ""))
    fallback_tokens = _expand_tokens(_tokenize((clause.fallback_content or "") + " " + (clause.playbook_notes or "")))
    return title_tokens, tags_tokens, content_tokens, fallback_tokens


def _semantic_score(clause: ClauseTemplate, query_tokens: set[str], query_text: str) -> float:
    if not query_tokens:
        return 0.0

    title_tokens, tags_tokens, content_tokens, fallback_tokens = _field_tokens(clause)
    weighted_overlap = (
        3.0 * len(query_tokens.intersection(title_tokens))
        + 2.0 * len(query_tokens.intersection(tags_tokens))
        + 1.0 * len(query_tokens.intersection(content_tokens))
        + 1.0 * len(query_tokens.intersection(fallback_tokens))
    )
    max_weight = 7.0 * max(len(query_tokens), 1)
    base_score = weighted_overlap / max_weight

    query_text_normalized = (query_text or "").strip().lower()
    if query_text_normalized:
        if query_text_normalized in (clause.title or "").lower():
            base_score += 0.35
        elif query_text_normalized in (clause.content or "").lower():
            base_score += 0.2

    return base_score


def rank_clause_templates_semantic(
    clauses: Iterable[ClauseTemplate],
    query: str,
    *,
    limit: int = 10,
    min_score: float = 0.1,
) -> list[ClauseTemplate]:
    query_tokens = _expand_tokens(_tokenize(query))
    scored: list[tuple[float, ClauseTemplate]] = []
    for clause in clauses:
        score = _semantic_score(clause, query_tokens, query)
        if score >= min_score:
            scored.append((score, clause))

    scored.sort(key=lambda entry: (-entry[0], -(entry[1].updated_at.timestamp() if entry[1].updated_at else 0), entry[1].pk))
    return [entry[1] for entry in scored[:limit]]

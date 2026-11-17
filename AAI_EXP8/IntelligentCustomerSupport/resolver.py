"""
resolver.py
Evidence-grounded resolution engine.

Two retrieval strategies compared:
  1. Baseline  – keyword overlap (professor's original approach)
  2. Improved  – TF-IDF + cosine similarity (our upgrade)

Returns a ResolutionResult with:
  - matched article(s) and scores
  - proposed response draft
  - numeric confidence score [0.0 – 1.0]
  - retrieval method used
  - list of matched terms (for transparency)
"""

from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ArticleMatch:
    article_id: str
    title: str
    score: float          # 0.0 – 1.0
    matched_terms: list[str]
    content: str


@dataclass
class ResolutionResult:
    query_id: str
    top_match: Optional[ArticleMatch]
    all_matches: list[ArticleMatch]
    proposed_response: str
    confidence_score: float       # 0.0 – 1.0
    retrieval_method: str         # "tfidf" or "keyword"
    has_knowledge: bool
    baseline_score: float = 0.0   # for comparison experiments


# ---------------------------------------------------------------------------
# Knowledge base loader (cached after first load)
# ---------------------------------------------------------------------------

_kb_cache: Optional[list[dict]] = None


def _load_kb(kb_path: str = "knowledge_base.json") -> list[dict]:
    global _kb_cache
    if _kb_cache is None:
        with open(kb_path, encoding="utf-8") as f:
            data = json.load(f)
        _kb_cache = [a for a in data["articles"] if a.get("approved", True)]
    return _kb_cache


# ---------------------------------------------------------------------------
# TF-IDF retrieval (improved method)
# ---------------------------------------------------------------------------

def _tfidf_retrieve(query_text: str, articles: list[dict], top_n: int = 3) -> list[ArticleMatch]:
    """
    Vectorise all article content + tags, then rank by cosine similarity
    against the query.  Works even when the customer's wording differs
    from the article vocabulary.
    """
    # Build corpus: title + tags + content for each article
    corpus = []
    for a in articles:
        tags_str = " ".join(a.get("tags", []))
        doc = f"{a['title']} {tags_str} {a['content']}"
        corpus.append(doc)

    # Add the query as the last document
    corpus.append(query_text)

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
    )
    tfidf_matrix = vectorizer.fit_transform(corpus)
    query_vector = tfidf_matrix[-1]
    article_matrix = tfidf_matrix[:-1]

    similarities = cosine_similarity(query_vector, article_matrix).flatten()
    feature_names = vectorizer.get_feature_names_out()

    results: list[ArticleMatch] = []
    top_indices = np.argsort(similarities)[::-1][:top_n]

    for idx in top_indices:
        score = float(similarities[idx])
        if score < 0.01:
            continue
        # Extract which terms contributed (non-zero in both query and article)
        q_vec = query_vector.toarray().flatten()
        a_vec = article_matrix[idx].toarray().flatten()
        shared_indices = np.where((q_vec > 0) & (a_vec > 0))[0]
        matched_terms = [feature_names[i] for i in shared_indices[:8]]

        results.append(ArticleMatch(
            article_id=articles[idx]["id"],
            title=articles[idx]["title"],
            score=round(score, 4),
            matched_terms=matched_terms,
            content=articles[idx]["content"],
        ))

    return results


# ---------------------------------------------------------------------------
# Baseline keyword retrieval (professor's approach, kept for comparison)
# ---------------------------------------------------------------------------

def _keyword_retrieve(query_text: str, articles: list[dict]) -> list[ArticleMatch]:
    """
    Simple keyword overlap ratio: matched_keywords / total_article_keywords.
    This is the baseline the experiment improves upon.
    """
    query_words = set(re.findall(r"\w+", query_text.lower()))
    results: list[ArticleMatch] = []

    for a in articles:
        article_keywords = set(
            word for tag in a.get("tags", [])
            for word in re.findall(r"\w+", tag.lower())
        )
        if not article_keywords:
            continue
        matched = query_words & article_keywords
        score = len(matched) / len(article_keywords)
        if score > 0:
            results.append(ArticleMatch(
                article_id=a["id"],
                title=a["title"],
                score=round(score, 4),
                matched_terms=list(matched)[:8],
                content=a["content"],
            ))

    results.sort(key=lambda x: x.score, reverse=True)
    return results[:3]


# ---------------------------------------------------------------------------
# Response drafter
# ---------------------------------------------------------------------------

def _draft_response(query_text: str, match: ArticleMatch) -> str:
    """
    Draft a response grounded exclusively in the approved article content.
    No invented facts.
    """
    return (
        f"Thank you for reaching out.\n\n"
        f"Based on our approved knowledge base article \"{match.title}\", "
        f"here is the information relevant to your query:\n\n"
        f"{match.content}\n\n"
        f"If this does not fully resolve your issue, a support agent "
        f"will follow up with you shortly.\n\n"
        f"[Reference: {match.article_id} | Confidence: {match.score:.0%}]"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve(
    query_id: str,
    query_text: str,
    kb_path: str = "knowledge_base.json",
    method: str = "tfidf",
) -> ResolutionResult:
    """
    Retrieve relevant articles and propose a grounded response.

    Args:
        query_id:   The query identifier for logging.
        query_text: Raw customer query text.
        kb_path:    Path to knowledge_base.json.
        method:     "tfidf" (improved) or "keyword" (baseline).

    Returns:
        ResolutionResult
    """
    articles = _load_kb(kb_path)

    # ── Improved retrieval ─────────────────────────────────────────────────
    tfidf_matches = _tfidf_retrieve(query_text, articles)

    # ── Baseline retrieval (always run for comparison) ─────────────────────
    keyword_matches = _keyword_retrieve(query_text, articles)
    baseline_score = keyword_matches[0].score if keyword_matches else 0.0

    # ── Select working method ──────────────────────────────────────────────
    if method == "tfidf":
        matches = tfidf_matches
    else:
        matches = keyword_matches

    top = matches[0] if matches else None
    confidence = top.score if top else 0.0
    has_knowledge = confidence > 0.05

    proposed = (
        _draft_response(query_text, top)
        if has_knowledge
        else (
            "We were unable to find an approved answer to your query in our "
            "knowledge base. A support agent will review your request and "
            "respond within the SLA timeframe."
        )
    )

    return ResolutionResult(
        query_id=query_id,
        top_match=top,
        all_matches=matches,
        proposed_response=proposed,
        confidence_score=round(confidence, 4),
        retrieval_method=method,
        has_knowledge=has_knowledge,
        baseline_score=baseline_score,
    )

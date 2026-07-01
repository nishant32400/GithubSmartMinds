"""Deterministic heuristic ranking based on keyword overlap and reach.

This module is the fast, free, always-available baseline. The LLM agent uses
it to pre-filter candidates before deeper evaluation, and falls back to it
entirely when no LLM provider is configured.
"""
import math

import utils


def score_profile(profile, query_keywords):
    """Score a single profile against a set of query keywords.

    Returns ``(score, matched_keywords)``. Followers use a log scale so a few
    very-high-follower accounts cannot dominate purely on popularity.
    """
    skills = {s.lower() for s in profile.get('skills', [])}
    bio = (profile.get('bio') or '').lower()
    repo_text = ' '.join(
        ((r.get('description') or '') + ' ' + (r.get('name') or ''))
        for r in profile.get('repos', [])
    ).lower()

    matched_keywords = sorted(k for k in query_keywords if k in skills)
    skill_matches = len(matched_keywords)
    bio_matches = sum(1 for k in query_keywords if k in bio)
    repo_matches = sum(1 for k in query_keywords if k in repo_text)
    followers = max(0, profile.get('followers') or 0)

    score = (
        skill_matches * 3.0
        + repo_matches * 1.5
        + bio_matches * 1.0
        + math.log10(1 + followers) * 0.5
    )
    return round(score, 2), matched_keywords


def rank_candidates(profiles, query, top_n=10):
    """Rank profiles by heuristic score, highest first, capped at ``top_n``."""
    query_keywords = set(utils.extract_keywords(query))
    scored = []
    for p in profiles:
        score, matched = score_profile(p, query_keywords)
        enriched = dict(p)
        enriched['score'] = score
        enriched['heuristic_score'] = score
        enriched['matched_keywords'] = matched
        scored.append(enriched)
    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored[:max(0, top_n)]

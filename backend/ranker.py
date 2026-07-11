"""Deterministic heuristic ranking based on keyword overlap and reach.

This module is the fast, free, always-available baseline. The LLM agent uses
it to pre-filter candidates before deeper evaluation, and falls back to it
entirely when no LLM provider is configured.
"""
import math

import utils


def score_profile(profile, query_keywords):
    """Score a single profile against a set of query keywords.

    Returns ``(score, matched_keywords)``. Reach signals (followers, repo stars
    and forks) use a log scale so a few very-popular accounts cannot dominate
    purely on popularity, while still rewarding demonstrable impact.
    """
    repos = profile.get('repos', [])
    skills = {s.lower() for s in profile.get('skills', [])}
    bio = (profile.get('bio') or '').lower()
    repo_text = ' '.join(
        ((r.get('description') or '') + ' ' + (r.get('name') or ''))
        for r in repos
    ).lower()

    matched_keywords = sorted(k for k in query_keywords if k in skills)
    skill_matches = len(matched_keywords)
    bio_matches = sum(1 for k in query_keywords if k in bio)
    repo_matches = sum(1 for k in query_keywords if k in repo_text)
    followers = max(0, profile.get('followers') or 0)
    public_repos = max(0, profile.get('public_repos') or 0)
    total_stars = sum(max(0, r.get('stargazers_count') or 0) for r in repos)
    total_forks = sum(max(0, r.get('forks_count') or 0) for r in repos)

    score = (
        skill_matches * 3.0
        + repo_matches * 1.5
        + bio_matches * 1.0
        + math.log10(1 + followers) * 0.8
        + math.log10(1 + public_repos) * 0.5
        + math.log10(1 + total_stars) * 1.5
        + math.log10(1 + total_forks) * 0.7
    )
    return round(score, 2), matched_keywords


def rank_candidates(profiles, query, top_n=10):
    """Rank profiles by heuristic score, highest first, capped at ``top_n``."""
    query_keywords = set(utils.extract_keywords(query))
    scored = []
    for p in profiles:
        score, matched = score_profile(p, query_keywords)
        repos = p.get('repos', [])
        enriched = dict(p)
        enriched['score'] = score
        enriched['heuristic_score'] = score
        enriched['matched_keywords'] = matched
        enriched['total_stars'] = sum(max(0, r.get('stargazers_count') or 0) for r in repos)
        enriched['total_forks'] = sum(max(0, r.get('forks_count') or 0) for r in repos)
        scored.append(enriched)
    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored[:max(0, top_n)]

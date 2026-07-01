"""LLM-powered GitHub talent-hunt agent.

Pipeline (each stage degrades gracefully if the LLM is unavailable):

    1. PLAN   - turn a natural-language job description into a focused GitHub
                user-search query + a structured skill list.
    2. SEARCH - fetch candidate usernames from the GitHub Search API.
    3. ENRICH - build full profiles (user + repos) in parallel.
    4. RANK   - heuristic pre-filter (fast, free) then deep LLM evaluation of
                the most promising candidates, blending both signals.

When ``LLM_PROVIDER=none`` (or the provider errors), every stage falls back to
the deterministic heuristic so the product still works end-to-end.
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import utils
from config import config
from llm import LLMUnavailable, get_llm_client
from ranker import rank_candidates, score_profile
from scrapers.github_scraper import GitHubError, GitHubScraper

logger = logging.getLogger(__name__)

_PLAN_SYSTEM = (
    "You are a technical sourcing assistant. Convert a hiring manager's job "
    "description into a GitHub user-search strategy. Reply ONLY with JSON."
)

_EVAL_SYSTEM = (
    "You are an expert technical recruiter evaluating a GitHub user's public "
    "profile against a role. Be concise, evidence-based, and avoid speculation "
    "about protected attributes. Reply ONLY with JSON."
)


class TalentHuntAgent:
    def __init__(self, scraper=None, llm=None):
        self.scraper = scraper or GitHubScraper()
        self.llm = llm or get_llm_client()

    # -- public entry point -----------------------------------------------
    def hunt(self, requirements, location="", search_size=100, top_n=10, max_workers=None):
        """Run the full pipeline and return a structured result dict."""
        requirements = (requirements or "").strip()
        if not requirements:
            raise ValueError("requirements must not be empty")

        plan = self.plan_search(requirements, location)
        users = self.scraper.search_users(plan["github_query"], max_results=search_size)
        profiles = self._build_profiles(users, max_workers)

        # Heuristic pre-rank over the whole pool (cheap), then deep-eval the top.
        ranking_text = requirements + " " + " ".join(plan.get("skills", []))
        prelim = rank_candidates(profiles, ranking_text, top_n=len(profiles))
        candidates = self._evaluate(prelim, requirements, plan, top_n)

        return {
            "plan": plan,
            "llm_enabled": self.llm.is_available(),
            "llm_model": self.llm.model_name if self.llm.is_available() else None,
            "scanned": len(profiles),
            "count": len(candidates),
            "candidates": candidates,
        }

    # -- stage 1: plan -----------------------------------------------------
    def plan_search(self, requirements, location=""):
        """Produce ``{github_query, skills, keywords, rationale}``."""
        if self.llm.is_available():
            try:
                return self._plan_with_llm(requirements, location)
            except LLMUnavailable as exc:
                logger.info("Planning fell back to heuristic: %s", exc)
        return self._plan_heuristic(requirements, location)

    def _plan_with_llm(self, requirements, location):
        user_prompt = (
            "Job description:\n"
            f"{requirements}\n\n"
            f"Preferred location (optional): {location or 'any'}\n\n"
            "Return JSON with this exact shape:\n"
            "{\n"
            '  "github_query": "<GitHub user-search query>",\n'
            '  "skills": ["canonical", "skills"],\n'
            '  "keywords": ["free", "text", "terms"],\n'
            '  "rationale": "<one sentence on the strategy>"\n'
            "}\n\n"
            "Rules for github_query: use at most 3 strong free-text terms plus "
            "qualifiers such as language:, location:, followers:>=N, repos:>=N. "
            "Do NOT include type:user (it is added automatically). Keep it focused "
            "so the search returns real people, not zero results."
        )
        data = self.llm.complete_json(_PLAN_SYSTEM, user_prompt)
        query = (data.get("github_query") or "").strip()
        if not query:
            raise LLMUnavailable("empty github_query from LLM")
        plan = {
            "github_query": self._finalize_query(query, location),
            "skills": _as_str_list(data.get("skills")) or utils.detect_known_skills(requirements),
            "keywords": _as_str_list(data.get("keywords")) or utils.extract_keywords(requirements),
            "rationale": (data.get("rationale") or "LLM-generated search strategy.").strip(),
            "source": "llm",
        }
        return plan

    def _plan_heuristic(self, requirements, location):
        keywords = utils.extract_keywords(requirements)
        skills = utils.detect_known_skills(requirements)
        # Prefer detected skills as the strongest free-text terms.
        terms = (skills or keywords)[:3]
        query = " ".join(terms) if terms else requirements[:80]
        return {
            "github_query": self._finalize_query(query, location),
            "skills": skills,
            "keywords": keywords,
            "rationale": "Heuristic keyword extraction (LLM disabled).",
            "source": "heuristic",
        }

    @staticmethod
    def _finalize_query(query, location):
        """Ensure location + type:user qualifiers are present exactly once."""
        q = query.strip()
        if location and "location:" not in q.lower():
            loc = location.strip()
            q = f'{q} location:"{loc}"' if " " in loc else f"{q} location:{loc}"
        if "type:user" not in q.lower():
            q = f"{q} type:user"
        return q.strip()

    # -- stage 3: enrich ---------------------------------------------------
    def _build_profiles(self, users, max_workers=None):
        workers = max(1, min(max_workers or config.SCRAPER_MAX_WORKERS, len(users) or 1))
        profiles = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(self.scraper.build_profile, u): u for u in users}
            for fut in as_completed(futures):
                username = futures[fut]
                try:
                    profiles.append(fut.result())
                except GitHubError as exc:
                    logger.info("Skipping %s: %s", username, exc)
                except Exception as exc:  # never let one profile crash the run
                    logger.warning("Unexpected error building %s: %s", username, exc)
        return profiles

    # -- stage 4: evaluate -------------------------------------------------
    def _evaluate(self, prelim, requirements, plan, top_n):
        if not prelim:
            return []
        top_n = max(1, top_n)
        eval_count = min(len(prelim), max(top_n, config.LLM_EVAL_TOP_K))
        to_eval = prelim[:eval_count]
        max_heuristic = max((c.get("heuristic_score", 0) for c in to_eval), default=0) or 1

        if self.llm.is_available():
            self._evaluate_with_llm(to_eval, requirements, plan, max_heuristic)
        else:
            for c in to_eval:
                self._apply_heuristic_summary(c, max_heuristic)

        to_eval.sort(key=lambda c: c.get("score", 0), reverse=True)
        return to_eval[:top_n]

    def _evaluate_with_llm(self, candidates, requirements, plan, max_heuristic):
        workers = max(1, min(4, len(candidates)))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(self._eval_one, c, requirements, plan, max_heuristic): c
                for c in candidates
            }
            for fut in as_completed(futures):
                candidate = futures[fut]
                try:
                    fut.result()
                except Exception as exc:  # fall back per-candidate
                    logger.info("LLM eval failed for %s: %s",
                                candidate.get("username"), exc)
                    self._apply_heuristic_summary(candidate, max_heuristic)

    def _eval_one(self, candidate, requirements, plan, max_heuristic):
        summary = _compact_candidate(candidate)
        user_prompt = (
            f"Role requirements:\n{requirements}\n\n"
            f"Must-have skills: {', '.join(plan.get('skills', [])) or 'n/a'}\n\n"
            f"Candidate (JSON):\n{json.dumps(summary, ensure_ascii=False)}\n\n"
            "Return JSON: {\n"
            '  "fit_score": <integer 0-100>,\n'
            '  "matched_skills": ["..."],\n'
            '  "missing_skills": ["..."],\n'
            '  "summary": "<<=2 sentences on fit, citing repos/skills>"\n'
            "}"
        )
        data = self.llm.complete_json(_EVAL_SYSTEM, user_prompt)
        llm_score = _clamp_int(data.get("fit_score"), 0, 100, default=0)
        heuristic_norm = 100.0 * candidate.get("heuristic_score", 0) / max_heuristic
        combined = round(0.75 * llm_score + 0.25 * heuristic_norm, 2)

        candidate["llm_score"] = llm_score
        candidate["matched_skills"] = _as_str_list(data.get("matched_skills")) or candidate.get("matched_keywords", [])
        candidate["missing_skills"] = _as_str_list(data.get("missing_skills"))
        candidate["fit_summary"] = (data.get("summary") or "").strip() or "Evaluated by LLM."
        candidate["evaluated_by"] = "llm"
        candidate["score"] = combined
        return candidate

    @staticmethod
    def _apply_heuristic_summary(candidate, max_heuristic):
        matched = candidate.get("matched_keywords", [])
        candidate["llm_score"] = None
        candidate["matched_skills"] = matched
        candidate["missing_skills"] = []
        candidate["evaluated_by"] = "heuristic"
        candidate["score"] = round(100.0 * candidate.get("heuristic_score", 0) / max_heuristic, 2)
        if matched:
            candidate["fit_summary"] = "Strong keyword overlap on " + ", ".join(matched[:5]) + "."
        else:
            candidate["fit_summary"] = "Limited keyword overlap with the role requirements."


# -- module helpers --------------------------------------------------------
def _compact_candidate(profile, max_repos=8):
    """Trim a profile to the few fields the LLM needs (controls token cost)."""
    repos = []
    for r in (profile.get("repos") or [])[:max_repos]:
        repos.append({
            "name": r.get("name"),
            "language": r.get("language"),
            "stars": r.get("stargazers_count", 0),
            "description": (r.get("description") or "")[:160],
        })
    return {
        "username": profile.get("username"),
        "name": profile.get("name"),
        "bio": profile.get("bio"),
        "location": profile.get("location"),
        "followers": profile.get("followers"),
        "public_repos": profile.get("public_repos"),
        "skills": profile.get("skills", []),
        "repos": repos,
    }


def _as_str_list(value):
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _clamp_int(value, low, high, default=0):
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))

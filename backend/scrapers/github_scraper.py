import logging
import os
import time

import requests

try:  # Allow use both as a package (app/main) and standalone.
    from config import config
except ImportError:  # pragma: no cover - fallback if config import path differs
    config = None

import utils

logger = logging.getLogger(__name__)


class GitHubError(Exception):
    """Base error with a message that is safe to surface to API clients."""


class GitHubAuthError(GitHubError):
    """Invalid or missing credentials (HTTP 401)."""


class GitHubRateLimitError(GitHubError):
    """Primary or secondary rate limit hit (HTTP 403/429)."""


class GitHubNotFoundError(GitHubError):
    """Requested resource does not exist (HTTP 404)."""


class GitHubScraper:
    BASE = "https://api.github.com"

    def __init__(self, token=None, per_page=30, timeout=15, max_retries=3):
        token = token or (config.GITHUB_TOKEN if config else os.getenv('GITHUB_TOKEN'))
        self.token = token
        self.per_page = min(per_page, 100)
        self.timeout = timeout
        self.max_retries = max(1, max_retries)
        self.session = requests.Session()
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'github-talent-hunt-agent/2.0',
        }
        if token:
            headers['Authorization'] = f'token {token}'
        else:
            logger.warning('No GITHUB_TOKEN set; anonymous GitHub limit is 60 requests/hour.')
        self.session.headers.update(headers)

    def _get(self, url, params=None):
        """GET with bounded retries and typed, sanitized error handling.

        Upstream response bodies are logged server-side but never raised to the
        caller, to avoid leaking GitHub internals to a public API client.
        """
        backoff = 1.0
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning('GitHub request error (attempt %s/%s): %s',
                               attempt, self.max_retries, exc)
                if attempt == self.max_retries:
                    raise GitHubError('Could not reach GitHub. Please try again later.') from exc
                time.sleep(backoff)
                backoff *= 2
                continue

            status = resp.status_code
            if status == 200:
                return resp.json()
            if status == 401:
                raise GitHubAuthError('GitHub authentication failed. Check the configured token.')
            if status == 404:
                raise GitHubNotFoundError('GitHub resource not found.')
            if status in (403, 429):
                remaining = resp.headers.get('X-RateLimit-Remaining')
                retry_after = self._retry_delay(resp)
                logger.warning('GitHub %s rate/abuse limit (remaining=%s, retry_after=%ss): %s',
                               status, remaining, retry_after, resp.text[:200])
                if retry_after is not None and retry_after <= 5 and attempt < self.max_retries:
                    time.sleep(retry_after)
                    continue
                raise GitHubRateLimitError(
                    'GitHub API rate limit reached. Add a GITHUB_TOKEN or retry later.'
                )
            if 500 <= status < 600:
                logger.warning('GitHub server error %s (attempt %s/%s)',
                               status, attempt, self.max_retries)
                if attempt == self.max_retries:
                    raise GitHubError('GitHub is temporarily unavailable. Please try again later.')
                time.sleep(backoff)
                backoff *= 2
                continue

            # Any other unexpected status.
            logger.warning('Unexpected GitHub status %s: %s', status, resp.text[:200])
            raise GitHubError('Unexpected response from GitHub.')

        # Should be unreachable, but be explicit.
        raise GitHubError('Could not reach GitHub.') from last_exc

    @staticmethod
    def _retry_delay(resp):
        """Best-effort retry delay (seconds) from GitHub rate-limit headers."""
        retry_after = resp.headers.get('Retry-After')
        if retry_after:
            try:
                return max(0, int(retry_after))
            except ValueError:
                return None
        reset = resp.headers.get('X-RateLimit-Reset')
        if reset:
            try:
                return max(0, int(reset) - int(time.time()))
            except ValueError:
                return None
        return None

    def search_users(self, query, max_results=100):
        # GitHub's Search API exposes at most 1000 results per query.
        max_results = max(1, min(max_results, 1000))
        users = []
        page = 1
        per_page = self.per_page or 30
        while len(users) < max_results:
            params = {'q': query, 'per_page': per_page, 'page': page}
            url = f"{self.BASE}/search/users"
            data = self._get(url, params=params)
            items = data.get('items', [])
            if not items:
                break
            for it in items:
                users.append(it.get('login'))
                if len(users) >= max_results:
                    break
            if len(items) < per_page:
                break
            page += 1
            time.sleep(0.1)
        return users

    def build_profile(self, username, fetch_readme=False, max_repos=None):
        if max_repos is None:
            max_repos = config.MAX_REPOS_PER_USER if config else 20
        user = self._get(f"{self.BASE}/users/{username}")
        repos = []
        page = 1
        per_page = 100
        collected = 0
        while True:
            params = {'per_page': per_page, 'page': page, 'sort': 'pushed'}
            repo_page = self._get(f"{self.BASE}/users/{username}/repos", params=params)
            if not repo_page:
                break
            for r in repo_page:
                repos.append({
                    'name': r.get('name'),
                    'description': r.get('description'),
                    'language': r.get('language'),
                    'html_url': r.get('html_url'),
                    'stargazers_count': r.get('stargazers_count', 0),
                    'forks_count': r.get('forks_count', 0),
                    'created_at': r.get('created_at'),
                    'updated_at': r.get('updated_at')
                })
                collected += 1
                if max_repos and collected >= max_repos:
                    break
            if max_repos and collected >= max_repos:
                break
            if len(repo_page) < per_page:
                break
            page += 1
            time.sleep(0.05)

        lang_counts = {}
        text_corpus = []
        for r in repos:
            lang = r.get('language')
            if lang:
                lang_counts[lang.lower()] = lang_counts.get(lang.lower(), 0) + 1
            text_corpus.append(' '.join(filter(None, [r.get('name') or '', r.get('description') or '', r.get('language') or ''])))
        bio = user.get('bio') or ''
        text_corpus.append(bio)

        skills_detected = utils.detect_known_skills(' '.join(text_corpus))
        top_langs = sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)
        for lang, _ in top_langs[:5]:
            l = (lang or '').lower()
            if l and l not in skills_detected:
                skills_detected.append(l)

        profile = {
            'username': user.get('login'),
            'name': user.get('name'),
            'bio': user.get('bio'),
            'location': user.get('location'),
            'company': user.get('company'),
            'blog': user.get('blog'),
            'email': user.get('email'),
            'followers': user.get('followers'),
            'public_repos': user.get('public_repos'),
            'created_at': user.get('created_at'),
            'avatar_url': user.get('avatar_url'),
            'html_url': user.get('html_url'),
            'skills': skills_detected,
            'repos': repos
        }
        return profile

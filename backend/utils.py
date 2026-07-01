"""Text utilities: keyword extraction and robust skill detection.

The previous implementation matched skills with naive substring checks, so
``c`` matched inside ``react`` and ``ai`` inside ``email``. This version
tokenizes text on word-like boundaries (while preserving ``+ # .`` so that
``c++``, ``c#`` and ``node.js`` survive) and matches against an alias map.
"""
import re

STOPWORDS = frozenset([
    'and', 'or', 'the', 'a', 'an', 'for', 'to', 'in', 'on', 'with', 'by', 'of',
    'is', 'are', 'as', 'be', 'has', 'have', 'that', 'this', 'we', 'our', 'you',
])

# Canonical skill -> surface forms that may appear as tokens in real text.
SKILL_ALIASES = {
    'python': {'python', 'py'},
    'javascript': {'javascript', 'js'},
    'typescript': {'typescript', 'ts'},
    'java': {'java'},
    'go': {'go', 'golang'},
    'ruby': {'ruby'},
    'c++': {'c++', 'cpp'},
    'c#': {'c#', 'csharp'},
    'c': {'c'},
    'rust': {'rust'},
    'php': {'php'},
    'scala': {'scala'},
    'kotlin': {'kotlin'},
    'swift': {'swift'},
    'sql': {'sql'},
    'html': {'html', 'html5'},
    'css': {'css', 'css3'},
    'docker': {'docker'},
    'kubernetes': {'kubernetes', 'k8s'},
    'aws': {'aws'},
    'azure': {'azure'},
    'gcp': {'gcp'},
    'react': {'react', 'reactjs', 'react.js'},
    'node': {'node', 'nodejs', 'node.js'},
    'django': {'django'},
    'flask': {'flask'},
    'fastapi': {'fastapi'},
    'rails': {'rails'},
    'spring': {'spring'},
    'vue': {'vue', 'vuejs', 'vue.js'},
    'angular': {'angular', 'angularjs'},
    'tensorflow': {'tensorflow'},
    'pytorch': {'pytorch'},
    'nlp': {'nlp'},
    'ml': {'ml'},
    'ai': {'ai'},
    'spark': {'spark'},
    'hadoop': {'hadoop'},
    'postgres': {'postgres', 'postgresql'},
    'mysql': {'mysql'},
    'mongodb': {'mongo', 'mongodb'},
    'graphql': {'graphql'},
    'redis': {'redis'},
    'terraform': {'terraform'},
    '.net': {'.net', 'dotnet', 'net'},
}

# Keep alphanumerics plus the few punctuation marks that are meaningful in
# technology names (c++, c#, node.js). Everything else is a separator.
_TOKEN_RE = re.compile(r'[a-z0-9][a-z0-9+#.\-]*')


def _tokenize(text):
    """Return a set of normalized tokens from ``text``.

    Each token is added both raw and with surrounding ``.`` / ``-`` stripped so
    that ``python.`` -> ``python`` while ``c++`` and ``c#`` are preserved.
    """
    tokens = set()
    for raw in _TOKEN_RE.findall((text or '').lower()):
        tokens.add(raw)
        trimmed = raw.strip('.-')
        if trimmed:
            tokens.add(trimmed)
    return tokens


def extract_keywords(text):
    """Tokenize free text into meaningful, de-duplicated keywords."""
    if not text:
        return []
    keywords = []
    seen = set()
    for tok in _tokenize(text):
        if len(tok) <= 1 and tok != 'c':
            continue
        if tok in STOPWORDS or tok in seen:
            continue
        seen.add(tok)
        keywords.append(tok)
    return keywords


def detect_known_skills(text):
    """Return a sorted list of canonical skills detected in ``text``.

    Matching is token-based (not substring), so it is free of the classic
    false positives where short skill names matched inside unrelated words.
    """
    tokens = _tokenize(text)
    if not tokens:
        return []
    found = [canonical for canonical, forms in SKILL_ALIASES.items() if tokens & forms]
    return sorted(set(found))

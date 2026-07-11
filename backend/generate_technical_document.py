"""Generates the GitHub Talent Hunt technical design document (PDF).

Run ``python generate_technical_document.py`` to (re)build the PDF at
``docs/GitHub_Talent_Hunt_Technical_Document.pdf``. The document includes
vector data-flow diagrams and a Q&A covering the engineering problems the
project ran into and how they were solved.
"""
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "docs" / "GitHub_Talent_Hunt_Technical_Document.pdf"

# --- palette (matches the web UI) -----------------------------------------
INK = colors.HexColor("#0F172A")
ACCENT = colors.HexColor("#5B4BFF")
ACCENT_2 = colors.HexColor("#B14BFF")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#CBD5E1")
BAND = colors.HexColor("#EEF0FF")
GOLD = colors.HexColor("#B8890A")
STAGE_COLORS = ["#5B4BFF", "#6A45F5", "#7C3BFF", "#9333EA", "#B14BFF"]


# ==========================================================================
# Vector diagram helpers
# ==========================================================================
def _arrow_down(d, x, y_top, y_bottom, color=colors.HexColor("#94A3B8"), width=1.6):
    d.add(Line(x, y_top, x, y_bottom + 5, strokeColor=color, strokeWidth=width))
    d.add(Polygon([x - 5, y_bottom + 6, x + 5, y_bottom + 6, x, y_bottom - 1],
                  fillColor=color, strokeColor=color))


def _box(d, x, y, w, h, title, subtitle=None, fill="#5B4BFF",
         title_color=colors.white, sub_color=colors.HexColor("#E5E7EB")):
    d.add(Rect(x, y, w, h, rx=9, ry=9, fillColor=colors.HexColor(fill),
               strokeColor=colors.HexColor("#1F2937"), strokeWidth=0.7))
    cy = y + h / 2
    if subtitle:
        d.add(String(x + w / 2, cy + 4, title, textAnchor="middle",
                     fontName="Helvetica-Bold", fontSize=9.5, fillColor=title_color))
        d.add(String(x + w / 2, cy - 9, subtitle, textAnchor="middle",
                     fontName="Helvetica", fontSize=7, fillColor=sub_color))
    else:
        d.add(String(x + w / 2, cy - 3, title, textAnchor="middle",
                     fontName="Helvetica-Bold", fontSize=9.5, fillColor=title_color))


def pipeline_diagram(width=468):
    """Vertical 5-stage request pipeline with graceful-fallback annotations."""
    steps = [
        ("1 · PLAN", "Job description -> focused GitHub query + skills"),
        ("2 · SEARCH", "GitHub user-search API -> candidate usernames"),
        ("3 · ENRICH", "Parallel fetch of profiles + repositories"),
        ("4 · RANK", "Heuristic pre-rank over the full pool (fast, free)"),
        ("5 · EVALUATE", "LLM scores the shortlist; blend + normalize"),
    ]
    notes = [
        "LLM disabled -> keyword heuristic plan",
        None,
        "Failed profiles skipped, run continues",
        "Stars/forks/followers/skills scored",
        "429 / no LLM -> heuristic score",
    ]
    box_w, box_h, gap = 300, 46, 30
    n = len(steps)
    height = n * box_h + (n - 1) * gap + 16
    d = Drawing(width, height)
    x = 18
    y = height - box_h - 8
    for i, (title, sub) in enumerate(steps):
        _box(d, x, y, box_w, box_h, title, sub, fill=STAGE_COLORS[i])
        if notes[i]:
            d.add(String(x + box_w + 12, y + box_h / 2 - 2, "fallback: " + notes[i],
                         textAnchor="start", fontName="Helvetica-Oblique",
                         fontSize=6.6, fillColor=MUTED))
        if i < n - 1:
            _arrow_down(d, x + box_w / 2, y, y - gap)
        y -= (box_h + gap)
    return d


def architecture_diagram(width=468):
    """Layered architecture: clients -> Flask -> agent -> domain -> external."""
    rows = [
        ("CLIENTS", [("Web UI", "index / results.html"), ("JSON API", "/api/search")], "#5B4BFF"),
        ("WEB / APP", [("Flask app.py", "routes · session history · CSV · rate limit · CSP")], "#6A45F5"),
        ("ORCHESTRATION", [("TalentHuntAgent", "agent.py · plans, enriches, ranks, evaluates")], "#7C3BFF"),
        ("DOMAIN", [("llm.py", "provider bridge"), ("github_scraper.py", "API + HTML"),
                    ("ranker.py + utils.py", "scoring")], "#9333EA"),
        ("EXTERNAL", [("GitHub REST API", None), ("GitHub profile HTML", None),
                      ("Groq / OpenAI / Bedrock", None)], "#334155"),
    ]
    row_h, gap = 44, 26
    n = len(rows)
    height = n * row_h + (n - 1) * gap + 16
    d = Drawing(width, height)
    area_x, area_w = 66, width - 66 - 8
    y = height - row_h - 8
    for i, (label, boxes, color) in enumerate(rows):
        d.add(String(6, y + row_h / 2 - 3, label, textAnchor="start",
                     fontName="Helvetica-Bold", fontSize=7, fillColor=MUTED))
        m = len(boxes)
        inner_gap = 12
        bw = (area_w - (m - 1) * inner_gap) / m
        bx = area_x
        for (title, sub) in boxes:
            _box(d, bx, y, bw, row_h, title, sub, fill=color)
            bx += bw + inner_gap
        if i < n - 1:
            _arrow_down(d, area_x + area_w / 2, y, y - gap)
        y -= (row_h + gap)
    return d


def scoring_diagram(width=468):
    """How a final 0-100 score is assembled."""
    d = Drawing(width, 250)
    # Row of heuristic input signals.
    signals = ["skills", "repo kw", "bio kw", "followers", "repos", "stars", "forks"]
    sw, sg = 54, 6
    total = len(signals) * sw + (len(signals) - 1) * sg
    sx = (width - total) / 2
    for s in signals:
        d.add(Rect(sx, 210, sw, 26, rx=6, ry=6, fillColor=BAND, strokeColor=ACCENT, strokeWidth=0.6))
        d.add(String(sx + sw / 2, 219, s, textAnchor="middle", fontName="Helvetica",
                     fontSize=7, fillColor=INK))
        sx += sw + sg
    # Raw heuristic (left) and achievements (right) both feed the combined score.
    raw_x, raw_w = 24, 250
    ach_x, ach_w = 302, 142
    _arrow_down(d, raw_x + raw_w / 2, 210, 184)
    _box(d, raw_x, 156, raw_w, 30, "raw heuristic score", "skills + log-scaled reach", fill="#5B4BFF")
    d.add(Rect(ach_x, 156, ach_w, 30, rx=7, ry=7, fillColor=colors.HexColor("#FDF6E3"),
               strokeColor=GOLD, strokeWidth=0.8))
    d.add(String(ach_x + ach_w / 2, 175, "achievement signal", textAnchor="middle",
                 fontName="Helvetica-Bold", fontSize=8, fillColor=GOLD))
    d.add(String(ach_x + ach_w / 2, 163, "capped, pre-normalization", textAnchor="middle",
                 fontName="Helvetica", fontSize=6.6, fillColor=GOLD))
    _box(d, (width - 300) / 2, 106, 300, 26, "combined_heuristic  ->  normalize to 0-100", fill="#7C3BFF")
    _arrow_down(d, raw_x + raw_w / 2, 156, 132)
    _arrow_down(d, ach_x + ach_w / 2, 156, 132)
    _arrow_down(d, width / 2, 106, 80)
    _box(d, (width - 340) / 2, 54, 340, 26,
         "final = 0.75 x LLM_fit  +  0.25 x heuristic_norm", fill="#9333EA")
    _arrow_down(d, width / 2, 54, 28)
    _box(d, (width - 220) / 2, 2, 220, 26, "FINAL SCORE  (0 - 100, one decimal)", fill="#B14BFF")
    return d


# ==========================================================================
# Content
# ==========================================================================
def _bullets(items, styles):
    return ListFlowable([Paragraph(i, styles["Bul"]) for i in items],
                        bulletType="bullet", start="square")


def _qa(story, styles, question, problem, solution):
    story.append(Paragraph(question, styles["QA"]))
    story.append(Paragraph('<b>Problem:</b> ' + problem, styles["Body"]))
    story.append(Paragraph('<b>Solution:</b> ' + solution, styles["Body"]))
    story.append(Spacer(1, 8))


def build_story(styles):
    story = []

    # ---- Title -----------------------------------------------------------
    story.append(Paragraph("GitHub Talent Hunt (GITRadar)", styles["DocTitle"]))
    story.append(Paragraph("Technical Design, Data Flow &amp; Engineering Decisions", styles["Subtitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=LINE, spaceBefore=4, spaceAfter=12))
    story.append(Paragraph(
        "An LLM-assisted talent-hunt service that reads a job description, plans a focused "
        "GitHub search, enriches candidate profiles, and ranks developers by a blend of a "
        "deterministic heuristic and large-language-model evaluation — always degrading "
        "gracefully to the heuristic when no model is available.", styles["Lead"]))
    story.append(Spacer(1, 10))

    # ---- 1. Executive summary -------------------------------------------
    story.append(Paragraph("1. Executive Summary", styles["H1"]))
    story.append(Paragraph(
        "GITRadar combines GitHub search, profile enrichment, heuristic ranking, GitHub "
        "achievement badges, and optional LLM evaluation into a single end-to-end workflow. "
        "It is provider-agnostic (OpenAI, Groq/gpt-oss, or AWS Bedrock) and remains fully "
        "functional with no model configured. Recruiters get a ranked shortlist with an "
        "evidence-based fit summary, a downloadable CSV, and a per-browser search history.",
        styles["Body"]))

    # ---- 2. What it does -------------------------------------------------
    story.append(Paragraph("2. What the Project Does", styles["H1"]))
    story.append(_bullets([
        "Accepts a job description, optional location, and result size.",
        "Translates the description into a GitHub search query and a canonical skill list.",
        "Searches GitHub, then enriches each candidate with repositories and achievement badges.",
        "Ranks candidates by a heuristic (skills + reach) refined by LLM evaluation.",
        "Exposes both a server-rendered web UI and a JSON API.",
        "Lets the user export the on-screen shortlist to CSV and revisit past searches.",
    ], styles))

    # ---- 3. Architecture -------------------------------------------------
    story.append(Paragraph("3. System Architecture", styles["H1"]))
    story.append(Paragraph(
        "Concerns are separated into layers: a thin presentation layer, a Flask application "
        "layer, a single orchestrating agent, and a domain layer that talks to external "
        "services. Each layer depends only on the one below it.", styles["Body"]))
    story.append(Spacer(1, 6))
    story.append(architecture_diagram())
    story.append(Paragraph("Figure 1 — Layered system architecture.", styles["Caption"]))
    story.append(Spacer(1, 8))

    table_data = [
        ["Component", "Responsibility"],
        ["backend/app.py", "Flask routes, session-based search history, CSV export, rate limiting, security headers."],
        ["backend/agent.py", "Orchestrates the plan → search → enrich → rank → evaluate pipeline."],
        ["backend/llm.py", "Provider-agnostic LLM client (OpenAI / Groq / Bedrock) with graceful fallback."],
        ["backend/ranker.py", "Deterministic heuristic scoring of profiles."],
        ["backend/utils.py", "Token-based keyword extraction and skill detection."],
        ["backend/scrapers/github_scraper.py", "GitHub REST calls, profile enrichment, achievement-badge HTML scraping."],
        ["backend/config.py", "Centralized, environment-driven configuration and hard limits."],
        ["frontend/*.html", "Server-rendered search UI, results, CSV button, history sidebar."],
    ]
    table = Table(table_data, colWidths=[188, 280], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Courier"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.4),
        ("FONTSIZE", (0, 1), (0, -1), 7.4),
        ("FONTSIZE", (1, 1), (1, -1), 8.4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#F8FAFC")]),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)

    # ---- 4. Request data flow -------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("4. Request Data Flow", styles["H1"]))
    story.append(Paragraph(
        "A search request flows through five staged transformations that progressively narrow "
        "the space from broad GitHub results to a ranked shortlist. Every stage has a "
        "documented fallback so a partial failure never breaks the run.", styles["Body"]))
    story.append(Spacer(1, 6))
    story.append(pipeline_diagram())
    story.append(Paragraph("Figure 2 — Five-stage request pipeline with per-stage fallbacks.",
                           styles["Caption"]))

    # ---- 5. Ranking model -----------------------------------------------
    story.append(Paragraph("5. Ranking &amp; Scoring Model", styles["H1"]))
    story.append(Paragraph(
        "The heuristic scores keyword overlap (skills, repo text, bio) plus log-scaled reach "
        "(followers, public repos, total stars, total forks). Achievement badges add a small, "
        "capped signal <i>before</i> normalization so every score stays within 0–100. When an "
        "LLM is enabled, its 0–100 fit score is blended 75/25 with the normalized heuristic.",
        styles["Body"]))
    story.append(Spacer(1, 6))
    story.append(scoring_diagram())
    story.append(Paragraph("Figure 3 — How a final 0–100 score is assembled.", styles["Caption"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Reach signals are log-scaled so a handful of very popular accounts cannot dominate on "
        "popularity alone, while genuine impact (stars, forks) still separates strong profiles "
        "from empty ones.", styles["Body"]))

    # ---- 6. Achievements -------------------------------------------------
    story.append(Paragraph("6. GitHub Achievements", styles["H1"]))
    story.append(Paragraph(
        "GitHub achievement badges (Pull Shark, Starstruck, Galaxy Brain, Arctic Code Vault, "
        "etc.) are exposed by neither the REST nor the GraphQL API. They are scraped best-effort "
        "from the public profile HTML, parsed for badge name and tier, and only fetched for the "
        "shortlist so the number of extra HTTP requests stays bounded. Any failure returns an "
        "empty list and never breaks ranking.", styles["Body"]))

    # ---- 7. LLM provider layer ------------------------------------------
    story.append(Paragraph("7. LLM Provider Layer", styles["H1"]))
    story.append(Paragraph(
        "A single provider-agnostic client supports OpenAI, Groq (OpenAI-compatible, serving "
        "gpt-oss-20b), and AWS Bedrock, selected by the <font face='Courier'>LLM_PROVIDER</font> "
        "environment variable. The client returns strict JSON, tolerates code fences, and raises "
        "a typed <font face='Courier'>LLMUnavailable</font> that callers catch to fall back to the "
        "heuristic. Rate-limit resilience (retries honoring Retry-After, bounded concurrency, "
        "capped output tokens) is configuration-driven.", styles["Body"]))

    # ---- 8. CSV & history ------------------------------------------------
    story.append(Paragraph("8. CSV Export &amp; Search History", styles["H1"]))
    story.append(_bullets([
        "<b>CSV export:</b> the results shown on screen are POSTed back to a dedicated route and "
        "streamed as a download, so the file always matches the view without re-running the search. "
        "Cells are sanitized against spreadsheet formula injection.",
        "<b>Search history:</b> stored in the signed Flask session (per browser), rendered as a "
        "slide-out sidebar. Each entry re-runs its search on click.",
        "<b>No JavaScript:</b> a strict <font face='Courier'>script-src 'none'</font> CSP forbids "
        "client scripts, so both features are pure server-side + HTML forms, and the sidebar uses a "
        "CSS checkbox toggle.",
    ], styles))

    # ---- 9. Security -----------------------------------------------------
    story.append(Paragraph("9. Security &amp; Reliability", styles["H1"]))
    story.append(_bullets([
        "Strict security headers and a Content-Security-Policy with <font face='Courier'>script-src 'none'</font>.",
        "Per-IP rate limiting (Flask-Limiter) on search and export routes.",
        "ProxyFix honors load-balancer headers; server-side clamping of all request limits.",
        "GitHub and LLM errors are normalized into safe, non-leaking messages.",
        "CSV cells starting with = + - @ are prefixed to neutralize formula injection.",
    ], styles))

    # ---- 10. Q&A ---------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("10. Problems Faced &amp; How We Solved Them (Q&amp;A)", styles["H1"]))
    story.append(Paragraph(
        "The questions below capture the real engineering issues encountered during development "
        "and the reasoning behind each fix.", styles["Body"]))
    story.append(Spacer(1, 6))

    _qa(story, styles,
        "Q1. Ranking looked wrong — impactful developers were not rising to the top. Why?",
        "The scraper fetched each repository's stars and forks, but the ranking formula never used "
        "them. Two developers with the same keyword match scored identically even if one had "
        "20k-star projects and the other had empty repositories.",
        "Repository impact was added to the heuristic as log-scaled terms for total stars and forks, "
        "alongside new log-scaled weights for followers and public-repo count. Impact now visibly "
        "separates strong profiles while the log scale prevents popularity from dominating.")

    _qa(story, styles,
        "Q2. Two clearly different candidates both showed a score of 88. Is the ranking broken?",
        "Three things combined: repository count was not scored at all, followers barely moved the "
        "needle, and the score was rounded to a whole number — so 87.6 and 88.4 both rendered as "
        "88. Separately, achievement points were added <i>after</i> normalizing to 100, which pushed "
        "top scores above 100.",
        "Achievements were folded into the raw heuristic <i>before</i> normalization (keeping scores "
        "within 0–100), the score display was given one decimal place, star totals were surfaced "
        "on each card, and followers/repo-count were given real log-scaled weight. Near-ties now "
        "separate and explain themselves.")

    _qa(story, styles,
        "Q3. How do we include GitHub achievements when the API does not expose them?",
        "Achievement badges appear only on the rendered profile page; neither the REST nor the "
        "GraphQL API returns them.",
        "The profile HTML is scraped best-effort, parsed for badge name and tier, wrapped in "
        "try/except so it never breaks a run, and fetched only for the shortlisted candidates to "
        "keep the extra request volume bounded.")

    _qa(story, styles,
        "Q4. After configuring an LLM, every provider failed at client creation. Why?",
        "The pinned <font face='Courier'>openai==1.51.2</font> passed a <font face='Courier'>proxies"
        "</font> argument that newer <font face='Courier'>httpx</font> (≥0.28) had removed, raising "
        "a TypeError before any request was made — affecting OpenAI and Groq alike.",
        "The dependency was upgraded to <font face='Courier'>openai==2.45.0</font>, which is "
        "compatible with modern httpx, and the requirement pin was updated with an explanatory note.")

    _qa(story, styles,
        "Q5. On Groq's free tier only one of five candidates got an AI evaluation. What happened?",
        "Groq's free tier caps usage at 8000 tokens per minute. Firing the plan call plus all "
        "candidate evaluations in parallel instantly exceeded that, so most calls returned HTTP 429 "
        "and silently fell back to the heuristic summary.",
        "Evaluation was made rate-limit-aware via configuration: concurrency was lowered "
        "(serialized on the free tier), SDK retries were increased to honor the Retry-After header, "
        "per-evaluation output tokens were capped, the candidate payload was trimmed, and the number "
        "of evaluated candidates was reduced. All shortlisted candidates now evaluate cleanly.")

    _qa(story, styles,
        "Q6. The CSP blocks all JavaScript — how can we add a CSV button and a history sidebar?",
        "A hardened <font face='Courier'>script-src 'none'</font> policy forbids inline and external "
        "scripts, so client-side CSV generation and localStorage-based history were both impossible.",
        "Both features were implemented server-side. CSV is a form POST that echoes the rendered rows "
        "back and streams a file; history lives in the signed Flask session and renders as a CSS-only "
        "(checkbox-toggle) slide-out sidebar whose entries are re-search forms.")

    _qa(story, styles,
        "Q7. The downloaded CSV could carry a spreadsheet-injection payload. How is that handled?",
        "Candidate names and bios come from untrusted GitHub data and can begin with = + - or @, which "
        "spreadsheet apps interpret as formulas (a known CSV-injection vector).",
        "Every exported cell that starts with one of those characters is prefixed with a single quote, "
        "neutralizing formula execution while leaving the visible value intact.")

    # ---- 11. Tech stack --------------------------------------------------
    story.append(Paragraph("11. Technology Stack", styles["H1"]))
    story.append(_bullets([
        "Python 3 — orchestration, text processing, and API integration.",
        "Flask + Flask-Limiter — web UI, JSON API, and per-IP rate limiting.",
        "Requests — GitHub REST calls and achievement-HTML scraping with bounded retries.",
        "OpenAI SDK — shared client for OpenAI and Groq (gpt-oss-20b); boto3 for Bedrock.",
        "python-dotenv — environment-driven configuration.",
        "ReportLab — this technical document.",
    ], styles))

    # ---- 12. Future ------------------------------------------------------
    story.append(Paragraph("12. Future Enhancements", styles["H1"]))
    story.append(_bullets([
        "Persist search history and evaluations in a datastore (e.g. SQLite) for cross-device recall.",
        "Add a recency/activity signal (recent pushes) to further sharpen ranking.",
        "Cache profiles and achievement lookups to cut repeated GitHub traffic.",
        "Deeper repository signal extraction (languages over time, contribution graphs).",
    ], styles))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=LINE, spaceBefore=2, spaceAfter=10))
    story.append(Paragraph(
        "GITRadar shows how a practical recruiting workflow can be built on public developer data, "
        "lightweight automation, and optional AI — with resilience and graceful degradation as "
        "first-class design goals.", styles["Body"]))
    return story


def _make_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="DocTitle", parent=styles["Title"], fontName="Helvetica-Bold",
                              fontSize=24, leading=28, alignment=TA_CENTER, spaceAfter=4, textColor=ACCENT))
    styles.add(ParagraphStyle(name="Subtitle", parent=styles["Heading2"], fontName="Helvetica-Oblique",
                              fontSize=11.5, leading=15, alignment=TA_CENTER, textColor=MUTED, spaceAfter=6))
    styles.add(ParagraphStyle(name="Lead", parent=styles["BodyText"], fontName="Helvetica",
                              fontSize=10.5, leading=15, alignment=TA_JUSTIFY, textColor=INK))
    styles.add(ParagraphStyle(name="H1", parent=styles["Heading1"], fontName="Helvetica-Bold",
                              fontSize=13.5, leading=17, spaceBefore=15, spaceAfter=7, textColor=INK))
    styles.add(ParagraphStyle(name="Body", parent=styles["BodyText"], fontName="Helvetica",
                              fontSize=10, leading=14, alignment=TA_JUSTIFY, spaceAfter=5, textColor=INK))
    styles.add(ParagraphStyle(name="Bul", parent=styles["BodyText"], fontName="Helvetica",
                              fontSize=9.8, leading=13.5, leftIndent=16, bulletIndent=2, spaceAfter=4, textColor=INK))
    styles.add(ParagraphStyle(name="Caption", parent=styles["BodyText"], fontName="Helvetica-Oblique",
                              fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=MUTED, spaceBefore=4, spaceAfter=8))
    styles.add(ParagraphStyle(name="QA", parent=styles["BodyText"], fontName="Helvetica-Bold",
                              fontSize=10.5, leading=14, spaceBefore=6, spaceAfter=3, textColor=ACCENT_2))
    return styles


def generate_pdf(output_path=OUTPUT_PATH):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _make_styles()
    document = SimpleDocTemplate(
        str(output_path), pagesize=letter,
        rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54,
        title="GitHub Talent Hunt — Technical Document",
    )
    document.build(build_story(styles))
    return output_path


if __name__ == "__main__":
    output = generate_pdf()
    print(f"Technical document generated at {output}")

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import ListFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "docs" / "GitHub_Talent_Hunt_Technical_Document.pdf"


def build_story(styles):
    story = []

    story.append(Paragraph("GitHub Talent Hunt", styles["Title"]))
    story.append(Paragraph("Technical Design and Architecture Overview", styles["Subtitle"]))
    story.append(Spacer(1, 18))
    story.append(
        Paragraph(
            "This document describes the purpose, system design, implementation approach, and engineering rationale behind the GitHub Talent Hunt project.",
            styles["Body"],
        )
    )
    story.append(
        Paragraph(
            "The application helps recruiters, hiring managers, and technical teams identify GitHub users whose public profiles and repositories appear to match a given job description.",
            styles["Body"],
        )
    )
    story.append(Spacer(1, 12))

    story.append(Paragraph("1. Executive Summary", styles["Heading1"]))
    story.append(
        Paragraph(
            "GitHub Talent Hunt combines GitHub search, profile enrichment, heuristic ranking, and optional large-language-model evaluation into a single end-to-end workflow. The system is designed to be useful even when AI is unavailable, because it always falls back to deterministic ranking logic.",
            styles["Body"],
        )
    )

    story.append(Paragraph("2. What the Project Does", styles["Heading1"]))
    bullet_items = [
        "Accepts a job description, optional location, and result size from the user.",
        "Translates the description into a GitHub search query and a set of candidate skills.",
        "Searches GitHub for relevant users and enriches their public profiles with repository context.",
        "Ranks candidates using a heuristic score and optionally improves the ranking with LLM-based evaluation.",
        "Returns a search experience through both a web UI and a JSON API.",
    ]
    story.append(ListFlowable([Paragraph(item, styles["Bullet"]) for item in bullet_items]))

    story.append(Paragraph("3. How the Workflow Works", styles["Heading1"]))
    story.append(
        Paragraph(
            "The system follows a staged pipeline that gradually narrows the search space from broad GitHub results to the most relevant candidate profiles.",
            styles["Body"],
        )
    )
    workflow_steps = [
        "Planning: the agent converts the job description into a focused GitHub query and extracts relevant skills.",
        "Search: the scraper queries GitHub's user search API and collects candidate usernames.",
        "Enrichment: each candidate profile is expanded by fetching user metadata and recent repositories.",
        "Ranking: the heuristic scorer measures keyword overlap in bios, repositories, and skills.",
        "Evaluation: when enabled, an LLM scores the top candidates and returns matched and missing skills.",
    ]
    story.append(ListFlowable([Paragraph(step, styles["Bullet"]) for step in workflow_steps]))

    story.append(Paragraph("4. System Architecture", styles["Heading1"]))
    table_data = [
        ["Component", "Responsibility"],
        ["backend/app.py", "Flask web app and HTTP routes for the UI and API."],
        ["backend/agent.py", "Coordinates the full talent-hunt pipeline."],
        ["backend/llm.py", "Provides optional LLM integration for planning and evaluation."],
        ["backend/ranker.py", "Implements deterministic heuristic ranking."],
        ["backend/utils.py", "Tokenizes text and detects known technologies and skills."],
        ["backend/scrapers/github_scraper.py", "Handles GitHub API requests and profile enrichment."],
        ["backend/config.py", "Centralizes environment-driven configuration."],
        ["frontend/index.html and results.html", "Provide the user-facing search experience."],
    ]
    table = Table(table_data, colWidths=[140, 340], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B5FFF")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#F8FAFC")]),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 12))

    story.append(Paragraph("5. Technology Stack", styles["Heading1"]))
    tech_items = [
        "Python 3 for the backend service and orchestration logic.",
        "Flask for the web interface and API endpoints.",
        "Requests for GitHub API communication and retries.",
        "python-dotenv and centralized configuration for environment-driven settings.",
        "ReportLab for PDF generation and document formatting.",
        "Optional OpenAI or Bedrock integrations for richer ranking and candidate summaries.",
    ]
    story.append(ListFlowable([Paragraph(item, styles["Bullet"]) for item in tech_items]))

    story.append(Paragraph("6. Why These Technologies Were Chosen", styles["Heading1"]))
    story.append(
        Paragraph(
            "The stack favors simplicity, reliability, and graceful degradation. Flask is lightweight for a focused web experience, Python has strong support for text processing and API integrations, and the heuristic fallback ensures the product still functions even if an LLM provider is not configured.",
            styles["Body"],
        )
    )
    story.append(
        Paragraph(
            "The architecture intentionally separates concerns: the scraper retrieves data, the agent orchestrates the workflow, the ranker provides deterministic scoring, and the UI stays thin. That separation makes it easier to extend the project with new data sources, ranking methods, or deployment targets.",
            styles["Body"],
        )
    )

    story.append(Paragraph("7. Security and Reliability Considerations", styles["Heading1"]))
    security_items = [
        "The Flask app applies security headers and scoped CORS behavior for the JSON API.",
        "Proxy handling is configured to respect upstream load balancer headers in production.",
        "Rate limiting helps protect the public endpoint from abuse and accidental traffic spikes.",
        "GitHub errors are normalized into safe messages rather than exposing raw upstream details.",
    ]
    story.append(ListFlowable([Paragraph(item, styles["Bullet"]) for item in security_items]))

    story.append(Paragraph("8. Project Structure", styles["Heading1"]))
    story.append(
        Paragraph(
            "The repository is organized into a backend service, a lightweight frontend, and supporting configuration. The backend contains the search workflow, the LLM bridge, the scraper, and the ranking logic.",
            styles["Body"],
        )
    )

    story.append(Paragraph("9. Future Enhancements", styles["Heading1"]))
    future_items = [
        "Add richer candidate explanations and visual analytics for search results.",
        "Support additional providers and deeper repository signal extraction.",
        "Introduce caching for repeated searches and profile refreshes.",
        "Add a database-backed history of previous searches and candidate evaluations.",
    ]
    story.append(ListFlowable([Paragraph(item, styles["Bullet"]) for item in future_items]))

    story.append(PageBreak())
    story.append(Paragraph("Conclusion", styles["Heading1"]))
    story.append(
        Paragraph(
            "GitHub Talent Hunt demonstrates how a practical recruiting workflow can be built around public developer data, lightweight automation, and optional AI assistance. Its design emphasizes accuracy, resilience, and flexibility while remaining approachable for continued development.",
            styles["Body"],
        )
    )
    return story


def generate_pdf(output_path=OUTPUT_PATH):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=28, alignment=TA_CENTER, spaceAfter=12, textColor=colors.HexColor("#0B5FFF")))
    styles.add(ParagraphStyle(name="Subtitle", parent=styles["Heading2"], fontName="Helvetica-Oblique", fontSize=11, leading=14, alignment=TA_CENTER, textColor=colors.HexColor("#475569"), spaceAfter=18))
    styles.add(ParagraphStyle(name="Heading1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=13, leading=16, spaceBefore=14, spaceAfter=8, textColor=colors.HexColor("#0F172A")))
    styles.add(ParagraphStyle(name="Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=10.5, leading=14, alignment=TA_JUSTIFY, spaceAfter=6))
    styles.add(ParagraphStyle(name="Bullet", parent=styles["BodyText"], fontName="Helvetica", fontSize=10.2, leading=13, leftIndent=18, bulletIndent=0, spaceAfter=4))

    document = SimpleDocTemplate(str(output_path), pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)
    document.build(build_story(styles))
    return output_path


if __name__ == "__main__":
    output = generate_pdf()
    print(f"Technical document generated at {output}")

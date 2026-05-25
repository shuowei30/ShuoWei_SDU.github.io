#!/usr/bin/env python3
"""Send a daily graph theory paper digest through Resend."""

from __future__ import annotations

import datetime as dt
import email.utils
import html
import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ARXIV_API = "https://export.arxiv.org/api/query"
CROSSREF_API = "https://api.crossref.org/works"
RESEND_API = "https://api.resend.com/emails"
try:
    BEIJING = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:
    BEIJING = dt.timezone(dt.timedelta(hours=8), name="Asia/Shanghai")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

UNKNOWN_AUTHORS = "\u4f5c\u8005\u672a\u6807\u660e"

ARXIV_QUERIES = [
    'all:"directed graph" OR all:digraph OR all:"oriented graph"',
    'all:"graph theory" AND (all:directed OR all:digraph)',
    "all:tournament AND all:graph",
    'all:"directed network" AND (all:algorithm OR all:combinatorial)',
    'all:"directed hypergraph" OR all:"signed digraph"',
]

CROSSREF_TERMS = [
    "directed graph",
    "digraph graph theory",
    "oriented graph",
    "tournament graph theory",
]

KEYWORDS = {
    "directed graph": 5,
    "directed graphs": 5,
    "digraph": 5,
    "digraphs": 5,
    "oriented graph": 5,
    "oriented graphs": 5,
    "tournament": 4,
    "strong connectivity": 4,
    "directed hypergraph": 4,
    "graph theory": 3,
    "extremal": 3,
    "matching": 2,
    "coloring": 2,
    "domination": 2,
    "hamilton": 2,
    "connectivity": 2,
    "network": 1,
}

RELEVANT_ARXIV_CATEGORIES = {
    "math.CO",
    "cs.DM",
    "cs.DS",
    "cs.SI",
    "cs.LG",
    "stat.ML",
    "math.PR",
}


@dataclass(frozen=True)
class Paper:
    title: str
    authors: list[str]
    source: str
    link: str
    published: dt.datetime | None
    updated: dt.datetime | None
    summary: str
    venue: str = ""

    @property
    def date(self) -> dt.datetime | None:
        return self.updated or self.published


def request_text(url: str, headers: dict[str, str] | None = None) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ShuoWeiPaperDigest/1.0 (mailto:shuowei@mail.sdu.edu.cn)",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_arxiv_date(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def fetch_arxiv() -> list[Paper]:
    papers: list[Paper] = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    for query in ARXIV_QUERIES:
        params = urllib.parse.urlencode(
            {
                "search_query": query,
                "start": 0,
                "max_results": 20,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
        )
        try:
            feed = request_text(f"{ARXIV_API}?{params}")
            root = ET.fromstring(feed)
        except (urllib.error.URLError, ET.ParseError):
            continue

        for entry in root.findall("atom:entry", ns):
            title = clean_text(entry.findtext("atom:title", default="", namespaces=ns))
            summary = clean_text(entry.findtext("atom:summary", default="", namespaces=ns))
            link = clean_text(entry.findtext("atom:id", default="", namespaces=ns))
            authors = [
                clean_text(author.findtext("atom:name", default="", namespaces=ns))
                for author in entry.findall("atom:author", ns)
            ]
            categories = [
                category.attrib.get("term", "")
                for category in entry.findall("atom:category", ns)
                if category.attrib.get("term")
            ]
            venue = ", ".join(categories)
            papers.append(
                Paper(
                    title=title,
                    authors=[author for author in authors if author],
                    source="arXiv",
                    link=link,
                    published=parse_arxiv_date(entry.findtext("atom:published", default="", namespaces=ns)),
                    updated=parse_arxiv_date(entry.findtext("atom:updated", default="", namespaces=ns)),
                    summary=summary,
                    venue=venue,
                )
            )

    return papers


def parse_crossref_date(message: dict) -> dt.datetime | None:
    for key in ("published-online", "published-print", "published"):
        parts = message.get(key, {}).get("date-parts", [])
        if parts and parts[0]:
            year, month, day = (parts[0] + [1, 1])[:3]
            try:
                return dt.datetime(year, month, day, tzinfo=dt.timezone.utc)
            except ValueError:
                continue
    return None


def fetch_crossref(lookback_days: int) -> list[Paper]:
    papers: list[Paper] = []
    from_date = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=max(lookback_days, 7))).date()

    for term in CROSSREF_TERMS:
        params = urllib.parse.urlencode(
            {
                "query.title": term,
                "filter": f"from-pub-date:{from_date.isoformat()}",
                "sort": "published",
                "order": "desc",
                "rows": 5,
            }
        )
        try:
            data = json.loads(request_text(f"{CROSSREF_API}?{params}"))
        except (urllib.error.URLError, json.JSONDecodeError):
            continue

        for item in data.get("message", {}).get("items", []):
            title = clean_text(" ".join(item.get("title") or []))
            if not title:
                continue
            authors = []
            for author in item.get("author", []):
                full_name = clean_text(" ".join([author.get("given", ""), author.get("family", "")]))
                if full_name:
                    authors.append(full_name)
            link = item.get("URL") or item.get("DOI") or ""
            venue = clean_text(" ".join(item.get("container-title") or []))
            published = parse_crossref_date(item)
            abstract = clean_text(re.sub(r"<[^>]+>", " ", item.get("abstract", "")))
            papers.append(
                Paper(
                    title=title,
                    authors=authors,
                    source="Journal/Crossref",
                    link=link,
                    published=published,
                    updated=None,
                    summary=abstract or "Crossref record found. The publisher page may contain the full abstract.",
                    venue=venue,
                )
            )

    return papers


def relevance_score(paper: Paper) -> int:
    blob = f"{paper.title} {paper.summary}".lower()
    score = 0
    for keyword, weight in KEYWORDS.items():
        if keyword in blob:
            score += weight
    return score


def is_relevant(paper: Paper, now: dt.datetime) -> bool:
    score = relevance_score(paper)
    if score <= 0:
        return False
    if paper.date and paper.date > now + dt.timedelta(days=1):
        return False
    if paper.source == "arXiv":
        categories = {category.strip() for category in paper.venue.split(",") if category.strip()}
        if categories and categories.isdisjoint(RELEVANT_ARXIV_CATEGORIES) and score < 8:
            return False
    if paper.source == "Journal/Crossref" and score < 5:
        return False
    return True


def dedupe(papers: list[Paper]) -> list[Paper]:
    seen: set[str] = set()
    unique: list[Paper] = []
    for paper in papers:
        key = paper.link.lower() or paper.title.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(paper)
    return unique


def pick_papers(papers: list[Paper], lookback_days: int, limit: int = 8) -> tuple[list[Paper], bool]:
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=lookback_days)
    relevant = [paper for paper in dedupe(papers) if is_relevant(paper, now)]
    recent = [paper for paper in relevant if paper.date and paper.date >= cutoff]
    pool = recent or relevant
    pool.sort(key=lambda item: (relevance_score(item), item.date or dt.datetime.min.replace(tzinfo=dt.timezone.utc)), reverse=True)
    return pool[:limit], bool(recent)


def short_date(value: dt.datetime | None) -> str:
    if not value:
        return "\u65e5\u671f\u672a\u6807\u660e"
    return value.astimezone(BEIJING).strftime("%Y-%m-%d")


def split_sentences(text: str, max_sentences: int = 2) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text)
    selected = " ".join(parts[:max_sentences]).strip()
    return selected or text


def main_work(paper: Paper) -> str:
    text = split_sentences(paper.summary, 2)
    return textwrap.shorten(text, width=460, placeholder="...")


def research_questions(paper: Paper) -> list[str]:
    blob = f"{paper.title} {paper.summary}".lower()
    questions = [
        "\u80fd\u5426\u628a\u6587\u4e2d\u7684\u7ed3\u8bba\u63a8\u5e7f\u5230\u66f4\u4e00\u822c\u7684\u6709\u5411\u56fe\u7c7b\u3001\u5e26\u6743\u6709\u5411\u56fe\u6216\u968f\u673a\u6709\u5411\u56fe\u6a21\u578b\uff1f",
        "\u6838\u5fc3\u754c\u6216\u7ed3\u6784\u6761\u4ef6\u662f\u5426\u662f\u6700\u4f18\u7684\uff0c\u662f\u5426\u5b58\u5728\u66f4\u7d27\u7684\u6781\u503c\u6784\u9020\u6216\u53cd\u4f8b\u65cf\uff1f",
    ]
    if any(term in blob for term in ("algorithm", "complexity", "approximation", "parameterized")):
        questions.append("\u76f8\u5e94\u95ee\u9898\u662f\u5426\u5b58\u5728\u66f4\u5feb\u7684\u7cbe\u786e\u7b97\u6cd5\u3001\u53c2\u6570\u5316\u7b97\u6cd5\u6216\u8fd1\u4f3c\u4e0b\u754c\uff1f")
    if any(term in blob for term in ("spectral", "eigen", "laplacian", "matrix")):
        questions.append("\u8c31\u6761\u4ef6\u4e0e\u6709\u5411\u56fe\u7684\u8fde\u901a\u6027\u3001\u5708\u7ed3\u6784\u6216\u7a33\u5b9a\u6027\u4e4b\u95f4\u662f\u5426\u6709\u66f4\u76f4\u63a5\u7684\u523b\u753b\uff1f")
    if any(term in blob for term in ("random", "probabilistic", "threshold")):
        questions.append("\u968f\u673a\u6a21\u578b\u4e2d\u7684\u9608\u503c\u73b0\u8c61\u80fd\u5426\u8f6c\u5316\u4e3a\u786e\u5b9a\u6027\u56fe\u7c7b\u4e0a\u7684\u7ed3\u6784\u5b9a\u7406\uff1f")
    if any(term in blob for term in ("tournament", "oriented graph", "digraph")):
        questions.append("\u8fd9\u4e9b\u65b9\u6cd5\u5bf9 tournament\u3001oriented graph \u6216\u5f3a\u8fde\u901a digraph \u662f\u5426\u7ed9\u51fa\u65b0\u7684\u5206\u7c7b\u601d\u8def\uff1f")
    return questions[:4]


def build_digest(papers: list[Paper], has_recent: bool) -> tuple[str, str, str]:
    today = dt.datetime.now(BEIJING).strftime("%Y-%m-%d")
    subject = f"\u56fe\u8bba\u4e0e\u6709\u5411\u56fe\u6700\u65b0\u8bba\u6587\u65e5\u62a5 - {today}"
    note = "\u4ee5\u4e0b\u8bba\u6587\u4f18\u5148\u6765\u81ea\u6700\u8fd1\u66f4\u65b0\u8bb0\u5f55\u3002" if has_recent else "\u6700\u8fd1\u7a97\u53e3\u5185\u6ca1\u6709\u7b5b\u5230\u8db3\u591f\u5f3a\u76f8\u5173\u7684\u65b0\u8bba\u6587\uff0c\u4e0b\u9762\u8865\u5145\u8fd1\u671f\u9ad8\u76f8\u5173\u8bb0\u5f55\u3002"

    text_lines = [subject, "", note, ""]
    html_parts = [
        f"<h2>{html.escape(subject)}</h2>",
        f"<p>{html.escape(note)}</p>",
    ]

    if not papers:
        text_lines.append("\u4eca\u5929\u6ca1\u6709\u68c0\u7d22\u5230\u8db3\u591f\u76f8\u5173\u7684\u8bba\u6587\u3002")
        html_parts.append("<p>\u4eca\u5929\u6ca1\u6709\u68c0\u7d22\u5230\u8db3\u591f\u76f8\u5173\u7684\u8bba\u6587\u3002</p>")
    for index, paper in enumerate(papers, 1):
        authors = ", ".join(paper.authors[:8]) + (" et al." if len(paper.authors) > 8 else "")
        questions = research_questions(paper)
        score = relevance_score(paper)

        text_lines.extend(
            [
                f"{index}. {paper.title}",
                f"\u4f5c\u8005\uff1a{authors or UNKNOWN_AUTHORS}",
                f"\u6765\u6e90\uff1a{paper.source}{' | ' + paper.venue if paper.venue else ''}",
                f"\u65e5\u671f\uff1a{short_date(paper.date)}",
                f"\u94fe\u63a5\uff1a{paper.link}",
                f"\u76f8\u5173\u5ea6\uff1a{score}",
                f"\u6458\u8981\u6982\u62ec\uff1a{paper.summary}",
                f"\u4e3b\u8981\u5de5\u4f5c\uff1a{main_work(paper)}",
                "\u53ef\u4ee5\u7ee7\u7eed\u505a\u7684\u95ee\u9898\uff1a",
                *[f"- {question}" for question in questions],
                "",
            ]
        )

        html_parts.append("<hr>")
        html_parts.append(f"<h3>{index}. {html.escape(paper.title)}</h3>")
        html_parts.append(f"<p><strong>\u4f5c\u8005\uff1a</strong>{html.escape(authors or UNKNOWN_AUTHORS)}</p>")
        html_parts.append(
            f"<p><strong>\u6765\u6e90\uff1a</strong>{html.escape(paper.source)}"
            f"{html.escape(' | ' + paper.venue) if paper.venue else ''}<br>"
            f"<strong>\u65e5\u671f\uff1a</strong>{html.escape(short_date(paper.date))}<br>"
            f"<strong>\u94fe\u63a5\uff1a</strong><a href=\"{html.escape(paper.link)}\">{html.escape(paper.link)}</a><br>"
            f"<strong>\u76f8\u5173\u5ea6\uff1a</strong>{score}</p>"
        )
        html_parts.append(f"<p><strong>\u6458\u8981\u6982\u62ec\uff1a</strong>{html.escape(paper.summary)}</p>")
        html_parts.append(f"<p><strong>\u4e3b\u8981\u5de5\u4f5c\uff1a</strong>{html.escape(main_work(paper))}</p>")
        html_parts.append("<p><strong>\u53ef\u4ee5\u7ee7\u7eed\u505a\u7684\u95ee\u9898\uff1a</strong></p><ul>")
        html_parts.extend(f"<li>{html.escape(question)}</li>" for question in questions)
        html_parts.append("</ul>")

    if papers:
        text_lines.extend(["\u4f18\u5148\u9605\u8bfb\u5efa\u8bae\uff1a"])
        html_parts.append("<h3>\u4f18\u5148\u9605\u8bfb\u5efa\u8bae</h3><ol>")
        for paper in papers[: min(5, len(papers))]:
            text_lines.append(f"- {paper.title}")
            html_parts.append(f"<li>{html.escape(paper.title)}</li>")
        html_parts.append("</ol>")

    return subject, "\n".join(text_lines), "\n".join(html_parts)


def send_email(subject: str, text: str, html_body: str) -> str:
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    sender = os.environ.get("PAPER_DIGEST_FROM", "Shuo Wei Paper Digest <onboarding@resend.dev>").strip()
    recipient = os.environ.get("PAPER_DIGEST_TO", "shuowei@mail.sdu.edu.cn").strip()
    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not configured.")

    payload = json.dumps(
        {
            "from": sender,
            "to": [recipient],
            "subject": subject,
            "text": text,
            "html": html_body,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        RESEND_API,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "Idempotency-Key": f"paper-digest-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S')}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
            return body.get("id", "sent")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Resend API failed: HTTP {exc.code} {details}") from exc


def main() -> None:
    lookback_days = int(os.environ.get("LOOKBACK_DAYS", "3"))
    papers = fetch_arxiv() + fetch_crossref(lookback_days)
    selected, has_recent = pick_papers(papers, lookback_days)
    subject, text, html_body = build_digest(selected, has_recent)

    print(text)
    if os.environ.get("PAPER_DIGEST_DRY_RUN", "").lower() in {"1", "true", "yes"}:
        print("\nDry run enabled. Email was not sent.")
        return

    email_id = send_email(subject, text, html_body)
    print(f"\nEmail sent through Resend. id={email_id}")


if __name__ == "__main__":
    main()

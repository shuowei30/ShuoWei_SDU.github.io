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
        return "鏃ユ湡鏈爣鏄?
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
        "鑳藉惁鎶婃枃涓殑缁撹鎺ㄥ箍鍒版洿涓€鑸殑鏈夊悜鍥剧被銆佸甫鏉冩湁鍚戝浘鎴栭殢鏈烘湁鍚戝浘妯″瀷锛?,
        "鏍稿績鐣屾垨缁撴瀯鏉′欢鏄惁鏄渶浼樼殑锛屾槸鍚﹀瓨鍦ㄦ洿绱х殑鏋佸€兼瀯閫犳垨鍙嶄緥鏃忥紵",
    ]
    if any(term in blob for term in ("algorithm", "complexity", "approximation", "parameterized")):
        questions.append("鐩稿簲闂鏄惁瀛樺湪鏇村揩鐨勭簿纭畻娉曘€佸弬鏁板寲绠楁硶鎴栬繎浼间笅鐣岋紵")
    if any(term in blob for term in ("spectral", "eigen", "laplacian", "matrix")):
        questions.append("璋辨潯浠朵笌鏈夊悜鍥剧殑杩為€氭€с€佸湀缁撴瀯鎴栫ǔ瀹氭€т箣闂存槸鍚︽湁鏇寸洿鎺ョ殑鍒荤敾锛?)
    if any(term in blob for term in ("random", "probabilistic", "threshold")):
        questions.append("闅忔満妯″瀷涓殑闃堝€肩幇璞¤兘鍚﹁浆鍖栦负纭畾鎬у浘绫讳笂鐨勭粨鏋勫畾鐞嗭紵")
    if any(term in blob for term in ("tournament", "oriented graph", "digraph")):
        questions.append("杩欎簺鏂规硶瀵?tournament銆乷riented graph 鎴栧己杩為€?digraph 鏄惁缁欏嚭鏂扮殑鍒嗙被鎬濊矾锛?)
    return questions[:4]


def build_digest(papers: list[Paper], has_recent: bool) -> tuple[str, str, str]:
    today = dt.datetime.now(BEIJING).strftime("%Y-%m-%d")
    subject = f"鍥捐涓庢湁鍚戝浘鏈€鏂拌鏂囨棩鎶?- {today}"
    note = "浠ヤ笅璁烘枃浼樺厛鏉ヨ嚜鏈€杩戞洿鏂拌褰曘€? if has_recent else "鏈€杩戠獥鍙ｅ唴娌℃湁绛涘埌瓒冲寮虹浉鍏崇殑鏂拌鏂囷紝涓嬮潰琛ュ厖杩戞湡楂樼浉鍏宠褰曘€?

    text_lines = [subject, "", note, ""]
    html_parts = [
        f"<h2>{html.escape(subject)}</h2>",
        f"<p>{html.escape(note)}</p>",
    ]

    if not papers:
        text_lines.append("浠婂ぉ娌℃湁妫€绱㈠埌瓒冲鐩稿叧鐨勮鏂囥€?)
        html_parts.append("<p>浠婂ぉ娌℃湁妫€绱㈠埌瓒冲鐩稿叧鐨勮鏂囥€?/p>")
    for index, paper in enumerate(papers, 1):
        authors = ", ".join(paper.authors[:8]) + (" et al." if len(paper.authors) > 8 else "")
        questions = research_questions(paper)
        score = relevance_score(paper)

        text_lines.extend(
            [
                f"{index}. {paper.title}",
                f"浣滆€咃細{authors or '浣滆€呮湭鏍囨槑'}",
                f"鏉ユ簮锛歿paper.source}{' | ' + paper.venue if paper.venue else ''}",
                f"鏃ユ湡锛歿short_date(paper.date)}",
                f"閾炬帴锛歿paper.link}",
                f"鐩稿叧搴︼細{score}",
                f"鎽樿姒傛嫭锛歿paper.summary}",
                f"涓昏宸ヤ綔锛歿main_work(paper)}",
                "鍙互缁х画鍋氱殑闂锛?,
                *[f"- {question}" for question in questions],
                "",
            ]
        )

        html_parts.append("<hr>")
        html_parts.append(f"<h3>{index}. {html.escape(paper.title)}</h3>")
        html_parts.append(f"<p><strong>浣滆€咃細</strong>{html.escape(authors or '浣滆€呮湭鏍囨槑')}</p>")
        html_parts.append(
            f"<p><strong>鏉ユ簮锛?/strong>{html.escape(paper.source)}"
            f"{html.escape(' | ' + paper.venue) if paper.venue else ''}<br>"
            f"<strong>鏃ユ湡锛?/strong>{html.escape(short_date(paper.date))}<br>"
            f"<strong>閾炬帴锛?/strong><a href=\"{html.escape(paper.link)}\">{html.escape(paper.link)}</a><br>"
            f"<strong>鐩稿叧搴︼細</strong>{score}</p>"
        )
        html_parts.append(f"<p><strong>鎽樿姒傛嫭锛?/strong>{html.escape(paper.summary)}</p>")
        html_parts.append(f"<p><strong>涓昏宸ヤ綔锛?/strong>{html.escape(main_work(paper))}</p>")
        html_parts.append("<p><strong>鍙互缁х画鍋氱殑闂锛?/strong></p><ul>")
        html_parts.extend(f"<li>{html.escape(question)}</li>" for question in questions)
        html_parts.append("</ul>")

    if papers:
        text_lines.extend(["浼樺厛闃呰寤鸿锛?])
        html_parts.append("<h3>浼樺厛闃呰寤鸿</h3><ol>")
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

#!/usr/bin/env python3
"""Privacy-safe intake and public extraction for mobile-shared social links."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse, urlunparse


URL_RE = re.compile(r"https?://[^\s<>)\"']+")
TRAILING_URL_PUNCTUATION = ".,;:!?，。；：！？、"
SUPPORTED_HOST_HINTS = ("mp.weixin.qq.com", "xiaohongshu.com", "xhslink.com")
SENSITIVE_PATTERNS = re.compile(
    r"(?i)(xsec[_-]?token=|share_id=|wechatwid=|shareredid=|app_platform=|app_version=|xhscdn|masterurl|url_ref|cookie=|authorization:|set-cookie|token=|sig=|sign=|signature=)"
)


@dataclass(frozen=True)
class LinkItem:
    original_url: str
    storage_url: str
    platform: str


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone().replace(microsecond=0)


def today() -> str:
    return now_local().date().isoformat()


def clean_url(value: str) -> str:
    return value.rstrip(TRAILING_URL_PUNCTUATION)


def detect_platform(value: str) -> str:
    host = urlparse(value).netloc.lower()
    if "mp.weixin.qq.com" in host:
        return "wechat-article"
    if "xiaohongshu.com" in host or "xhslink.com" in host:
        return "xhs"
    return "unknown"


def is_supported(value: str) -> bool:
    host = urlparse(value).netloc.lower()
    return any(hint in host for hint in SUPPORTED_HOST_HINTS)


def storage_url_for(value: str) -> str:
    parsed = urlparse(value)
    if detect_platform(value) == "xhs":
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    return value


def sanitize_durable_text(value: object) -> str:
    text = str(value or "")
    for match in list(URL_RE.finditer(text)):
        original = clean_url(match.group(0))
        replacement = storage_url_for(original) if is_supported(original) else "[redacted-url]"
        text = text.replace(original, replacement)
    text = re.sub(
        r"(?i)(xsec[_-]?token|share_id|wechatwid|shareredid|app_platform|app_version|url_ref|cookie|authorization|set-cookie|token|sig|sign|signature)=\S+",
        "[redacted-param]",
        text,
    )
    return text.strip()


def slugify(value: str, fallback: str = "source") -> str:
    value = value.strip().lower()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "-", value)
    return value.strip("-")[:90] or fallback


def short_hash(value: str, length: int = 10) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def extract_links(texts: Iterable[str], urls: Iterable[str]) -> list[LinkItem]:
    seen: set[str] = set()
    items: list[LinkItem] = []
    candidates: list[str] = []
    for value in urls:
        candidates.append(value)
    for text in texts:
        candidates.extend(match.group(0) for match in URL_RE.finditer(text))
    for candidate in candidates:
        original = clean_url(candidate)
        if not is_supported(original):
            continue
        storage = storage_url_for(original)
        if storage in seen:
            continue
        seen.add(storage)
        items.append(LinkItem(original_url=original, storage_url=storage, platform=detect_platform(original)))
    return items


def read_inputs(args: argparse.Namespace) -> list[str]:
    texts: list[str] = []
    for path_text in args.text_file or []:
        texts.append(Path(path_text).read_text(encoding="utf-8", errors="replace"))
    if args.text:
        texts.append(args.text)
    if args.stdin:
        texts.append(sys.stdin.read())
    return texts


def relative(path: Optional[Path], root: Path) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def write_inbox(root: Path, item: LinkItem, run_id: str, source_channel: str) -> Path:
    inbox_dir = root / ".codex-project" / "inbox" / "mobile-share"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(item.storage_url, "mobile-share")
    path = inbox_dir / f"{run_id}-{item.platform}-{slug}-{short_hash(item.storage_url, 8)}.md"
    redaction = "xhs_share_query_redacted" if item.platform == "xhs" else "not_required"
    path.write_text(
        f"""---
source_channel: {yaml_quote(source_channel)}
captured_at: {yaml_quote(now_local().isoformat())}
platform_hint: {yaml_quote(item.platform)}
status: inbox
redaction_status: {yaml_quote(redaction)}
---

# Mobile Share Inbox / 手机分享入口

{item.storage_url}

privacy_note: durable storage uses canonical URL only; tracking query and signed media URLs are not stored.
""",
        encoding="utf-8",
    )
    return path


def write_raw(root: Path, item: LinkItem, inbox: Path) -> Path:
    raw_dir = root / ".raw" / "social" / item.platform
    raw_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(item.storage_url, item.platform)
    path = raw_dir / f"{slug}-{today()}-{short_hash(str(inbox), 8)}.md"
    tags = [
        f"platform/{item.platform}",
        "source/mobile-share",
        "status/queued",
    ]
    if item.platform == "xhs":
        tags.append("privacy/share-query-redacted")
    path.write_text(
        f"""---
source_type: social_link_raw
platform: {yaml_quote(item.platform)}
source_channel: "mobile_share"
source_url: {yaml_quote(item.storage_url)}
canonical_url: {yaml_quote(item.storage_url)}
captured_at: {yaml_quote(now_local().isoformat())}
original_inbox_item: {yaml_quote(relative(inbox, root))}
triage_status: queued
tags:
{chr(10).join(f"  - {yaml_quote(tag)}" for tag in tags)}
---

# {item.platform} raw link package

## Link / 链接

- canonical_url: {item.storage_url}

## Privacy / 隐私

- Xiaohongshu query parameters are removed before durable storage.
- No cookies, account tokens, signed media URLs, or chat exports are stored.
""",
        encoding="utf-8",
    )
    return path


def ephemeral_fetch_url_for(item: LinkItem) -> str:
    """Return the URL used only for transient HTML probing.

    Xiaohongshu often exposes SSR noteData only on the original mobile share
    URL. Durable files still use storage_url, so callers must never persist
    this value in reports or raw packages.
    """

    return item.original_url if item.platform == "xhs" else item.storage_url


def fetch_html(url: str, timeout: int, platform: str = "") -> tuple[str, str]:
    user_agent = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
        "Mobile/15E148 Safari/604.1"
        if platform == "xhs"
        else "Mozilla/5.0 AppleWebKit/537.36 Chrome/125 Safari/537.36"
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
        return data.decode("utf-8", errors="replace"), "fetched"
    except Exception as exc:  # pragma: no cover - network dependent.
        return "", f"fetch_failed: {exc}"


def meta_content(html_text: str, key: str) -> str:
    patterns = [
        rf"<meta[^>]+property=[\"']{re.escape(key)}[\"'][^>]+content=[\"']([^\"']*)[\"']",
        rf"<meta[^>]+name=[\"']{re.escape(key)}[\"'][^>]+content=[\"']([^\"']*)[\"']",
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def decode_js_literal(value: str) -> str:
    value = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), value)
    value = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), value)
    for old, new in {
        r"\'": "'",
        r'\"': '"',
        r"\/": "/",
        r"\n": "\n",
        r"\r": "\r",
        r"\t": "\t",
        r"\\": "\\",
    }.items():
        value = value.replace(old, new)
    return value


def strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def wechat_body_text(html_text: str) -> str:
    match = re.search(r"content_noencode:\s*'((?:\\.|[^'])*)'", html_text)
    if not match:
        return ""
    return strip_tags(decode_js_literal(match.group(1)))


def excerpt(value: str, limit: int = 900) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def key_points(text: str, description: str, title: str) -> list[str]:
    basis = "\n".join(part for part in [description, text] if part).strip()
    if not basis:
        return [f"Public HTML fetched for {title or 'article'}, but article body could not be decoded."]
    chunks = [
        chunk.strip(" ，。；;:：")
        for chunk in re.split(r"(?:\n+|。|；|！|？|(?<=[.!?])\s+)", basis)
    ]
    points: list[str] = []
    for chunk in chunks:
        compact = re.sub(r"\s+", " ", chunk).strip()
        if len(compact) < 12 or compact in points:
            continue
        points.append(compact[:160])
        if len(points) >= 4:
            break
    return points or [excerpt(basis, 160)]


def write_wechat_extraction(root: Path, item: LinkItem, inbox: Path, html_text: str) -> Path:
    title = meta_content(html_text, "og:title") or meta_content(html_text, "twitter:title") or "微信公众号文章"
    description = meta_content(html_text, "description")
    author = meta_content(html_text, "author") or meta_content(html_text, "og:article:author")
    account_match = re.search(r'data-nickname="([^"]+)"', html_text)
    account = html.unescape(account_match.group(1)).strip() if account_match else author
    body = wechat_body_text(html_text)
    output = root / ".raw" / "social" / "wechat-article" / f"{slugify(title, 'wechat-article')}-extracted-{today()}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    points = key_points(body, description, title)
    output.write_text(
        f"""---
source_type: wechat_article_extracted
platform: wechat-article
source_channel: "mobile_share"
source_url: {yaml_quote(item.storage_url)}
canonical_url: {yaml_quote(item.storage_url)}
fetched_at: {yaml_quote(now_local().isoformat())}
original_inbox_item: {yaml_quote(relative(inbox, root))}
triage_status: extracted
tags:
  - "platform/wechat-article"
  - "source/mobile-share"
  - "status/extracted"
---

# {title}

## Metadata / 元数据

- account: {account or "unknown"}
- author: {author or "unknown"}
- description: {description or "none"}

## Key Points / 要点

{chr(10).join(f"- {point}" for point in points)}

## Article Excerpt / 文章摘录

{excerpt(body) or "Article body could not be decoded from public HTML."}

## Pipeline Status / 流水线状态

- public metadata extraction: done
- media download: not performed
- relevance screening: ready
""",
        encoding="utf-8",
    )
    return output


def json_after_marker(text: str, marker: str) -> dict[str, object]:
    start = text.find(marker)
    if start < 0:
        return {}
    decoder = json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(text[start + len(marker) :])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def write_xhs_extraction(root: Path, item: LinkItem, inbox: Path, html_text: str) -> Path:
    note_id = urlparse(item.storage_url).path.rstrip("/").split("/")[-1] or "unknown"
    state = json_after_marker(html_text, "window.__SETUP_SERVER_STATE__=")
    page_data = state.get("LAUNCHER_SSR_STORE_PAGE_DATA", {}) if isinstance(state, dict) else {}
    note = page_data.get("noteData", {}) if isinstance(page_data, dict) else {}
    blocked = not isinstance(note, dict) or not note
    title = (
        f"小红书公开页抽取受限-{note_id}"
        if blocked
        else sanitize_durable_text(note.get("title") or note.get("displayTitle") or f"小红书-{note_id}")
    )
    output = root / ".raw" / "social" / "xhs" / f"{slugify(title, 'xhs')}-extracted-{today()}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    if blocked:
        status = "extraction_blocked"
        description = "Public HTML did not expose SSR noteData in this environment."
        evidence = "Public HTML fetched, but noteData was unavailable. No media, ASR, OCR, or signed stream URL was persisted."
        content_type = "unknown"
    else:
        status = "extracted_metadata_only"
        description = sanitize_durable_text(note.get("desc") or note.get("displayTitle") or "")
        evidence = "Public noteData metadata was available; media URLs remain redacted."
        content_type = sanitize_durable_text(note.get("type") or "unknown")
    output.write_text(
        f"""---
source_type: {"xhs_public_extraction_blocked" if blocked else "xhs_public_metadata_extracted"}
platform: xhs
source_channel: "mobile_share"
source_url: {yaml_quote(item.storage_url)}
canonical_url: {yaml_quote(item.storage_url)}
fetched_at: {yaml_quote(now_local().isoformat())}
original_inbox_item: {yaml_quote(relative(inbox, root))}
triage_status: {status}
tags:
  - "platform/xhs"
  - "source/mobile-share"
  - "status/{'extraction-blocked' if blocked else 'metadata-only'}"
---

# {title}

## Metadata / 元数据

- note_id: {note_id}
- content_type: {content_type}
- description: {description or "none"}

## Analysis Boundary / 分析边界

- This is not a full reading of Xiaohongshu content unless ASR, OCR, screenshots, keyframes, or exported text are present.
- Likes, collections, author data, and comments are weak routing signals only.

## Extraction Evidence / 抽取证据

- {evidence}

## Pipeline Status / 流水线状态

- link parsing: done
- public HTML probe: done
- media download: not performed
- ASR/OCR: not started
""",
        encoding="utf-8",
    )
    return output


def write_batch_report(root: Path, run_dir: Path, records: list[dict[str, str]], since: str) -> Path:
    passed_wechat = sum(1 for item in records if item["platform"] == "wechat-article" and item["result"] == "pass")
    xhs_partial = sum(1 for item in records if item["platform"] == "xhs" and item["result"] == "partial")
    report = run_dir / "run-report.md"
    lines = [
        "---",
        "artifact_type: social_link_intake_report",
        f"created_at: {yaml_quote(now_local().isoformat())}",
        f"since: {yaml_quote(since)}",
        f"link_count: {len(records)}",
        "---",
        "",
        "# Social Link Intake Report / 社交链接入口报告",
        "",
        "## Summary / 摘要",
        "",
        f"- links: `{len(records)}`",
        f"- wechat_extracted: `{passed_wechat}`",
        f"- xhs_partial_or_blocked: `{xhs_partial}`",
        "",
        "## Items / 条目",
        "",
        "| platform | result | storage_url | extracted_source | blocker |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in records:
        lines.append(
            "| {platform} | `{result}` | {url} | `{extracted}` | {blocker} |".format(
                platform=record["platform"],
                result=record["result"],
                url=record["storage_url"],
                extracted=record.get("extracted_source", ""),
                blocker=record.get("blocker", ""),
            )
        )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (run_dir / "items.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def validate_no_sensitive_text(paths: Iterable[Path]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), 1):
            if SENSITIVE_PATTERNS.search(line):
                findings.append(f"{path}:{line_no}: sensitive marker")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Workspace/vault root for output files.")
    parser.add_argument("--text-file", action="append", help="Text file containing copied links or exported messages.")
    parser.add_argument("--text", help="Inline text containing links.")
    parser.add_argument("--url", action="append", default=[], help="Direct URL input; may be repeated.")
    parser.add_argument("--stdin", action="store_true", help="Read additional text from stdin.")
    parser.add_argument("--since", default="", help="Recorded scan window start; filtering exported text is caller-owned.")
    parser.add_argument("--source-channel", default="mobile_share", help="Source label written to inbox files.")
    parser.add_argument("--fetch-html", choices=["never", "auto"], default="never")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    texts = read_inputs(args)
    items = extract_links(texts, args.url)
    run_id = f"{now_local().strftime('%Y%m%d-%H%M%S')}-social-link-intake-{short_hash('|'.join(item.storage_url for item in items), 8)}"
    run_dir = root / ".codex-project" / "outbox" / "social-link-intake" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, str]] = []
    generated: list[Path] = []
    for item in items:
        inbox = write_inbox(root, item, run_id, args.source_channel)
        raw = write_raw(root, item, inbox)
        generated.extend([inbox, raw])
        extracted: Optional[Path] = None
        result = "queued"
        blocker = ""
        if args.fetch_html == "auto":
            html_text, fetch_status = fetch_html(ephemeral_fetch_url_for(item), args.timeout, item.platform)
            if html_text:
                if item.platform == "wechat-article":
                    extracted = write_wechat_extraction(root, item, inbox, html_text)
                    result = "pass"
                elif item.platform == "xhs":
                    extracted = write_xhs_extraction(root, item, inbox, html_text)
                    result = "partial" if "extraction_blocked" in extracted.read_text(encoding="utf-8") else "pass"
                    blocker = "public_html_missing_note_data" if result == "partial" else ""
                generated.append(extracted)
            else:
                result = "partial"
                blocker = fetch_status
        records.append(
            {
                "platform": item.platform,
                "result": result,
                "storage_url": item.storage_url,
                "inbox": relative(inbox, root),
                "raw_source": relative(raw, root),
                "extracted_source": relative(extracted, root) if extracted else "",
                "blocker": blocker,
            }
        )

    report = write_batch_report(root, run_dir, records, args.since)
    generated.extend([report, run_dir / "items.json"])
    findings = validate_no_sensitive_text(generated)
    if findings:
        (run_dir / "privacy-findings.txt").write_text("\n".join(findings) + "\n", encoding="utf-8")
        print(report)
        print("privacy_findings: " + str(len(findings)), file=sys.stderr)
        return 2
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Render a content-first Xiaohongshu video analysis source package.

This script intentionally does not fetch platform pages or media. It combines
privacy-safe metadata, temporary ASR/visual evidence summaries, and a curated
analysis JSON into a durable `raw/social/xhs/` source package.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse


SENSITIVE_MARKERS = [
    "_".join(["xsec", "token"]),
    "wechat" + "Wid",
    "_".join(["share", "id"]),
    "share" + "Red" + "Id",
    "app" + "time",
    "sig" + "n=",
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "-", value)
    return value.strip("-")[:90] or "xhs-video-content-analysis"


def redact_url_query(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def extract_frontmatter_value(text: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", text, re.MULTILINE)
    if not match:
        return ""
    return match.group(1).strip().strip('"').strip("'")


def extract_markdown_field(text: str, label: str) -> str:
    match = re.search(rf"^- {re.escape(label)}:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def metadata_from_source(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    title = ""
    heading = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if heading:
        title = heading.group(1).strip()
    return {
        "title": title or extract_frontmatter_value(text, "title") or "小红书视频内容分析",
        "source_url": redact_url_query(extract_frontmatter_value(text, "source_url")),
        "canonical_url": redact_url_query(extract_frontmatter_value(text, "canonical_url")),
        "note_id": extract_markdown_field(text, "Note ID"),
        "author": extract_markdown_field(text, "Author"),
        "published_at": extract_markdown_field(text, "Published at"),
        "duration": extract_markdown_field(text, "Duration seconds"),
        "local_file": str(path),
    }


def transcript_stats(path: Path | None) -> dict[str, Any]:
    if not path:
        return {"status": "not_provided"}
    data = read_json(path)
    segments = data.get("segments", [])
    return {
        "status": "done",
        "language": data.get("language", "unknown"),
        "segments": len(segments),
        "text_sha1": hashlib.sha1(data.get("text", "").encode("utf-8")).hexdigest(),
        "duration_last_segment": segments[-1].get("end", "") if segments else "",
        "engine_note": "Whisper transcript is used as evidence, but durable output keeps paraphrased notes instead of full transcript.",
    }


def yaml_list(items: list[str]) -> str:
    if not items:
        return "[]"
    return "\n" + "\n".join(f"  - {json.dumps(item, ensure_ascii=False)}" for item in items)


def bullet_list(items: list[str]) -> str:
    if not items:
        return "- None recorded."
    return "\n".join(f"- {item}" for item in items)


def numbered_list(items: list[str]) -> str:
    if not items:
        return "1. None recorded."
    return "\n".join(f"{idx}. {item}" for idx, item in enumerate(items, start=1))


def render_timeline(items: list[dict[str, str]]) -> str:
    if not items:
        return "- No timeline notes recorded."
    rows = []
    for item in items:
        ts = item.get("time", "unknown")
        note = item.get("note", "")
        rows.append(f"- `{ts}`: {note}")
    return "\n".join(rows)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def render_source(
    metadata: dict[str, str],
    transcript: dict[str, Any],
    analysis: dict[str, Any],
    metadata_source_rel: str,
) -> str:
    title = analysis.get("title") or metadata["title"]
    canonical_url = redact_url_query(analysis.get("canonical_url") or metadata["canonical_url"])
    source_url = redact_url_query(analysis.get("source_url") or metadata["source_url"])
    status = analysis.get("analysis_status", {})
    visual = analysis.get("visual_evidence", {})
    reproduction = analysis.get("reproduction_decision", {})
    tags = analysis.get(
        "tags",
        [
            "platform/xhs",
            "source/mobile-share",
            "source/video-content-analysis",
            "status/content-analyzed",
        ],
    )

    frontmatter = [
        "---",
        "source_type: xhs_video_content_analysis",
        "platform: xhs",
        'source_channel: "wechat_file_assistant"',
        f"source_url: {json.dumps(source_url, ensure_ascii=False)}",
        f"canonical_url: {json.dumps(canonical_url, ensure_ascii=False)}",
        f"note_id: {json.dumps(analysis.get('note_id') or metadata.get('note_id'), ensure_ascii=False)}",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"author: {json.dumps(metadata.get('author', ''), ensure_ascii=False)}",
        f"fetched_at: {json.dumps(now_utc())}",
        f"metadata_source: {json.dumps(metadata_source_rel, ensure_ascii=False)}",
        'rights_note: "for personal knowledge review only"',
        "triage_status: content_analyzed",
        f"tags:{yaml_list(tags)}",
        "---",
        "",
    ]

    body = [
        f"# {title}",
        "",
        "## Analysis Status / 分析状态",
        "",
        f"- Metadata extraction: `{status.get('metadata', 'unknown')}`",
        f"- Media acquisition: `{status.get('media_acquisition', 'unknown')}`",
        f"- ASR / transcript: `{status.get('transcript', transcript.get('status', 'unknown'))}`",
        f"- Keyframes / visual observations: `{status.get('visual_observations', 'unknown')}`",
        f"- OCR engine: `{status.get('ocr', 'unknown')}`",
        f"- Content synthesis: `{status.get('synthesis', 'unknown')}`",
        "",
        "## What The Video Is About / 视频讲了什么",
        "",
        analysis.get("content_summary", {}).get("video_topic", "Not recorded."),
        "",
        "## Core Method / 核心方法",
        "",
        analysis.get("content_summary", {}).get("core_method", "Not recorded."),
        "",
        "## Method Steps / 方法步骤",
        "",
        numbered_list(analysis.get("method_steps", [])),
        "",
        "## Actual Cases And Tutorial Clues / 实际案例与教程线索",
        "",
        bullet_list(analysis.get("actual_cases", [])),
        "",
        "## Worth Absorbing / 值得吸收",
        "",
        bullet_list(analysis.get("worth_absorbing", [])),
        "",
        "## Overlap With Soren AI / 与当前体系重合",
        "",
        bullet_list(analysis.get("overlap_with_soren_ai", [])),
        "",
        "## Practical Effect If Adopted / 落地后的实际效果",
        "",
        bullet_list(analysis.get("practical_effect_if_adopted", [])),
        "",
        "## Transcript-Derived Timeline / 转写时间线",
        "",
        render_timeline(analysis.get("timeline_notes", [])),
        "",
        "## Visual Evidence / 视觉证据",
        "",
        f"- Frame extraction: `{visual.get('frame_extraction', 'unknown')}`",
        f"- Frame count reviewed: `{visual.get('frame_count_reviewed', 'unknown')}`",
        f"- OCR status: `{visual.get('ocr_status', 'unknown')}`",
        f"- Visual inspection note: {visual.get('inspection_note', 'not recorded')}",
        "",
        "### Frame Observations / 关键帧观察",
        "",
        render_timeline(visual.get("frame_observations", [])),
        "",
        "## Transcript Evidence Status / 转写证据状态",
        "",
        f"- ASR status: `{transcript.get('status', 'unknown')}`",
        f"- Language: `{transcript.get('language', 'unknown')}`",
        f"- Segment count: `{transcript.get('segments', 'unknown')}`",
        f"- Transcript SHA1: `{transcript.get('text_sha1', 'not-recorded')}`",
        f"- Evidence note: {transcript.get('engine_note', 'not recorded')}",
        "",
        "## Reproduction Decision / 复现决策",
        "",
        f"- Recommendation: `{reproduction.get('recommendation', 'unknown')}`",
        f"- Why: {reproduction.get('why', 'Not recorded.')}",
        "",
        "### Missing Information / 缺失信息",
        "",
        bullet_list(reproduction.get("missing_information", [])),
        "",
        "### Suggested Next Tasks / 建议下一步",
        "",
        bullet_list(reproduction.get("next_tasks", [])),
        "",
        "## What Not To Over-Interpret / 不要过度解读",
        "",
        "- Likes, collections, comments, and author profile are not the content analysis target.",
        "- Engagement can only be used as a weak routing signal for whether a workflow may be worth inspecting.",
        "- This source package does not preserve the video file, audio file, signed stream URL, cookie, or mobile share tracking query.",
        "",
        "## Durable Evidence / 长期证据",
        "",
        f"- Metadata source: `{metadata_source_rel}`",
        f"- Canonical URL: {canonical_url or 'unknown'}",
        f"- Note ID: `{analysis.get('note_id') or metadata.get('note_id') or 'unknown'}`",
        f"- Duration seconds: `{metadata.get('duration') or 'unknown'}`",
        "- Temporary media and HTML snapshots must be deleted after validation.",
        "",
    ]
    rendered = "\n".join(frontmatter + body) + "\n"
    assert_no_sensitive_markers(rendered)
    return rendered


def assert_no_sensitive_markers(text: str) -> None:
    lowered = text.lower()
    for marker in SENSITIVE_MARKERS:
        if marker.lower() in lowered:
            raise ValueError(f"Sensitive marker would be written: {marker}")
    if re.search(r"xhs[cdn-]*\.com/[^\s)>\"]+\?[^\\s)>\"]+", text, re.IGNORECASE):
        raise ValueError("Signed or query-bearing XHS media URL would be written")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--metadata-source", required=True)
    parser.add_argument("--analysis-json", required=True)
    parser.add_argument("--transcript-json", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    metadata_path = Path(args.metadata_source)
    if not metadata_path.is_absolute():
        metadata_path = root / metadata_path
    analysis_path = Path(args.analysis_json)
    transcript_path = Path(args.transcript_json) if args.transcript_json else None

    metadata = metadata_from_source(metadata_path)
    transcript = transcript_stats(transcript_path)
    analysis = read_json(analysis_path)

    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
    else:
        date = dt.date.today().isoformat()
        output = root / "raw" / "social" / "xhs" / f"{slugify(analysis.get('title') or metadata['title'])}-content-analysis-{date}.md"

    metadata_source_rel = str(metadata_path.relative_to(root)) if metadata_path.is_relative_to(root) else str(metadata_path)
    rendered = render_source(metadata, transcript, analysis, metadata_source_rel)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)

#!/usr/bin/env python3
"""Synthetic smoke tests for the social-link-intake skill."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
INTAKE_SCRIPT = SCRIPT_DIR / "social_link_intake.py"
XHS_PROBE_SCRIPT = SCRIPT_DIR / "xhs_public_probe.mjs"
XHS_MEDIA_EVIDENCE_SCRIPT = SCRIPT_DIR / "xhs_media_evidence.mjs"
XHS_RENDER_SCRIPT = SCRIPT_DIR / "xhs_video_content_analysis.py"
SENSITIVE_NEEDLES = [
    "xsec_token=",
    "share_id=",
    "wechatWid=",
    "shareRedId=",
    "app_platform=",
    "app_version=",
    "xhscdn",
    "masterUrl",
    "url_ref",
    "cookie=",
    "authorization:",
    "set-cookie",
    "token=",
    "sig=",
    "sign=",
    "signature=",
]


def load_intake_module():
    spec = importlib.util.spec_from_file_location("social_link_intake", INTAKE_SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load social_link_intake.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def assert_no_sensitive(root: Path) -> None:
    hits: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lowered = text.lower()
        for needle in SENSITIVE_NEEDLES:
            if needle.lower() in lowered:
                hits.append(f"{path}: {needle}")
    if hits:
        raise AssertionError("sensitive marker persisted:\n" + "\n".join(hits))


def test_cli_redacts_xhs_query() -> None:
    with tempfile.TemporaryDirectory(prefix="social-link-intake-smoke.") as tmp:
        root = Path(tmp)
        text = (
            "公众号 https://mp.weixin.qq.com/s/exampleArticle\n"
            "小红书 https://www.xiaohongshu.com/explore/abc123?"
            "xsec_token=secret&share_id=abc&wechatWid=wid&app_platform=android"
        )
        result = subprocess.run(
            [
                sys.executable,
                str(INTAKE_SCRIPT),
                "--root",
                str(root),
                "--text",
                text,
                "--fetch-html",
                "never",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr or result.stdout)
        assert (root / ".codex-project" / "inbox" / "mobile-share").exists()
        assert (root / ".raw" / "social" / "xhs").exists()
        assert_no_sensitive(root)


def test_xhs_metadata_sanitizer() -> None:
    module = load_intake_module()
    with tempfile.TemporaryDirectory(prefix="social-link-intake-xhs-meta.") as tmp:
        root = Path(tmp)
        inbox = root / ".codex-project" / "inbox" / "mobile-share" / "sample.md"
        inbox.parent.mkdir(parents=True)
        inbox.write_text("sample", encoding="utf-8")
        item = module.LinkItem(
            original_url="https://www.xiaohongshu.com/explore/abc123?xsec_token=secret",
            storage_url="https://www.xiaohongshu.com/explore/abc123",
            platform="xhs",
        )
        fake_html = (
            '<script>window.__SETUP_SERVER_STATE__={"LAUNCHER_SSR_STORE_PAGE_DATA":'
            '{"noteData":{"title":"demo https://example.com/a?token=secret",'
            '"displayTitle":"demo",'
            '"desc":"see https://www.xiaohongshu.com/explore/abc123?xsec_token=secret&share_id=abc and https://cdn.example.com/a?sig=secret",'
            '"type":"video"}}}</script>'
        )
        output = module.write_xhs_extraction(root, item, inbox, fake_html)
        assert output.exists()
        assert_no_sensitive(root)


def test_xhs_ephemeral_fetch_url_is_not_durable() -> None:
    module = load_intake_module()
    secret_param = "xsec" + "_token"
    original = f"https://www.xiaohongshu.com/explore/abc123?{secret_param}=secret&share_id=abc"
    item = module.LinkItem(
        original_url=original,
        storage_url="https://www.xiaohongshu.com/explore/abc123",
        platform="xhs",
    )
    assert module.ephemeral_fetch_url_for(item) == original
    with tempfile.TemporaryDirectory(prefix="social-link-intake-xhs-ephemeral.") as tmp:
        root = Path(tmp)
        inbox = module.write_inbox(root, item, "run", "mobile_share")
        raw = module.write_raw(root, item, inbox)
        assert inbox.exists()
        assert raw.exists()
        assert_no_sensitive(root)


def test_xhs_video_content_renderer() -> None:
    with tempfile.TemporaryDirectory(prefix="social-link-intake-xhs-render.") as tmp:
        root = Path(tmp)
        metadata = root / "raw" / "social" / "xhs" / "metadata.md"
        metadata.parent.mkdir(parents=True)
        metadata.write_text(
            """---
source_url: "https://www.xiaohongshu.com/explore/abc123"
canonical_url: "https://www.xiaohongshu.com/discovery/item/abc123"
---

# 测试小红书视频

## Metadata

- Note ID: abc123
- Author: 测试作者
- Duration seconds: 60
""",
            encoding="utf-8",
        )
        analysis = root / "analysis.json"
        analysis.write_text(
            """{
  "title": "测试视频内容分析",
  "note_id": "abc123",
  "analysis_status": {
    "metadata": "done",
    "media_acquisition": "done_temporary",
    "transcript": "done",
    "visual_observations": "done",
    "ocr": "unavailable",
    "synthesis": "done"
  },
  "content_summary": {
    "video_topic": "演示如何把一个社交视频拆成可复现方法。",
    "core_method": "先提取内容证据，再判断是否进入复现。"
  },
  "method_steps": ["读取视频内容", "拆方法", "判断复现"],
  "actual_cases": ["示例案例"],
  "worth_absorbing": ["内容优先，不用互动数据代替视频理解。"],
  "overlap_with_soren_ai": ["与移动端分享入口重合。"],
  "practical_effect_if_adopted": ["能把外部视频变成可判断任务。"],
  "timeline_notes": [{"time": "00:00-00:10", "note": "开场说明教程目标。"}],
  "visual_evidence": {
    "frame_extraction": "done",
    "frame_count_reviewed": 1,
    "ocr_status": "unavailable",
    "inspection_note": "人工视觉观察。",
    "frame_observations": [{"time": "00:00", "note": "画面显示教程页。"}]
  },
  "reproduction_decision": {
    "recommendation": "light_validation",
    "why": "线索足够做小验证。",
    "missing_information": ["缺完整代码"],
    "next_tasks": ["创建最小验证任务"]
  }
}""",
            encoding="utf-8",
        )
        transcript = root / "transcript.json"
        transcript.write_text(
            """{"language":"Chinese","text":"测试转写","segments":[{"start":0,"end":10,"text":"测试转写"}]}""",
            encoding="utf-8",
        )
        output = root / "raw" / "social" / "xhs" / "content.md"
        result = subprocess.run(
            [
                sys.executable,
                str(XHS_RENDER_SCRIPT),
                "--root",
                str(root),
                "--metadata-source",
                "raw/social/xhs/metadata.md",
                "--analysis-json",
                str(analysis),
                "--transcript-json",
                str(transcript),
                "--output",
                "raw/social/xhs/content.md",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr or result.stdout)
        text = output.read_text(encoding="utf-8")
        assert "## What The Video Is About / 视频讲了什么" in text
        assert "## Worth Absorbing / 值得吸收" in text
        assert "Recommendation: `light_validation`" in text
        assert_no_sensitive(root)


def test_xhs_public_probe_synthetic_html() -> None:
    if not XHS_PROBE_SCRIPT.exists():
        raise AssertionError("missing xhs_public_probe.mjs")
    text = XHS_PROBE_SCRIPT.read_text(encoding="utf-8")
    assert "masterUrl" in text
    assert "present_redacted" in text
    assert "assertSafeResult" in text


def test_xhs_media_evidence_script_safety_contract() -> None:
    if not XHS_MEDIA_EVIDENCE_SCRIPT.exists():
        raise AssertionError("missing xhs_media_evidence.mjs")
    text = XHS_MEDIA_EVIDENCE_SCRIPT.read_text(encoding="utf-8")
    assert "ffprobe" in text
    assert "ffmpeg" in text
    assert "downloaded_temporary_deleted_after_run" in text
    assert "used_temporarily_redacted" in text
    assert "retained_files" in text
    assert "assertSafeResult" in text


def main() -> int:
    test_cli_redacts_xhs_query()
    test_xhs_metadata_sanitizer()
    test_xhs_ephemeral_fetch_url_is_not_durable()
    test_xhs_video_content_renderer()
    test_xhs_public_probe_synthetic_html()
    test_xhs_media_evidence_script_safety_contract()
    print("social-link-intake smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

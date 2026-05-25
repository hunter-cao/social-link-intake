# Social Link Intake / 社交链接入口

Privacy-safe intake and first-pass extraction tools for mobile-shared social links, especially WeChat public-account articles and Xiaohongshu/Rednote links.

这个包解决的是一个很具体的 Agent 工作流问题：用户在手机上看到外部材料，把链接转发/复制给 Agent 入口后，Agent 需要先安全接收、去敏、判断是否真的读到了内容，再进入知识库关联、复现验证或任务派发。

## What It Does / 它能做什么

- Capture supported links from text batches or mobile-share exports.
- Store durable evidence packages without Xiaohongshu tracking query strings, cookies, signed media URLs, chat exports, raw media, or full transcripts.
- Extract readable public WeChat article metadata and bounded excerpts.
- Probe Xiaohongshu public HTML for safe SSR `noteData` and redacted stream metadata.
- Render a durable Xiaohongshu video analysis package from already-produced temporary ASR/keyframe/OCR evidence.
- Hand off readable sources into relevance screening with progressive context reading.

## What It Does Not Claim / 它不声称什么

- It does not bypass platform authentication.
- It does not store or publish signed media URLs.
- It does not keep downloaded videos, audio, keyframes, or full transcripts.
- A Xiaohongshu link is not treated as content evidence until metadata, ASR, OCR, screenshots, keyframes, or trusted exported text are available.

## Layout / 目录

```text
social-link-intake/
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── privacy-boundary.md
│   ├── relevance-handoff.md
│   └── xhs-content-analysis.md
└── scripts/
    ├── social_link_intake.py
    ├── xhs_public_probe.mjs
    ├── xhs_video_content_analysis.py
    └── smoke_test.py
```

## Quick Start / 快速开始

Run intake on copied links:

```bash
python3 scripts/social_link_intake.py \
  --root /path/to/workspace-or-vault \
  --text "公众号 https://mp.weixin.qq.com/s/exampleArticle 小红书 https://www.xiaohongshu.com/explore/abc123?xsec_token=secret" \
  --fetch-html never
```

Probe a Xiaohongshu link from an always-on entry machine:

```bash
node scripts/xhs_public_probe.mjs --url "http://xhslink.com/o/example"
```

The probe output is intentionally redacted and should only be used as routing evidence. If it reports stream metadata, the next stage can use temporary media download, ASR/no-audio detection, keyframe extraction, and then `xhs_video_content_analysis.py` to produce durable analysis.

Extract temporary media evidence when `ffmpeg` / `ffprobe` are available:

```bash
node scripts/xhs_media_evidence.mjs --url "http://xhslink.com/o/example"
```

This downloads media only to the system temp directory, extracts safe audio/keyframe evidence, and deletes temporary files by default. Durable output contains hashes, counts, stream status, and next actions, not signed media URLs or media files.

## Validation / 验证

```bash
python3 scripts/smoke_test.py
node --check scripts/xhs_public_probe.mjs
node --check scripts/xhs_media_evidence.mjs
python3 -m py_compile scripts/social_link_intake.py scripts/xhs_video_content_analysis.py scripts/smoke_test.py
```

If local Python tries to write pycache outside your workspace, redirect it:

```bash
PYTHONPYCACHEPREFIX=/tmp/social-link-intake-pycache \
  python3 -m py_compile scripts/social_link_intake.py scripts/xhs_video_content_analysis.py scripts/smoke_test.py
```

## Privacy Boundary / 隐私边界

Durable outputs may store canonical URLs, statuses, hashes, counts, summaries, and paraphrased evidence. They must not store platform credentials, full share queries, signed media URLs, raw chat history, downloaded media, or full transcripts.

See [references/privacy-boundary.md](references/privacy-boundary.md).

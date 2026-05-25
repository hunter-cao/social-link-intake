---
name: social-link-intake
description: Privacy-safe intake and first-pass extraction for social links shared from mobile contexts, especially WeChat public-account articles and Xiaohongshu/Rednote links. Use when Codex is given copied links, a WeChat File Transfer export, or a batch of mp.weixin.qq.com / xiaohongshu.com / xhslink.com URLs and needs to create sanitized inbox/raw packages, extract readable WeChat article text, flag blocked Xiaohongshu content without hallucinating video content, and hand the result to relevance screening.
---

# Social Link Intake

## Purpose / 用途

Turn mobile-shared social links into durable, privacy-safe evidence packages:

```text
links or export text -> sanitized inbox -> raw source -> platform extraction -> batch report -> relevance-ready decision
```

This skill is an intake layer, not a full recommender. It must separate "link was captured" from "content was actually read".

## Workflow / 工作流

1. Capture only supported links:
   - WeChat public articles: `mp.weixin.qq.com`
   - Xiaohongshu/Rednote: `xiaohongshu.com`, `xhslink.com`
2. Redact Xiaohongshu query strings before durable storage.
3. Create inbox/raw packages with source URL, capture channel, privacy notes, and extraction status.
4. Fetch public HTML only when the user or task asks for extraction.
5. For WeChat articles, extract title, account, description, deterministic key points, and a bounded body excerpt from the article HTML.
6. For Xiaohongshu, use public HTML only as a probe. Durable files must keep the canonical, query-stripped URL, but the original mobile share URL may be used ephemerally for fetching because it can expose SSR `noteData` that the canonical URL does not expose. Never write that ephemeral URL to reports or raw packages.
7. If Xiaohongshu note data is available, treat it as routing/metadata evidence. For true content reading, continue to temporary media, ASR, keyframes, screenshots, or exported text.
8. If note data, media, ASR, OCR, or keyframes are not available, write `extraction_blocked` and say clearly that the video/content has not been read.
9. Run relevance screening after extraction, using tags and progressive context disclosure. Do not read whole projects up front.

For Xiaohongshu video or image posts that must be understood as content, continue with `references/xhs-content-analysis.md`. Intake alone is not enough.

## Use The Bundled Script / 使用脚本

For a neutral, publishable intake run:

```bash
python3 scripts/social_link_intake.py \
  --root /path/to/vault-or-workspace \
  --text-file /path/to/links.txt \
  --fetch-html auto
```

Outputs are created under the chosen root:

```text
.codex-project/inbox/mobile-share/
.raw/social/wechat-article/
.raw/social/xhs/
.codex-project/outbox/social-link-intake/<run-id>/
```

Use `--fetch-html never` when the task is only to sanitize and queue links.

For an always-on Windows OpenClaw host, use the Node public probe before any
media work:

```bash
node scripts/xhs_public_probe.mjs --url "http://xhslink.com/o/..."
```

The probe may be run on Windows without Python. It returns only redacted status,
safe metadata, and whether stream metadata exists. It must not write HTML,
signed media URLs, media files, frames, audio, or transcripts.

## Reading Rules / 读取规则

- Treat WeChat extracted article text as readable evidence.
- Treat Xiaohongshu public metadata as routing evidence only unless the media/content itself has been read through ASR, OCR, screenshot analysis, keyframes, or a trusted exported text source.
- For Xiaohongshu video or image-note content analysis, classify the evidence path explicitly: `video_asr_keyframes_done`, `video_no_audio_keyframes_done`, `image_note_contact_sheet_done`, `metadata_only`, or `extraction_blocked`.
- Ignore likes, collections, author profile, and engagement as decision evidence unless the user explicitly asks for popularity analysis.
- If extraction is blocked, preserve the blocker and stop. Do not infer the content from the note ID, title-shaped URL text, comments, or previous unrelated examples.

## Privacy Boundary / 隐私边界

Always avoid durable storage of:

- full Xiaohongshu share query strings
- signed platform media URLs
- cookies, account tokens, local chat databases, and contact lists
- full WeChat chat exports
- video/audio files and full transcripts unless the user explicitly provides them for analysis

See `references/privacy-boundary.md` for the denylist and validation pattern.

## Relevance Handoff / 关联筛选交接

After intake, produce or request a relevance bridge with these bilingual sections:

- `Source Snapshot / 来源快照`
- `Routing Tags / 路由标签`
- `Context Read Ledger / 上下文读取记录`
- `Claim / Method Units / 主张与方法单元`
- `Worth Absorbing / 值得吸收`
- `Overlap With Target System / 与目标系统现状重合`
- `Real Gap / 真实缺口`
- `Practical Effect If Adopted / 采用后的实际效果`
- `Minimum Validation / 最小验证`
- `Do Not Copy / 不要照搬`
- `Decision / 决策`

Use `references/relevance-handoff.md` when writing a bridge or batch summary.

Use `references/xhs-content-analysis.md` when a Xiaohongshu item should be analyzed for methods, examples, tutorial steps, ASR/OCR, or visual evidence.

## Durable Content Renderer / 持久内容渲染器

When temporary ASR/keyframe/OCR evidence has already been produced, render a
privacy-safe Markdown analysis package with:

```bash
python3 scripts/xhs_video_content_analysis.py \
  --metadata-source raw/social/xhs/<metadata-source>.md \
  --analysis-json /tmp/<run-id>-analysis.json \
  --transcript-json /tmp/<run-id>-transcript.json
```

This renderer does not fetch media. It only combines sanitized metadata,
paraphrased ASR/visual notes, evidence status, and a reproduction decision into
durable Markdown.

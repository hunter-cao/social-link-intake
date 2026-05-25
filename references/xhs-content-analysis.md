# Xiaohongshu Content Analysis / 小红书内容读取

## Rule / 规则

A Xiaohongshu link is only an entry point. It becomes content evidence only after at least one content-bearing source is available:

- public HTML exposes note content and safe metadata
- user-provided video, screenshot, screen recording, or exported text
- temporary media access that can be processed and cleaned up
- authenticated browser/session extraction explicitly authorized by the user

If none of these exists, mark the item as `partial` or `extraction_blocked` and stop.

## Content-First Workflow / 内容优先链路

For video or image posts, the durable analysis should answer:

- what the post/video says or shows
- what method it teaches
- what actual cases, tutorial steps, or visual examples appear
- what evidence was used: ASR, OCR, keyframes, screenshots, exported text, or public metadata
- whether the user should ask Codex to test, verify, reproduce, dispatch, or archive it

Recommended chain:

1. Use the canonical, query-stripped Xiaohongshu URL for all durable records.
2. Use the original mobile share URL only ephemerally, in memory or under `/private/tmp`, when fetching public HTML. This is often necessary because canonical URLs can hide SSR `noteData`.
3. On Windows/OpenClaw, first run `scripts/xhs_public_probe.mjs` to confirm whether `noteData` and redacted stream metadata are present.
4. If `noteData` is available, extract safe metadata, description, note type, topic tags, duration, media status, and redacted stream metadata.
5. For image notes, download images only to `/private/tmp` or the Windows temp directory, build a temporary contact sheet, read the visual content, then delete the images/contact sheet.
6. For videos, run `scripts/xhs_media_evidence.mjs` when temporary media access is available. It downloads media only to `/private/tmp` or the Windows temp directory, uses ffprobe/ffmpeg to detect audio/video streams, extracts temporary keyframes/audio evidence, and deletes the files after the run.
7. If an audio stream exists, run ASR and keep only segment count, hash, status, and paraphrased timeline notes. If no audio stream exists, use keyframes plus description/comment signals and mark `transcript: no_audio_stream`.
8. Generate the durable `*-content-analysis-YYYY-MM-DD.md` file with `scripts/xhs_video_content_analysis.py` or an equivalent renderer.
9. Delete temporary HTML, media, audio, transcripts, frames, and contact sheets before acceptance.

## Durable Output / 持久产物

Keep only analysis, evidence status, hashes, and paraphrased notes. Do not keep:

- platform media files
- signed media URLs
- full ASR transcripts
- temporary keyframes
- cookies, account identifiers, or tracking query strings

Recommended source package shape:

```text
.raw/social/xhs/<note-or-title>-content-analysis-YYYY-MM-DD.md
```

Required sections:

- `Analysis Status / 分析状态`
- `What The Video Is About / 视频内容`
- `Core Method / 核心方法`
- `Method Steps / 方法步骤`
- `Actual Cases And Tutorial Clues / 案例与教程线索`
- `Worth Absorbing / 值得吸收`
- `Overlap With Target System / 与目标系统现状重合`
- `Practical Effect If Adopted / 采用后的实际效果`
- `Transcript Evidence Status / 转写证据状态`
- `Visual Evidence / 视觉证据`
- `Reproduction Decision / 复现决策`
- `What Not To Over-Interpret / 不要过度解读`

For image notes, use the same sections but label the content as `Note / 笔记` rather than `Video / 视频`, and set the evidence path to `image_note_contact_sheet_done`.

## Blocked Case / 受限情况

When public HTML does not expose note data and no media/screenshot/export is available, write:

```text
result: partial
blocker: public_html_missing_note_data
content_read: false
next_input_needed: user-provided media, screenshot/export, or authorized browser extraction
```

Do not infer content from author, likes, collections, comments, note ID, or previous similar posts.

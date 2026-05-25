# Privacy Boundary / 隐私边界

## Durable Storage Rules / 持久化规则

Store:

- canonical WeChat article URLs
- Xiaohongshu canonical path URLs with query removed
- platform, captured time, source channel, extraction status
- bounded article excerpts and deterministic summaries for public WeChat articles
- blocker evidence when public extraction fails

Do not store:

- Xiaohongshu share query parameters such as security tokens, share IDs, app metadata, account identifiers, or tracking fields
- signed media URLs, CDN URLs with query signatures, cookies, request headers, or account tokens
- full chat exports, contact names beyond the immediate source label, or local WeChat database contents
- downloaded videos, audio tracks, full transcripts, or keyframe images unless the user explicitly provides them for analysis and retention

## Validation Pattern / 验证模式

After a run, scan generated durable folders for sensitive markers. Adapt this pattern to the local project:

```bash
rg -n "xsec|share_id|wechatWid|shareRedId|app_platform|app_version|xhscdn|masterUrl|url_ref|cookie|token" \
  .codex-project/inbox/mobile-share \
  .raw/social \
  .codex-project/outbox/social-link-intake || true
```

Expected result: no hits, except generic words inside this privacy reference if the skill package itself is included in the scan.

## Xiaohongshu Rule / 小红书规则

A Xiaohongshu link is not content evidence by itself. Mark it as blocked unless at least one of these exists:

- exported note text
- screenshots/OCR
- video/audio provided by the user
- ASR transcript created from user-provided media
- keyframes or visual analysis created from user-provided media
- authenticated browser extraction explicitly authorized by the user

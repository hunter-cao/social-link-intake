#!/usr/bin/env node
/**
 * Privacy-safe Xiaohongshu public page probe.
 *
 * This script is intended for always-on entry machines such as a Windows
 * OpenClaw host. It checks whether a Xiaohongshu/xhslink URL exposes SSR
 * noteData and redacted media metadata. It does not print or write signed
 * media URLs, cookies, query strings, HTML snapshots, video, audio, frames, or
 * transcripts.
 */

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";

const URL_RE = /^https?:\/\/.+/i;
const XHS_RE = /(?:xiaohongshu\.com|xhslink\.com)/i;
const SENSITIVE_KEY_RE = /(xsec|token|share_id|wechatwid|shareredid|app_platform|app_version|apptime|masterurl|backupurls|url_ref|cookie|sign|signature)/i;

function parseArgs(argv) {
  const args = {
    url: "",
    urlStdin: false,
    output: "",
    keepTemp: false,
    timeoutMs: 20000,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = () => {
      index += 1;
      if (index >= argv.length) throw new Error(`Missing value for ${arg}`);
      return argv[index];
    };
    if (arg === "--url") args.url = next();
    else if (arg === "--url-stdin") args.urlStdin = true;
    else if (arg === "--output") args.output = next();
    else if (arg === "--keep-temp") args.keepTemp = true;
    else if (arg === "--timeout-ms") args.timeoutMs = Number(next());
    else if (arg === "-h" || arg === "--help") {
      printHelp();
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (!args.urlStdin && (!URL_RE.test(args.url) || !XHS_RE.test(args.url))) {
    throw new Error("--url must be a Xiaohongshu/xhslink URL");
  }
  return args;
}

function printHelp() {
  console.log(`Usage:
  node scripts/xhs_public_probe.mjs --url <xhs-url> [--output result.json]
  printf '%s' '<xhs-url>' | node scripts/xhs_public_probe.mjs --url-stdin

The result is a redacted JSON status object. It is safe to store as evidence.`);
}

async function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => resolve(data.trim()));
    process.stdin.on("error", reject);
  });
}

function canonicalUrl(rawUrl) {
  const url = new URL(rawUrl);
  url.search = "";
  url.hash = "";
  return url.toString();
}

function sha1(value) {
  return crypto.createHash("sha1").update(value).digest("hex");
}

async function fetchHtml(rawUrl, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(rawUrl, {
      redirect: "follow",
      signal: controller.signal,
      headers: {
        "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      },
    });
    const text = await response.text();
    return {
      ok: response.ok,
      status: response.status,
      final_url: response.url ? canonicalUrl(response.url) : "",
      html: text,
    };
  } finally {
    clearTimeout(timer);
  }
}

function jsonAfterMarker(text, marker) {
  const start = text.indexOf(marker);
  if (start < 0) return {};
  const decoderText = text.slice(start + marker.length);
  try {
    return JSON.parse(decoderText);
  } catch {
    const trimmed = decoderText.trim();
    let depth = 0;
    let inString = false;
    let escape = false;
    for (let i = 0; i < trimmed.length; i += 1) {
      const ch = trimmed[i];
      if (escape) {
        escape = false;
        continue;
      }
      if (ch === "\\") {
        escape = true;
        continue;
      }
      if (ch === "\"") inString = !inString;
      if (inString) continue;
      if (ch === "{") depth += 1;
      if (ch === "}") {
        depth -= 1;
        if (depth === 0) {
          try {
            return JSON.parse(trimmed.slice(0, i + 1));
          } catch {
            return {};
          }
        }
      }
    }
  }
  return {};
}

function getByPath(value, keys) {
  let current = value;
  for (const key of keys) {
    if (!current || typeof current !== "object") return undefined;
    current = current[key];
  }
  return current;
}

function redactForStorage(value) {
  if (value === undefined || value === null) return "";
  let text = String(value);
  text = text.replace(/https?:\/\/[^\s"')>]+/gi, (raw) => {
    try {
      const parsed = new URL(raw);
      parsed.search = "";
      parsed.hash = "";
      return parsed.toString();
    } catch {
      return "[redacted-url]";
    }
  });
  text = text.replace(/\b(?:xsec[_-]?token|share_id|wechatwid|shareredid|app_platform|app_version|apptime|token|sign|signature)=\S+/gi, "[redacted-param]");
  return text.slice(0, 500);
}

function summarizeStreams(note) {
  const stream = getByPath(note, ["video", "media", "stream"]) || {};
  const streams = [];
  for (const codec of Object.keys(stream)) {
    const items = Array.isArray(stream[codec]) ? stream[codec] : [];
    for (const item of items) {
      streams.push({
        codec,
        format: item.format || "",
        quality: item.qualityType || item.quality || "",
        width: item.width || "",
        height: item.height || "",
        duration_ms: item.duration || "",
        size: item.size || "",
        media_url_status: item.masterUrl || item.master_url ? "present_redacted" : "not_present",
      });
    }
  }
  return streams.slice(0, 12);
}

function buildResult(rawUrl, fetched) {
  const state = jsonAfterMarker(fetched.html, "window.__SETUP_SERVER_STATE__=");
  const pageData = getByPath(state, ["LAUNCHER_SSR_STORE_PAGE_DATA"]) || {};
  const note = pageData.noteData || {};
  const hasNoteData = Boolean(note && typeof note === "object" && Object.keys(note).length > 0);
  const noteId = note.noteId || new URL(canonicalUrl(fetched.final_url || rawUrl)).pathname.split("/").filter(Boolean).pop() || "";
  const streams = hasNoteData ? summarizeStreams(note) : [];
  return {
    ok: Boolean(fetched.ok && hasNoteData),
    fetched_at: new Date().toISOString(),
    source_url: canonicalUrl(rawUrl),
    final_url: canonicalUrl(fetched.final_url || rawUrl),
    html_sha1: sha1(fetched.html),
    html_length: fetched.html.length,
    http_status: fetched.status,
    has_setup_state: fetched.html.includes("__SETUP_SERVER_STATE__"),
    has_note_data: hasNoteData,
    has_media_stream_metadata: streams.length > 0,
    note_id: redactForStorage(noteId),
    title: redactForStorage(note.title || note.displayTitle || ""),
    description_present: Boolean(note.desc),
    content_type: redactForStorage(note.type || ""),
    duration_seconds: getByPath(note, ["video", "capa", "duration"]) || getByPath(note, ["video", "media", "video", "duration"]) || "",
    media_md5_present: Boolean(getByPath(note, ["video", "media", "video", "md5"])),
    stream_references: streams,
    content_read_status: "metadata_only",
    next_actions: streams.length > 0
      ? ["temporary_media_download", "asr_or_no_audio_detection", "keyframe_extraction", "content_analysis_render"]
      : ["content_export_or_authenticated_extraction_needed"],
  };
}

function assertSafeResult(result) {
  const text = JSON.stringify(result);
  if (SENSITIVE_KEY_RE.test(text)) {
    throw new Error("Sensitive marker would be written to probe result");
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.urlStdin) {
    args.url = await readStdin();
  }
  if (!URL_RE.test(args.url) || !XHS_RE.test(args.url)) {
    throw new Error("--url must be a Xiaohongshu/xhslink URL");
  }
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "soren-xhs-probe-"));
  try {
    const fetched = await fetchHtml(args.url, args.timeoutMs);
    const result = buildResult(args.url, fetched);
    assertSafeResult(result);
    const rendered = `${JSON.stringify(result, null, 2)}\n`;
    if (args.output) {
      await fs.mkdir(path.dirname(path.resolve(args.output)), { recursive: true });
      await fs.writeFile(args.output, rendered, "utf8");
    }
    process.stdout.write(rendered);
    return result.has_note_data ? 0 : 2;
  } finally {
    if (!args.keepTemp) await fs.rm(tempDir, { recursive: true, force: true }).catch(() => undefined);
  }
}

main().then((code) => process.exit(code)).catch((error) => {
  console.error(error.message || String(error));
  process.exit(1);
});

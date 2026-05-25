#!/usr/bin/env node
/**
 * Temporary Xiaohongshu media evidence extractor.
 *
 * This script may fetch platform HTML and a video stream into a temp directory,
 * then uses ffprobe/ffmpeg to collect content-bearing evidence status. It never
 * writes signed media URLs, HTML snapshots, video files, audio files, frames, or
 * transcripts to durable output. Default behavior deletes all temporary files.
 */

import crypto from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const URL_RE = /^https?:\/\/.+/i;
const XHS_RE = /(?:xiaohongshu\.com|xhslink\.com)/i;
const SENSITIVE_RE = /(xsec|token|share_id|wechatwid|shareredid|app_platform|app_version|apptime|masterurl|backupurls|url_ref|cookie|sign|signature|xhscdn|sns-video)/i;

function parseArgs(argv) {
  const args = {
    url: "",
    urlStdin: false,
    output: "",
    keepTemp: false,
    timeoutMs: 30000,
    maxBytes: 60 * 1024 * 1024,
    frameCount: 6,
    ffmpeg: process.env.FFMPEG_PATH || "",
    ffprobe: process.env.FFPROBE_PATH || "",
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
    else if (arg === "--max-bytes") args.maxBytes = Number(next());
    else if (arg === "--frame-count") args.frameCount = Number(next());
    else if (arg === "--ffmpeg") args.ffmpeg = next();
    else if (arg === "--ffprobe") args.ffprobe = next();
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
  node scripts/xhs_media_evidence.mjs --url <xhs-url> [--output evidence.json]
  printf '%s' '<xhs-url>' | node scripts/xhs_media_evidence.mjs --url-stdin

Requires ffmpeg/ffprobe, either on PATH, via FFMPEG_PATH/FFPROBE_PATH, or via
ffmpeg-static + ffprobe-static installed near this script.`);
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

function sha1Buffer(buffer) {
  return crypto.createHash("sha1").update(buffer).digest("hex");
}

async function sha1File(filePath) {
  return sha1Buffer(await fs.readFile(filePath));
}

async function resolveToolPath(name, configured, required = true) {
  if (configured) return configured;
  if (name === "ffmpeg") {
    try {
      const value = require("ffmpeg-static");
      if (typeof value === "string") return value;
    } catch {}
  }
  if (name === "ffprobe") {
    try {
      const value = require("ffprobe-static");
      if (value?.path) return value.path;
    } catch {}
  }
  if (required) return name;
  return "";
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
    return {
      ok: response.ok,
      status: response.status,
      final_url: response.url ? canonicalUrl(response.url) : "",
      html: await response.text(),
    };
  } finally {
    clearTimeout(timer);
  }
}

function jsonAfterMarker(text, marker) {
  const start = text.indexOf(marker);
  if (start < 0) return {};
  const trimmed = text.slice(start + marker.length).trim();
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

function streamCandidates(note) {
  const stream = getByPath(note, ["video", "media", "stream"]) || {};
  const candidates = [];
  for (const codec of Object.keys(stream)) {
    const items = Array.isArray(stream[codec]) ? stream[codec] : [];
    for (const item of items) {
      const mediaUrl = item.masterUrl || item.master_url || "";
      if (!mediaUrl) continue;
      candidates.push({
        codec,
        format: item.format || "",
        quality: item.qualityType || item.quality || "",
        width: item.width || "",
        height: item.height || "",
        duration_ms: item.duration || "",
        size: Number(item.size || 0),
        mediaUrl,
      });
    }
  }
  return candidates.sort((a, b) => Number(a.size || 0) - Number(b.size || 0));
}

async function downloadToTemp(mediaUrl, filePath, maxBytes, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(mediaUrl, {
      redirect: "follow",
      signal: controller.signal,
      headers: {
        "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
        "referer": "https://www.xiaohongshu.com/",
      },
    });
    if (!response.ok) throw new Error(`media_http_${response.status}`);
    const reader = response.body.getReader();
    const chunks = [];
    let total = 0;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxBytes) throw new Error("media_exceeds_max_bytes");
      chunks.push(Buffer.from(value));
    }
    const buffer = Buffer.concat(chunks);
    await fs.writeFile(filePath, buffer);
    return {
      size_bytes: buffer.length,
      sha1: sha1Buffer(buffer),
    };
  } finally {
    clearTimeout(timer);
  }
}

function runTool(command, args, timeoutMs) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
    }, timeoutMs);
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code === 0) resolve({ stdout, stderr });
      else reject(new Error(stderr || stdout || `${command} exited ${code}`));
    });
  });
}

async function ffprobeJson(ffprobe, mediaPath, timeoutMs) {
  if (!ffprobe) {
    return { streams: [], format: {}, probe_status: "ffprobe_unavailable" };
  }
  const { stdout } = await runTool(ffprobe, [
    "-v", "error",
    "-print_format", "json",
    "-show_format",
    "-show_streams",
    mediaPath,
  ], timeoutMs);
  return JSON.parse(stdout);
}

async function ffmpegMediaInfo(ffmpeg, mediaPath, timeoutMs) {
  try {
    const { stderr } = await runTool(ffmpeg, ["-hide_banner", "-i", mediaPath, "-f", "null", "-"], timeoutMs);
    return stderr;
  } catch (error) {
    return String(error.message || error);
  }
}

async function extractFrames(ffmpeg, mediaPath, framesDir, frameCount, durationSeconds, timeoutMs) {
  await fs.mkdir(framesDir, { recursive: true });
  const fps = durationSeconds > 0 ? Math.max(0.02, frameCount / durationSeconds) : 0.05;
  await runTool(ffmpeg, [
    "-hide_banner",
    "-loglevel", "error",
    "-i", mediaPath,
    "-vf", `fps=${fps},scale='min(720,iw)':-2`,
    "-frames:v", String(frameCount),
    path.join(framesDir, "frame-%03d.jpg"),
  ], timeoutMs);
  const files = (await fs.readdir(framesDir)).filter((name) => name.endsWith(".jpg")).sort();
  const hashes = [];
  for (const file of files) {
    const filePath = path.join(framesDir, file);
    const stat = await fs.stat(filePath);
    hashes.push({
      index: hashes.length + 1,
      sha1: await sha1File(filePath),
      size_bytes: stat.size,
    });
  }
  return hashes;
}

async function extractAudioEvidence(ffmpeg, mediaPath, audioPath, hasAudio, timeoutMs) {
  if (!hasAudio) return { status: "no_audio_stream" };
  try {
    await runTool(ffmpeg, [
      "-hide_banner",
      "-loglevel", "error",
      "-i", mediaPath,
      "-vn",
      "-ac", "1",
      "-ar", "16000",
      "-t", "600",
      audioPath,
    ], timeoutMs);
    const stat = await fs.stat(audioPath);
    return {
      status: "audio_extracted_temporary",
      sha1: await sha1File(audioPath),
      size_bytes: stat.size,
      next_action: "asr_required",
    };
  } catch (error) {
    return {
      status: "audio_extract_failed",
      error: String(error.message || error).slice(0, 160),
    };
  }
}

function safeStreamSummary(candidate) {
  return {
    codec: candidate.codec,
    format: candidate.format,
    quality: candidate.quality,
    width: candidate.width,
    height: candidate.height,
    duration_ms: candidate.duration_ms,
    size: candidate.size,
    media_url_status: "used_temporarily_redacted",
  };
}

function assertSafeResult(result) {
  const text = JSON.stringify(result);
  if (SENSITIVE_RE.test(text)) {
    throw new Error("Sensitive marker would be written to media evidence result");
  }
}

async function buildEvidence(args, tempDir) {
  const ffmpeg = await resolveToolPath("ffmpeg", args.ffmpeg, true);
  const ffprobe = await resolveToolPath("ffprobe", args.ffprobe, false);
  const fetched = await fetchHtml(args.url, args.timeoutMs);
  const state = jsonAfterMarker(fetched.html, "window.__SETUP_SERVER_STATE__=");
  const note = getByPath(state, ["LAUNCHER_SSR_STORE_PAGE_DATA", "noteData"]) || {};
  if (!note || typeof note !== "object" || Object.keys(note).length === 0) {
    return {
      ok: false,
      source_url: canonicalUrl(args.url),
      final_url: canonicalUrl(fetched.final_url || args.url),
      http_status: fetched.status,
      has_note_data: false,
      media_acquisition_status: "blocked_no_note_data",
      content_read_status: "extraction_blocked",
    };
  }
  const candidates = streamCandidates(note);
  if (candidates.length === 0) {
    return {
      ok: false,
      source_url: canonicalUrl(args.url),
      final_url: canonicalUrl(fetched.final_url || args.url),
      http_status: fetched.status,
      has_note_data: true,
      has_media_stream_metadata: false,
      media_acquisition_status: "blocked_no_stream_metadata",
      content_read_status: "metadata_only",
    };
  }
  const chosen = candidates[0];
  const mediaPath = path.join(tempDir, "media.mp4");
  const audioPath = path.join(tempDir, "audio.wav");
  const framesDir = path.join(tempDir, "frames");
  const media = await downloadToTemp(chosen.mediaUrl, mediaPath, args.maxBytes, args.timeoutMs);
  const probe = await ffprobeJson(ffprobe, mediaPath, args.timeoutMs);
  const fallbackInfo = probe.probe_status ? await ffmpegMediaInfo(ffmpeg, mediaPath, args.timeoutMs) : "";
  const streams = Array.isArray(probe.streams) ? probe.streams : [];
  const videoStreams = streams.filter((stream) => stream.codec_type === "video");
  const audioStreams = streams.filter((stream) => stream.codec_type === "audio");
  const fallbackHasVideo = /Video:/i.test(fallbackInfo);
  const fallbackHasAudio = /Audio:/i.test(fallbackInfo);
  const durationSeconds = Number(probe.format?.duration || 0) || Number(chosen.duration_ms || 0) / 1000 || 0;
  const frameEvidence = await extractFrames(ffmpeg, mediaPath, framesDir, args.frameCount, durationSeconds, args.timeoutMs);
  const hasAudio = audioStreams.length > 0 || fallbackHasAudio;
  const audioEvidence = await extractAudioEvidence(ffmpeg, mediaPath, audioPath, hasAudio, args.timeoutMs);
  return {
    ok: true,
    fetched_at: new Date().toISOString(),
    source_url: canonicalUrl(args.url),
    final_url: canonicalUrl(fetched.final_url || args.url),
    http_status: fetched.status,
    note_id: String(note.noteId || "").slice(0, 80),
    title: String(note.title || note.displayTitle || "").slice(0, 200),
    content_type: String(note.type || "").slice(0, 40),
    has_note_data: true,
    has_media_stream_metadata: true,
    selected_stream: safeStreamSummary(chosen),
    media_acquisition_status: "downloaded_temporary_deleted_after_run",
    media_sha1: media.sha1,
    media_size_bytes: media.size_bytes,
    ffprobe: {
      status: probe.probe_status || "done",
      duration_seconds: durationSeconds,
      video_stream_count: videoStreams.length || (fallbackHasVideo ? 1 : 0),
      audio_stream_count: audioStreams.length || (fallbackHasAudio ? 1 : 0),
      format_name: String(probe.format?.format_name || "").slice(0, 80),
    },
    audio_evidence: audioEvidence,
    frame_evidence: {
      status: frameEvidence.length > 0 ? "keyframes_extracted_temporary" : "no_frames_extracted",
      frame_count: frameEvidence.length,
      frame_hashes: frameEvidence,
    },
    content_read_status: hasAudio ? "media_audio_and_keyframes_ready" : "media_keyframes_ready_no_audio",
    next_actions: hasAudio
      ? ["run_asr_on_temporary_audio_or_model_api", "review_keyframes_with_multimodal_model", "render_content_analysis"]
      : ["review_keyframes_with_multimodal_model", "render_content_analysis"],
    retained_files: args.keepTemp ? "temporary_files_retained_by_user_request" : "none",
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.urlStdin) args.url = await readStdin();
  if (!URL_RE.test(args.url) || !XHS_RE.test(args.url)) {
    throw new Error("--url must be a Xiaohongshu/xhslink URL");
  }
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "soren-xhs-media-"));
  try {
    const result = await buildEvidence(args, tempDir);
    assertSafeResult(result);
    const rendered = `${JSON.stringify(result, null, 2)}\n`;
    if (args.output) {
      await fs.mkdir(path.dirname(path.resolve(args.output)), { recursive: true });
      await fs.writeFile(args.output, rendered, "utf8");
    }
    process.stdout.write(rendered);
    return result.ok ? 0 : 2;
  } finally {
    if (!args.keepTemp) await fs.rm(tempDir, { recursive: true, force: true }).catch(() => undefined);
  }
}

main().then((code) => process.exit(code)).catch((error) => {
  console.error(error.message || String(error));
  process.exit(1);
});

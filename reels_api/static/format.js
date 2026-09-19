// Pure text helpers shared by the board and the player.

export const SOURCE_NAME = { tiktok: "TikTok", instagram: "Instagram", x: "X" };

const MINUTE_MS = 60_000;

// Tile badge: "now", "12m", "3h", "1d" since an ISO time (spec 6.2).
export function formatAge(iso, now = Date.now()) {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const minutes = Math.floor((now - then) / MINUTE_MS);
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

// m:ss, floored; "" when unknown.
export function formatDuration(seconds) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return "";
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

// "gone in 6h", "gone in 40m", "gone soon" (spec 7.1).
export function formatExpiry(iso, now = Date.now()) {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const ms = then - now;
  if (ms <= 0) return "gone soon";
  const minutes = Math.round(ms / MINUTE_MS);
  if (minutes < 60) return `gone in ${Math.max(1, minutes)}m`;
  return `gone in ${Math.round(minutes / 60)}h`;
}

// "TikTok · 0:19 · gone in 6h", leaving out parts that are unknown.
export function sourceLine(reel, now = Date.now()) {
  return [SOURCE_NAME[reel.source] || reel.source, formatDuration(reel.duration_seconds), formatExpiry(reel.expires_at, now)]
    .filter(Boolean)
    .join(" · ");
}

// Same rules as routes.slugify on the server.
export function slugify(title) {
  const slug = String(title || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug.slice(0, 60).replace(/-+$/g, "") || "video";
}

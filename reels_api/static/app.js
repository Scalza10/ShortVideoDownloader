import { Unauthorized, getJob, listJobs, logout } from "./api.js";
import { createBoard } from "./board.js";
import { createCookieAsk } from "./cookie.js";
import { hydrateIcons } from "./icons.js";
import { createPaste } from "./paste.js";
import { createPlayer } from "./player.js";
import { showToast } from "./toast.js";

const REFRESH_MS = 30_000;
const $ = (id) => document.getElementById(id);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
hydrateIcons(document);

const board = createBoard({
  grid: $("grid"),
  empty: $("empty"),
  count: $("count-n"),
  onOpen: (id, tile) => player.open(board.getReels(), id, { from: tile }),
});

const player = createPlayer({
  root: $("player"),
  onGone: (id) => board.remove(id),
});

let pastedOver = new Set(); // the reels already on the board when the current paste started

const paste = createPaste({
  form: $("paste"),
  onStart: () => {
    pastedOver = new Set(board.getReels().map((reel) => reel.id));
    board.addPending();
  },
  onMore: (n) => board.addPending(n),
  onFail: () => board.removePending(),
  onStateChange: (state) => board.setDimmed(state === "error"),
  // Once per video: an X post can bring several (X links spec 7).
  onDone: async (job) => {
    // One set of jobs per URL: the link was already in the pile. Not board.has(): an earlier
    // video's reload may already show this one.
    const existed = pastedOver.has(job.id);
    const jobs = (await loadJobs()) || [job, ...board.getReels().filter((reel) => reel.id !== job.id)];
    board.finishPending(jobs);
    player.addReels(jobs);
    if (existed) board.reveal(job.id);
  },
});

// The pile from the server, or null when it could not be loaded.
async function loadJobs() {
  try {
    return await listJobs();
  } catch (_) {
    return null;
  }
}

async function refresh() {
  const jobs = await loadJobs();
  if (!jobs) return; // keep whatever is on screen
  board.setReels(jobs);
  player.addReels(jobs);
}

function reelInUrl() {
  return new URLSearchParams(location.search).get("reel");
}

// A ?reel= link: open that reel muted, or say it is gone (spec 4).
async function openLinkedReel(id) {
  if (player.open(board.getReels(), id, { gesture: false, push: false })) return;
  let job = null;
  try {
    job = await getJob(id);
  } catch (err) {
    if (err instanceof Unauthorized) return;
  }
  if (job && job.status === "done" && player.open([job], id, { gesture: false, push: false })) return;
  history.replaceState(null, "", location.pathname);
  showToast("that one's gone", { error: true });
}

// Android share target: /?url=...&text=...&title=... starts a paste (web spec 7.2).
function consumeShareTarget() {
  const params = new URLSearchParams(location.search);
  const parts = ["url", "text", "title"].map((key) => params.get(key)).filter(Boolean);
  if (!parts.length) return false;
  history.replaceState(null, "", location.pathname);
  paste.submit(parts.join(" "));
  return true;
}

// Back closes the player; Forward to a reel opens it again.
window.addEventListener("popstate", () => {
  const id = reelInUrl();
  if (!id) player.close({ fromHistory: true });
  else if (!player.isOpen()) openLinkedReel(id);
});

// Log out deletes the cookie; the login page then asks again (cookie spec 6).
const logoutButton = $("logout");
logoutButton.addEventListener("click", async () => {
  logoutButton.disabled = true;
  try {
    await logout();
    location.replace("/");
  } catch (err) {
    if (err instanceof Unauthorized) return; // api() is already reloading
    logoutButton.disabled = false;
    showToast("couldn't log out. try again.", { error: true });
  }
});

// Runs once the page may use the cookie: at load, or after "allow cookie" (pop-up spec 6.2).
async function start() {
  setInterval(() => {
    if (document.visibilityState === "visible") refresh();
  }, REFRESH_MS);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refresh();
  });
  await refresh();
  if (consumeShareTarget()) return;
  const id = reelInUrl();
  if (id) openLinkedReel(id);
}

// A cookie set before the login page asked: nothing loads, not even the pile, until the person agrees.
if (document.body.dataset.cookie === "ask") {
  createCookieAsk({ dialog: $("cookie-ask"), onAccepted: start }).open();
} else {
  start();
}

import { Unauthorized, deleteJob, getJob, listJobs, logout, setFavorite } from "./api.js";
import { createBoard } from "./board.js";
import { createCookieAsk } from "./cookie.js";
import { hydrateIcons } from "./icons.js";
import { createPaste } from "./paste.js";
import { createPlayer } from "./player.js";
import { createSearch } from "./search.js";
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
  emptyFavorites: $("empty-favorites"),
  emptySearch: $("empty-search"),
  count: $("count-n"),
  tabs: { pile: $("tab-pile"), favorites: $("tab-favorites") },
  favoritesCount: $("favorites-n"),
  // The player gets the open tab's reels, so swiping stays in that tab (favorites spec 6).
  onOpen: (id, tile) => player.open(board.getShown(), id, { from: tile }),
});

// Search filters the board; the player gets the filtered list through board.getShown() (search spec 5.3).
const search = createSearch({
  row: $("search"),
  toggle: $("search-toggle"),
  input: $("search-input"),
  chips: [...document.querySelectorAll("#search .chip")],
  clearButton: $("search-clear"),
  onChange: (match) => board.setFilter(match),
});

const player = createPlayer({
  root: $("player"),
  onGone: (id) => board.remove(id),
  onDelete: (reel) => deleteReel(reel, "deleted"),
  onFavorite: (reel, on) => toggleStar(reel, on),
});

// ---- delete with undo (favorites spec 8)

// Reels deleted on this phone whose undo toast is up or whose DELETE is on its way.
// Every list from the server leaves them out.
const pendingDeletes = new Map(); // id -> {reel, sending}
const newestFirst = (a, b) => Date.parse(b.finished_at) - Date.parse(a.finished_at);

function putBack(reel) {
  board.setReels([...board.getReels().filter((r) => r.id !== reel.id), reel].sort(newestFirst));
}

// Gone from this phone now; the DELETE goes when the toast ends, unless undo is tapped first.
function deleteReel(reel, message) {
  pendingDeletes.set(reel.id, { reel, sending: false });
  board.remove(reel.id);
  player.remove(reel.id);
  showToast(message, {
    action: {
      label: "undo",
      onClick: () => {
        const entry = pendingDeletes.get(reel.id);
        if (!entry || entry.sending) {
          showToast("too late. it's deleted.", { error: true });
          return;
        }
        pendingDeletes.delete(reel.id);
        putBack(reel); // an open player gets it back at its next refresh or opening
      },
      onEnd: () => sendDelete(reel.id),
    },
  });
}

async function sendDelete(id, { keepalive = false } = {}) {
  const entry = pendingDeletes.get(id);
  if (!entry || entry.sending) return; // undone, or already on its way
  entry.sending = true;
  try {
    await deleteJob(id, { keepalive });
    pendingDeletes.delete(id);
  } catch (err) {
    pendingDeletes.delete(id);
    if (err instanceof Unauthorized) return; // api() is already reloading
    putBack(entry.reel);
    showToast("couldn't delete. try again.", { error: true });
  }
}

// Leaving the page ends the undo: send now, in requests that outlive the page.
function flushDeletes() {
  for (const id of pendingDeletes.keys()) sendDelete(id, { keepalive: true });
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") flushDeletes();
});
window.addEventListener("pagehide", flushDeletes);

// ---- star (favorites spec 8)

const starring = new Set(); // reels with a star or un-star on its way: another tap is ignored until it's back

// Un-starring a reel past its time is a delete: only the star kept it.
function toggleStar(reel, on) {
  if (!on && Date.parse(reel.expires_at) <= Date.now()) {
    deleteReel(reel, "removed");
    return;
  }
  star(reel, on);
}

async function star(reel, on) {
  if (starring.has(reel.id)) return;
  starring.add(reel.id);
  let job;
  try {
    job = await setFavorite(reel.id, on);
  } catch (err) {
    if (err instanceof Unauthorized) return; // api() is already reloading
    job = { error: "network" };
  } finally {
    starring.delete(reel.id);
  }
  if (job.error === "favorites_full") {
    showToast(`favorites are full (${board.favoriteCount()}). remove one first.`, { error: true });
    return;
  }
  if (job.error) {
    showToast("couldn't save that. try again.", { error: true });
    return;
  }
  board.update(job);
  player.update(job);
  if (on) showToast("added to favorites");
  else showToast("un-starred", { action: { label: "undo", onClick: () => star(job, true) } });
}

let pastedOver = new Set(); // the reels already on the board when the current paste started

const paste = createPaste({
  form: $("paste"),
  onStart: () => {
    search.clear(); // the new tile, or the reel it turns out to be, must not be hidden (search spec 3.5)
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
    player.addReels(board.getShown());
    if (existed) board.reveal(job.id);
  },
});

// The pile from the server without the reels being deleted here, or null when it could not be loaded.
async function loadJobs() {
  try {
    return (await listJobs()).filter((job) => !pendingDeletes.has(job.id));
  } catch (_) {
    return null;
  }
}

async function refresh() {
  const jobs = await loadJobs();
  if (!jobs) return; // keep whatever is on screen
  board.setReels(jobs);
  player.addReels(board.getShown());
}

function reelInUrl() {
  return new URLSearchParams(location.search).get("reel");
}

// A ?reel= link: open that reel muted, or say it is gone (spec 4).
async function openLinkedReel(id) {
  const where = board.tabOf(id);
  if (where) {
    board.setTab(where); // an old favorite opens on the favorites tab (favorites spec 6)
    if (player.open(board.getShown(), id, { gesture: false, push: false })) return;
  }
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

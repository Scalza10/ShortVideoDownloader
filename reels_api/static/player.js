import { api } from "./api.js";
import { formatDuration, slugify, sourceLine } from "./format.js";
import { icon } from "./icons.js";
import { showToast } from "./toast.js";

const desktopQuery = matchMedia("(min-width: 700px)");

// Phone gestures (spec 7.2).
const TAP_SLOP_PX = 10;
const SWIPE_FRACTION = 0.2;
const FLICK_PX_PER_MS = 0.5;
const SLIDE_MS = 200;
const SPRING_MS = 160;

// A web download on iPhone lands in Files, never Photos; the share sheet's "Save Video" does (spec 7.4).
const isIOS =
  /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
// Decided once, before any file exists (web spec 7.4).
const canShareFiles =
  typeof navigator.canShare === "function" &&
  navigator.canShare({ files: [new File([""], "probe.mp4", { type: "video/mp4" })] });
const saveWithShareSheet = isIOS && canShareFiles;

// The share link: opens the reel for anyone, the board only with the cookie (links spec 4.3).
function reelPath(reel) {
  const path = `/?reel=${encodeURIComponent(reel.id)}`;
  return reel.share_key ? `${path}&k=${encodeURIComponent(reel.share_key)}` : path;
}

// The link that Share, Copy link and the WhatsApp button hand out.
function reelLink(reel) {
  return location.origin + reelPath(reel);
}

// Full-bleed with tap-to-reveal chrome below 700px, a centred overlay from 700px (spec 7).
// standalone: the view-only page's single reel. No history, no closing, no swiping (links spec 8).
export function createPlayer({ root, onGone, standalone = false }) {
  const video = root.querySelector("video");
  const frame = root.querySelector(".player-frame");
  const idleFill = root.querySelector(".idle-fill");
  const scrubbers = [...root.querySelectorAll(".scrubber")];
  const volumeButtons = [...root.querySelectorAll('[data-action="volume"]')];
  const saveButtons = [...root.querySelectorAll('[data-action="save"]')];
  const prevButton = root.querySelector('[data-action="prev"]');
  const nextButton = root.querySelector('[data-action="next"]');
  const desktopClose = root.querySelector(".player-close-desktop");
  // Where focus goes when the overlay opens on desktop; the view-only page has no close button.
  const desktopFocus = desktopClose || saveButtons[saveButtons.length - 1];
  const cover = root.querySelector(".nsfw-cover");

  let reels = []; // snapshot of the board's order, taken on open
  let index = -1;
  let pushed = false; // open() added a history entry that close() must pop
  let opener = null;
  let muted = false; // the viewer's choice carries from reel to reel
  let frameRequest = 0;
  let drag = null; // {id, x, y, time, dy} while a finger is down on the frame
  let sliding = false;
  let prefetch = null; // {id, controller, state: "loading" | "ready" | "failed", file}
  const uncovered = new Set(); // NSFW reels tapped open while this page is open (NSFW cover spec 5)

  const current = () => reels[index];
  const isOpen = () => !root.hidden;
  const isCovered = () => root.classList.contains("is-covered");

  function setCovered(covered) {
    root.classList.toggle("is-covered", covered);
    cover.hidden = !covered;
  }

  function setText(selector, text) {
    for (const el of root.querySelectorAll(selector)) el.textContent = text;
  }

  function setChrome(visible) {
    root.classList.toggle("chrome-on", visible);
  }

  function renderVolume() {
    for (const button of volumeButtons) {
      button.innerHTML = icon(muted ? "volumeX" : "volume2");
      button.setAttribute("aria-label", muted ? "unmute" : "mute");
    }
  }

  function renderNav() {
    if (prevButton) prevButton.disabled = index <= 0;
    if (nextButton) nextButton.disabled = index >= reels.length - 1;
  }

  function renderProgress() {
    const reel = current();
    const duration = Number.isFinite(video.duration) ? video.duration : (reel && reel.duration_seconds) || 0;
    const time = video.currentTime || 0;
    const percent = duration > 0 ? Math.min(100, (time / duration) * 100) : 0;
    for (const range of scrubbers) {
      range.max = String(duration || 1);
      range.value = String(time);
      range.style.setProperty("--progress", `${percent}%`);
    }
    idleFill.style.width = `${percent}%`;
    setText(".js-elapsed", formatDuration(time) || "0:00");
    setText(".js-duration", formatDuration(duration) || "0:00");
  }

  // Redraw the progress every frame while open, so the 3px bar moves smoothly.
  function tick() {
    renderProgress();
    frameRequest = requestAnimationFrame(tick);
  }

  function renderSave() {
    const loading = Boolean(prefetch && prefetch.state === "loading");
    for (const button of saveButtons) {
      button.classList.toggle("is-loading", loading);
      button.setAttribute("aria-disabled", String(loading));
    }
  }

  function abortPrefetch() {
    if (prefetch) prefetch.controller.abort();
    prefetch = null;
    renderSave();
  }

  // iPhone only: fetch the file while the reel plays, so Save can open the share sheet on the tap itself.
  async function startPrefetch(reel) {
    const entry = { id: reel.id, controller: new AbortController(), state: "loading", file: null };
    prefetch = entry;
    renderSave();
    try {
      const response = await api(reel.file_url, { signal: entry.controller.signal });
      if (!response.ok) throw new Error(`fetch failed: ${response.status}`);
      const blob = await response.blob();
      const file = new File([blob], `${slugify(reel.title)}.mp4`, { type: "video/mp4" });
      entry.file = file;
      entry.state = navigator.canShare({ files: [file] }) ? "ready" : "failed";
    } catch (_) {
      entry.state = "failed"; // aborted, network error or 404: Save falls back to a download
    }
    if (prefetch === entry) renderSave();
  }

  function play() {
    if (isCovered()) return; // an NSFW reel waits for a tap
    video.muted = muted;
    const attempt = video.play();
    if (!attempt) return;
    attempt.catch((err) => {
      if (err.name !== "NotAllowedError" || video.muted) return;
      // No sound allowed without a fresh tap: play muted and show it.
      muted = true;
      renderVolume();
      video.muted = true;
      video.play().catch(() => {});
    });
  }

  // A tap on a covered reel: it stays uncovered while the page is open.
  function uncover() {
    const fromButton = cover.contains(document.activeElement);
    uncovered.add(current().id);
    setCovered(false);
    play();
    // The button just hid itself; keep keyboard focus inside the overlay.
    if (fromButton && desktopQuery.matches && desktopFocus) desktopFocus.focus();
  }

  function show(i) {
    abortPrefetch();
    index = i;
    const reel = current();
    video.pause();
    if (reel.thumbnail_url) video.poster = reel.thumbnail_url;
    else video.removeAttribute("poster");
    video.src = reel.file_url;
    const covered = Boolean(reel.nsfw) && !uncovered.has(reel.id);
    setCovered(covered);
    if (covered) setChrome(false); // the cover, not the options, is what a covered reel shows first
    setText(".js-source", sourceLine(reel));
    setText(".js-caption", reel.caption || reel.title || "");
    renderNav();
    renderProgress();
    if (saveWithShareSheet) startPrefetch(reel);
  }

  function open(list, id, { gesture = true, push = true, from = null } = {}) {
    const i = list.findIndex((reel) => reel.id === id);
    if (i === -1) return false;
    reels = list.slice();
    opener = from;
    if (!gesture) muted = true;
    root.hidden = false;
    document.body.classList.add("player-open");
    setChrome(false);
    setFrame(0, 0);
    renderVolume();
    show(i);
    play();
    if (!standalone) {
      if (push) history.pushState({ reel: id }, "", reelPath(current()));
      else history.replaceState({ reel: id }, "", reelPath(current()));
      pushed = push;
    }
    cancelAnimationFrame(frameRequest);
    tick();
    if (desktopQuery.matches && desktopFocus) desktopFocus.focus();
    return true;
  }

  function move(step) {
    const next = index + step;
    if (!isOpen() || next < 0 || next >= reels.length) return false;
    show(next);
    play();
    if (!standalone) history.replaceState({ reel: current().id }, "", reelPath(current()));
    return true;
  }

  function close({ fromHistory = false } = {}) {
    if (!isOpen()) return;
    cancelAnimationFrame(frameRequest);
    abortPrefetch();
    drag = null;
    root.hidden = true;
    document.body.classList.remove("player-open");
    video.pause();
    video.removeAttribute("src");
    video.removeAttribute("poster");
    video.load(); // release the stream
    if (!fromHistory) {
      if (pushed) history.back();
      else history.replaceState(null, "", location.pathname);
    }
    pushed = false;
    if (opener && opener.isConnected) opener.focus({ preventScroll: true });
    opener = null;
  }

  // A refresh while open: new reels join the front; nothing is removed or reordered (spec 7.1).
  function addReels(list) {
    if (!isOpen()) return;
    const known = new Set(reels.map((reel) => reel.id));
    const fresh = list.filter((reel) => !known.has(reel.id));
    if (!fresh.length) return;
    reels = [...fresh, ...reels];
    index += fresh.length;
    renderNav();
  }

  // ---- actions (spec 7.4)

  function openWhatsApp(url) {
    window.open(`https://wa.me/?text=${encodeURIComponent(url)}`, "_blank", "noopener");
  }

  function share() {
    const url = reelLink(current());
    if (typeof navigator.share !== "function") {
      openWhatsApp(url);
      return;
    }
    navigator.share({ url }).catch((err) => {
      if (err && err.name === "AbortError") return; // the viewer closed the sheet
      openWhatsApp(url);
    });
  }

  async function copyLink() {
    setChrome(false);
    try {
      await navigator.clipboard.writeText(reelLink(current()));
      showToast("link copied");
    } catch (_) {
      showToast("couldn't copy the link", { error: true });
    }
  }

  function download() {
    const link = document.createElement("a");
    link.href = current().file_url; // the server sends Content-Disposition: attachment
    link.download = "";
    document.body.append(link);
    link.click();
    link.remove();
    setChrome(false);
    showToast("saved to your downloads");
  }

  function save() {
    const entry = prefetch && prefetch.id === current().id ? prefetch : null;
    if (entry && entry.state === "loading") return;
    if (entry && entry.state === "ready") {
      // No await before share(): iOS only opens the sheet inside the tap itself.
      navigator.share({ files: [entry.file] }).catch((err) => {
        if (err && err.name === "AbortError") return;
        showToast("couldn't save that one", { error: true });
      });
      return; // no toast: the sheet's choice is unknown
    }
    download();
  }

  function togglePlay() {
    if (video.paused) play();
    else video.pause();
  }

  function toggleMute() {
    muted = !muted;
    video.muted = muted;
    renderVolume();
  }

  const actions = {
    close: () => close(),
    prev: () => move(-1),
    next: () => move(1),
    share,
    whatsapp: () => openWhatsApp(reelLink(current())),
    copy: copyLink,
    save,
    volume: toggleMute,
    reveal: uncover,
  };

  root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button || !root.contains(button)) return;
    if (button.getAttribute("aria-disabled") === "true") return;
    actions[button.dataset.action]();
  });

  // ---- desktop: click on the video plays and pauses

  frame.addEventListener("click", (event) => {
    if (!desktopQuery.matches || event.target.closest("button, input")) return;
    if (isCovered()) uncover();
    else togglePlay();
  });

  // ---- phone: tap toggles the chrome, vertical swipes move through the pile (spec 7.2)

  function setFrame(offset, ms) {
    frame.style.transition = ms ? `transform ${ms}ms ease-out` : "none";
    frame.style.transform = offset ? `translateY(${offset}px)` : "";
  }

  // Slide the current reel out, swap in the next one, slide it in from the other side.
  function slide(step) {
    const height = frame.offsetHeight;
    sliding = true;
    setFrame(-step * height, SLIDE_MS);
    setTimeout(() => {
      if (!isOpen()) {
        sliding = false;
        return;
      }
      move(step);
      setFrame(step * height, 0);
      frame.getBoundingClientRect(); // commit the start position before animating from it
      setFrame(0, SLIDE_MS);
      setTimeout(() => {
        sliding = false;
      }, SLIDE_MS);
    }, SLIDE_MS);
  }

  frame.addEventListener("pointerdown", (event) => {
    if (desktopQuery.matches || sliding || drag || event.target.closest("button, input")) return;
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, time: performance.now(), dy: 0 };
    frame.setPointerCapture(event.pointerId);
    setFrame(0, 0);
  });

  frame.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.id || standalone) return;
    const dy = event.clientY - drag.y;
    const pastEnd = (dy < 0 && index >= reels.length - 1) || (dy > 0 && index <= 0);
    drag.dy = dy;
    setFrame(pastEnd ? dy / 3 : dy, 0);
  });

  frame.addEventListener("pointerup", (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    const { x, y, time, dy } = drag;
    drag = null;
    if (Math.hypot(event.clientX - x, event.clientY - y) < TAP_SLOP_PX) {
      setFrame(0, 0);
      if (isCovered()) uncover();
      else setChrome(!root.classList.contains("chrome-on"));
      return;
    }
    if (standalone) return; // the frame never moved
    const step = dy < 0 ? 1 : -1; // finger up: next reel
    const target = index + step;
    const far = Math.abs(dy) > window.innerHeight * SWIPE_FRACTION;
    const flick = Math.abs(dy) / Math.max(1, performance.now() - time) > FLICK_PX_PER_MS;
    if ((far || flick) && target >= 0 && target < reels.length) slide(step);
    else setFrame(0, SPRING_MS);
  });

  frame.addEventListener("pointercancel", (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    drag = null;
    setFrame(0, SPRING_MS);
  });

  // ---- scrubbers, errors, keys

  for (const range of scrubbers) {
    range.addEventListener("input", () => {
      video.currentTime = Number(range.value);
      renderProgress();
    });
  }

  // play() refuses while covered, but media keys and the lock screen call the element directly.
  video.addEventListener("play", () => {
    if (isCovered()) video.pause();
  });

  video.addEventListener("error", () => {
    if (!isOpen()) return;
    const gone = current();
    if (standalone) {
      onGone(gone.id); // the page decides: expired page or a toast
      return;
    }
    close();
    onGone(gone.id);
    showToast("that one's gone", { error: true });
  });

  function trapFocus(event) {
    const focusable = [...root.querySelectorAll("button, input")].filter(
      (el) => !el.disabled && el.getClientRects().length > 0,
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!root.contains(document.activeElement)) {
      event.preventDefault();
      first.focus();
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  document.addEventListener("keydown", (event) => {
    if (!isOpen()) return;
    if (event.key === "Escape") {
      if (standalone) return;
      event.preventDefault();
      close();
      return;
    }
    if (!desktopQuery.matches) return;
    if (event.key === "Tab") {
      trapFocus(event);
      return;
    }
    if (event.target instanceof HTMLInputElement) return; // arrows seek inside the scrubber
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      move(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      move(1);
    }
  });

  // Crossing 700px while open: CSS switches the layout; reset what only one layout uses.
  desktopQuery.addEventListener("change", () => {
    if (!isOpen()) return;
    drag = null;
    setFrame(0, 0);
    setChrome(false);
  });

  return { open, close, isOpen, addReels };
}

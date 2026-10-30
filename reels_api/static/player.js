import { api } from "./api.js";
import { formatDuration, isIOS, slugify, sourceLine } from "./format.js";
import { icon } from "./icons.js";
import { showToast } from "./toast.js";

const desktopQuery = matchMedia("(min-width: 700px)");

// The desktop frame takes the video's shape, from tall 9:16 to wide 16:9.
const TALLEST_FRAME = 9 / 16;
const WIDEST_FRAME = 16 / 9;

// Phone gestures (spec 7.2).
const TAP_SLOP_PX = 10;
const SWIPE_FRACTION = 0.2;
const FLICK_PX_PER_MS = 0.5;
const SLIDE_MS = 200;
const SPRING_MS = 160;

// A double tap, double-click or held Enter on delete must not take the next reel too.
const DELETE_GUARD_MS = 700;

// The speed button steps through these (fullscreen spec 3.4).
const SPEEDS = [1, 1.5, 2];

// Esc leaves fullscreen, not the player; a browser may deliver the key just after leaving (fullscreen spec 3.3).
const FULLSCREEN_ESC_GUARD_MS = 500;

// A web download on iPhone lands in Files, never Photos; the share sheet's "Save Video" does (spec 7.4).
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
export function createPlayer({ root, onGone, onDelete = null, onFavorite = null, standalone = false }) {
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
  const starButtons = [...root.querySelectorAll('[data-action="favorite"]')];
  const speedButtons = [...root.querySelectorAll('[data-action="speed"]')];
  const stage = root.querySelector(".player-stage");
  const fullscreenButtons = [...root.querySelectorAll('[data-action="fullscreen"]')];
  // Decided once. iPhone has no element fullscreen, only Apple's own player for a <video> (fullscreen spec 3.3).
  const fullscreenMode =
    document.fullscreenEnabled || document.webkitFullscreenEnabled
      ? "element"
      : typeof video.webkitEnterFullscreen === "function"
        ? "video"
        : null;

  let reels = []; // snapshot of the board's order, taken on open
  let index = -1;
  let pushed = false; // open() added a history entry that close() must pop
  let opener = null;
  let muted = false; // the viewer's choice carries from reel to reel
  let speed = 0; // index into SPEEDS; carries from reel to reel like muted
  let fullscreenEndedAt = -Infinity; // performance.now() when fullscreen last ended, for FULLSCREEN_ESC_GUARD_MS
  let frameRequest = 0;
  let drag = null; // {id, x, y, time, dy} while a finger is down on the frame
  let sliding = false;
  let prefetch = null; // {id, controller, state: "loading" | "ready" | "failed", file}
  let lastDelete = 0; // performance.now() of the last accepted delete, for DELETE_GUARD_MS

  const current = () => reels[index];
  const isOpen = () => !root.hidden;
  const isFullscreen = () => (document.fullscreenElement || document.webkitFullscreenElement) === stage;

  function setText(selector, text) {
    for (const el of root.querySelectorAll(selector)) el.textContent = text;
  }

  function setChrome(visible) {
    root.classList.toggle("chrome-on", visible);
  }

  // The ▶ while paused (fullscreen spec 3.1). Read from the video, not the tap, so a pause from
  // elsewhere (a call, the lock screen, an autoplay refused even muted) shows it too.
  function renderPaused() {
    root.classList.toggle("is-paused", video.paused);
  }

  // The video always shows whole (object-fit: contain). On desktop the frame takes its shape.
  function fit(width, height) {
    const ratio = width > 0 && height > 0 ? width / height : TALLEST_FRAME;
    root.style.setProperty("--frame-ar", String(Math.min(WIDEST_FRAME, Math.max(TALLEST_FRAME, ratio))));
  }

  function renderVolume() {
    for (const button of volumeButtons) {
      button.innerHTML = icon(muted ? "volumeX" : "volume2");
      button.setAttribute("aria-label", muted ? "unmute" : "mute");
    }
  }

  function renderSpeed() {
    const rate = SPEEDS[speed];
    for (const button of speedButtons) {
      button.textContent = `${rate}x`;
      button.setAttribute("aria-label", `speed ${rate}x`);
      button.classList.toggle("is-fast", rate !== 1);
    }
  }

  // Both rates: loading a new src resets playbackRate to defaultPlaybackRate.
  function applySpeed() {
    video.defaultPlaybackRate = SPEEDS[speed];
    video.playbackRate = SPEEDS[speed];
  }

  function nextSpeed() {
    speed = (speed + 1) % SPEEDS.length;
    applySpeed();
    renderSpeed();
  }

  function renderFullscreen() {
    const on = isFullscreen();
    root.classList.toggle("is-fullscreen", on);
    for (const button of fullscreenButtons) {
      button.hidden = !fullscreenMode;
      button.innerHTML = icon(on ? "minimize" : "maximize");
      button.setAttribute("aria-label", on ? "exit fullscreen" : "fullscreen");
    }
  }

  // The video's own size first; a rotated file can differ from the job's.
  function isWide() {
    const reel = current();
    const width = video.videoWidth || reel.width || 0;
    const height = video.videoHeight || reel.height || 0;
    return width > height;
  }

  // Fullscreen is for watching: it plays and hides the options (fullscreen spec 3.3). Element mode does so once the
  // browser agrees; Apple's player must be asked inside the tap, so "video" mode plays first.
  async function enterFullscreen() {
    if (fullscreenMode === "video") {
      setChrome(false);
      play();
      try {
        video.webkitEnterFullscreen();
      } catch (_) {
        // not ready yet (InvalidStateError): the next tap works
      }
      return;
    }
    try {
      await (stage.requestFullscreen ? stage.requestFullscreen() : stage.webkitRequestFullscreen());
    } catch (_) {
      return; // refused: stay as we are
    }
    setChrome(false);
    play();
    // A wide reel turns sideways. Desktops and many browsers refuse the lock; that's fine.
    if (isWide() && screen.orientation && typeof screen.orientation.lock === "function") {
      screen.orientation.lock("landscape").catch(() => {});
    }
  }

  function exitFullscreen() {
    if (!isFullscreen()) return;
    const exit = document.exitFullscreen || document.webkitExitFullscreen;
    Promise.resolve(exit.call(document)).catch(() => {});
  }

  function toggleFullscreen() {
    if (isFullscreen()) exitFullscreen();
    else enterFullscreen();
  }

  // The browser only draws the fullscreen element's subtree, so the toast (the delete undo) moves into the stage
  // while it is fullscreen (fullscreen spec 3.3). Runs once per enter and once per exit.
  let toastHome = null; // {parent, next} while the toast is inside the stage
  function moveToast(was, now) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    if (!was && now) {
      toastHome = { parent: toast.parentNode, next: toast.nextSibling };
      stage.appendChild(toast);
    } else if (was && !now && toastHome) {
      const { parent, next } = toastHome;
      parent.insertBefore(toast, next && next.parentNode === parent ? next : null);
      toastHome = null;
    }
  }

  // Also runs when Esc or the system back gesture ends fullscreen. Crossing 700px never does.
  function onFullscreenChange() {
    const was = root.classList.contains("is-fullscreen");
    renderFullscreen();
    moveToast(was, isFullscreen());
    if (!was || isFullscreen()) return;
    fullscreenEndedAt = performance.now();
    try {
      screen.orientation.unlock();
    } catch (_) {
      // nothing was locked, or no Screen Orientation API
    }
  }

  // Filled and pressed while the reel is a favorite (favorites spec 7).
  function renderStar() {
    const on = Boolean(current() && current().favorite);
    for (const button of starButtons) {
      button.classList.toggle("is-on", on);
      button.setAttribute("aria-pressed", String(on));
      button.setAttribute("aria-label", on ? "remove from favorites" : "add to favorites");
      button.querySelector(".star-icon").innerHTML = icon(on ? "starFilled" : "star");
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
    video.muted = muted;
    const attempt = video.play();
    renderPaused(); // now, not on the "play" event, so the ▶ never flashes between reels
    if (!attempt) return;
    attempt.catch((err) => {
      if (err.name !== "NotAllowedError" || video.muted) {
        renderPaused(); // refused even muted, or cut short: the ▶ offers a tap
        return;
      }
      // No sound allowed without a fresh tap: play muted and show it.
      muted = true;
      renderVolume();
      video.muted = true;
      video.play().catch(renderPaused);
      renderPaused();
    });
  }

  function show(i) {
    abortPrefetch();
    index = i;
    const reel = current();
    video.pause();
    fit(reel.width, reel.height); // before the poster shows
    if (reel.thumbnail_url) video.poster = reel.thumbnail_url;
    else video.removeAttribute("poster");
    video.src = reel.file_url;
    applySpeed();
    setText(".js-source", sourceLine(reel));
    setText(".js-caption", reel.caption || reel.title || "");
    renderStar();
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
    renderSpeed();
    renderFullscreen();
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
    setChrome(false); // the next reel plays, so its options stay hidden (fullscreen spec 3.1)
    if (!standalone) history.replaceState({ reel: current().id }, "", reelPath(current()));
    return true;
  }

  function close({ fromHistory = false } = {}) {
    if (!isOpen()) return;
    exitFullscreen();
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

  // A reel deleted on this phone: drop it and show the next one, or close when none are left (favorites spec 7).
  function remove(id) {
    if (!isOpen()) return;
    const i = reels.findIndex((reel) => reel.id === id);
    if (i === -1) return;
    const wasCurrent = i === index;
    reels.splice(i, 1);
    if (!reels.length) {
      close();
      return;
    }
    if (i < index) index -= 1;
    else if (wasCurrent && index >= reels.length) index = reels.length - 1;
    if (wasCurrent) {
      show(index);
      play();
      if (!standalone) history.replaceState({ reel: current().id }, "", reelPath(current()));
    } else {
      renderNav();
    }
  }

  // A reel starred or un-starred on this phone: its new JSON, redrawn if it is showing.
  function update(reel) {
    const i = reels.findIndex((r) => r.id === reel.id);
    if (i === -1) return;
    reels[i] = reel;
    if (i === index && isOpen()) {
      setText(".js-source", sourceLine(reel));
      renderStar();
    }
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
    speed: nextSpeed,
    fullscreen: toggleFullscreen,
    delete: () => {
      // A double tap, double-click or held Enter must not take the next reel too.
      const now = performance.now();
      if (now - lastDelete < DELETE_GUARD_MS) return;
      lastDelete = now;
      setChrome(false); // like copyLink/download; also keeps the undo toast off the scrubber/volume row
      if (onDelete) onDelete(current());
    },
    favorite: () => {
      if (onFavorite) onFavorite(current(), !current().favorite);
    },
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
    togglePlay();
  });

  // ---- phone: a tap pauses and shows the options, or plays and hides them (fullscreen spec 3.1);
  // vertical swipes move through the pile (spec 7.2)

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
    if (!drag || event.pointerId !== drag.id || standalone || isFullscreen()) return;
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
      if (video.paused) {
        play();
        setChrome(false);
      } else {
        video.pause();
        setChrome(true);
      }
      return;
    }
    if (standalone || isFullscreen()) return; // the frame never moved; no swiping in fullscreen (fullscreen spec 3.3)
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

  // The element's size, with any rotation applied, can differ from the job's.
  video.addEventListener("loadedmetadata", () => {
    if (isOpen() && video.videoWidth && video.videoHeight) fit(video.videoWidth, video.videoHeight);
  });

  video.addEventListener("play", renderPaused);
  video.addEventListener("pause", renderPaused);

  // Apple's fullscreen player has its own speed menu; follow it so our button and the next reel agree.
  video.addEventListener("ratechange", () => {
    const picked = SPEEDS.indexOf(video.playbackRate);
    if (picked === -1 || picked === speed) return;
    speed = picked;
    video.defaultPlaybackRate = SPEEDS[speed];
    renderSpeed();
  });

  video.addEventListener("error", () => {
    if (!isOpen()) return;
    exitFullscreen();
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
    const scope = isFullscreen() ? stage : root;
    const focusable = [...scope.querySelectorAll("button, input")].filter(
      (el) => !el.disabled && el.getClientRects().length > 0,
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!scope.contains(document.activeElement)) {
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
      // Esc leaves fullscreen, not the player (fullscreen spec 3.3).
      if (isFullscreen() || performance.now() - fullscreenEndedAt < FULLSCREEN_ESC_GUARD_MS) return;
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

  document.addEventListener("fullscreenchange", onFullscreenChange);
  document.addEventListener("webkitfullscreenchange", onFullscreenChange);

  // Crossing 700px while open: CSS switches the layout; reset what only one layout uses.
  desktopQuery.addEventListener("change", () => {
    if (!isOpen()) return;
    drag = null;
    setFrame(0, 0);
    setChrome(false);
  });

  return { open, close, isOpen, addReels, remove, update };
}

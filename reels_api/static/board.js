import { formatAge } from "./format.js";
import { icon } from "./icons.js";

// The grid of reels, the pile count, the empty state and the optimistic tiles (spec 6.1-6.4).
export function createBoard({ grid, empty, count, onOpen }) {
  let reels = [];
  const pending = []; // optimistic tiles while a paste is in flight, one per video (X links spec 7)
  const tiles = new Map(); // job id -> tile element, kept across refreshes so images never reload

  function buildTile(reel) {
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = "tile";
    if (reel.thumbnail_url) {
      const img = document.createElement("img");
      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      img.addEventListener("load", () => img.classList.add("loaded"), { once: true });
      img.src = reel.thumbnail_url;
      tile.append(img);
    }
    if (reel.nsfw) {
      // Covered, not locked: the thumbnail is blurred and labelled (NSFW cover spec 4).
      tile.classList.add("nsfw");
      const label = document.createElement("span");
      label.className = "nsfw-label";
      label.textContent = "NSFW";
      tile.append(label);
    }
    const badge = document.createElement("span");
    badge.className = "badge";
    const hover = document.createElement("span");
    hover.className = "hover-row";
    hover.innerHTML = `<span class="hover-inner">${icon("play")}<span class="hover-label"></span></span>`;
    tile.append(badge, hover);
    tile.addEventListener("click", () => {
      if (onOpen) onOpen(reel.id, tile);
    });
    return tile;
  }

  function updateTile(tile, reel, newest, now) {
    const age = formatAge(reel.finished_at, now);
    const ago = age === "now" ? "now" : `${age} ago`;
    const badge = tile.querySelector(".badge");
    badge.replaceChildren(age);
    if (newest) badge.insertAdjacentHTML("afterbegin", icon("play"));
    badge.hidden = !age;
    tile.querySelector(".hover-label").textContent = `play · ${ago}`;
    tile.setAttribute("aria-label", `${reel.nsfw ? "play NSFW reel" : "play"}, ${ago}`);
  }

  function render() {
    const now = Date.now();
    const ids = new Set(reels.map((reel) => reel.id));
    for (const [id, tile] of tiles) {
      if (!ids.has(id)) {
        tile.remove();
        tiles.delete(id);
      }
    }
    let previous = pending.at(-1) || null; // reels go after the pending tiles
    reels.forEach((reel, i) => {
      let tile = tiles.get(reel.id);
      if (!tile) {
        tile = buildTile(reel);
        tiles.set(reel.id, tile);
      }
      updateTile(tile, reel, i === 0, now);
      const expected = previous ? previous.nextSibling : grid.firstChild;
      if (tile !== expected) grid.insertBefore(tile, expected);
      previous = tile;
    });
    const total = reels.length + pending.length;
    count.textContent = String(total);
    grid.hidden = total === 0;
    empty.hidden = total !== 0;
    document.body.classList.toggle("is-empty", total === 0);
  }

  function dropPending() {
    const tile = pending.pop();
    if (tile) tile.remove();
  }

  return {
    setReels(list) {
      reels = list.slice();
      render();
    },
    getReels() {
      return reels.slice();
    },
    has(id) {
      return tiles.has(id);
    },
    remove(id) {
      reels = reels.filter((reel) => reel.id !== id);
      render();
    },
    // Add n optimistic tiles at the top, after any already there.
    addPending(n = 1) {
      for (let i = 0; i < n; i++) {
        const tile = document.createElement("div");
        tile.className = "tile pending";
        tile.innerHTML = '<span class="spinner" aria-hidden="true"></span><span class="badge">now</span>';
        const last = pending.at(-1);
        grid.insertBefore(tile, last ? last.nextSibling : grid.firstChild);
        pending.push(tile);
      }
      render();
    },
    // Swap one optimistic tile for the fresh list in one render, so the count never flickers.
    finishPending(list) {
      dropPending();
      reels = list.slice();
      render();
    },
    removePending() {
      dropPending();
      render();
    },
    setDimmed(dimmed) {
      grid.classList.toggle("dimmed", dimmed);
    },
    reveal(id) {
      const tile = tiles.get(id);
      if (tile) tile.scrollIntoView({ block: "nearest", behavior: "smooth" });
    },
  };
}

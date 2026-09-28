import { fillsBox, formatAge } from "./format.js";
import { icon } from "./icons.js";

function fadeInOnLoad(img) {
  img.addEventListener("load", () => img.classList.add("loaded"), { once: true });
}

// The pile tab: every reel but the favorites past their time (favorites spec 6).
function inPile(reel, now) {
  return !(reel.favorite && Date.parse(reel.expires_at) <= now);
}

// The favorites tab: newest star first.
function byNewestStar(a, b) {
  return Date.parse(b.starred_at) - Date.parse(a.starred_at);
}

// The grid of reels, the pile count, the empty states, the optimistic tiles (spec 6.1-6.4)
// and the pile and favorites tabs (favorites spec 6).
export function createBoard({ grid, empty, emptyFavorites, emptySearch, count, tabs, favoritesCount, onOpen }) {
  let reels = []; // every reel from the server, newest first
  let tab = "pile";
  let match = null; // the search: null, or reel => true for the reels to show (search spec 5.2)
  const pending = []; // optimistic tiles while a paste is in flight, one per video (X links spec 7)
  const tiles = new Map(); // job id -> tile element, kept across refreshes and tab switches so images never reload

  // The open tab's reels, then only the ones the search matches.
  function shown(now = Date.now()) {
    const list = tab === "pile"
      ? reels.filter((reel) => inPile(reel, now))
      : reels.filter((reel) => reel.favorite).sort(byNewestStar);
    return match ? list.filter(match) : list;
  }

  function buildTile(reel) {
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = "tile";
    if (reel.thumbnail_url) {
      const img = document.createElement("img");
      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      fadeInOnLoad(img);
      img.addEventListener(
        "load",
        () => {
          if (fillsBox(img.naturalWidth, img.naturalHeight, 9, 16)) return;
          // Too wide or square to fill the tile: the whole thumbnail, over a blurred copy (from the cache).
          const backdrop = img.cloneNode();
          backdrop.className = "tile-backdrop";
          fadeInOnLoad(backdrop);
          img.before(backdrop);
          tile.classList.add("whole");
        },
        { once: true },
      );
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
    const star = document.createElement("span");
    star.className = "tile-star";
    star.innerHTML = icon("starFilled");
    tile.append(badge, hover, star);
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
    tile.querySelector(".tile-star").hidden = !reel.favorite;
    const what = reel.nsfw ? "play NSFW reel" : "play";
    tile.setAttribute("aria-label", `${what}${reel.favorite ? ", favorite" : ""}, ${ago}`);
  }

  function render() {
    const now = Date.now();
    const list = shown(now);
    const known = new Set(reels.map((reel) => reel.id));
    const visible = new Set(list.map((reel) => reel.id));
    for (const [id, tile] of tiles) {
      if (!known.has(id)) {
        tile.remove();
        tiles.delete(id);
      } else if (!visible.has(id)) {
        tile.remove(); // the other tab's: off the page, kept for when it shows again
      }
    }
    const onPile = tab === "pile";
    // A paste in flight has no caption to match, so it hides while searching (search spec 3.3).
    for (const tile of pending) tile.hidden = !onPile || match !== null;
    let previous = pending.at(-1) || null; // reels go after the pending tiles
    list.forEach((reel, i) => {
      let tile = tiles.get(reel.id);
      if (!tile) {
        tile = buildTile(reel);
        tiles.set(reel.id, tile);
      }
      updateTile(tile, reel, onPile && !match && i === 0, now); // ▶ marks the newest reel, not the newest match
      const expected = previous ? previous.nextSibling : grid.firstChild;
      if (tile !== expected) grid.insertBefore(tile, expected);
      previous = tile;
    });
    const pileTotal = reels.filter((reel) => inPile(reel, now)).length + pending.length;
    const favoriteTotal = reels.filter((reel) => reel.favorite).length;
    count.textContent = String(pileTotal);
    favoritesCount.textContent = favoriteTotal ? String(favoriteTotal) : "";
    for (const [name, button] of Object.entries(tabs)) button.setAttribute("aria-selected", String(name === tab));
    const total = onPile ? pileTotal : favoriteTotal;
    // The tab has reels but the search matches none of them (search spec 3.4).
    const noMatches = match !== null && total !== 0 && list.length === 0;
    grid.hidden = total === 0 || noMatches;
    emptySearch.hidden = !noMatches;
    empty.hidden = !onPile || total !== 0;
    emptyFavorites.hidden = onPile || total !== 0;
    document.body.classList.toggle("is-empty", onPile && total === 0);
  }

  function setTab(name) {
    if (name === tab) return;
    tab = name;
    render();
    window.scrollTo(0, 0);
  }

  // The tab that shows a reel: pile when it is in both.
  function tabOf(id) {
    const reel = reels.find((r) => r.id === id);
    if (!reel) return null;
    return inPile(reel, Date.now()) ? "pile" : "favorites";
  }

  function dropPending() {
    const tile = pending.pop();
    if (tile) tile.remove();
  }

  for (const [name, button] of Object.entries(tabs)) {
    button.addEventListener("click", () => setTab(name));
  }

  return {
    setReels(list) {
      reels = list.slice();
      render();
    },
    // The search's match, or null for none. No scrolling: the page would jump while someone types.
    setFilter(next) {
      match = next;
      render();
    },
    // Every reel, both tabs.
    getReels() {
      return reels.slice();
    },
    // The open tab's reels that match the search, in its order: the player's list.
    getShown() {
      return shown();
    },
    has(id) {
      return tiles.has(id);
    },
    remove(id) {
      reels = reels.filter((reel) => reel.id !== id);
      render();
    },
    // A reel starred or un-starred on this phone: the server's new JSON for it.
    update(reel) {
      reels = reels.map((r) => (r.id === reel.id ? reel : r));
      render();
    },
    favoriteCount() {
      return reels.filter((reel) => reel.favorite).length;
    },
    tabOf,
    setTab,
    // Add n optimistic tiles at the top, after any already there. A paste shows on the pile.
    addPending(n = 1) {
      setTab("pile");
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
    // Scroll to a reel, on the tab that shows it.
    reveal(id) {
      const where = tabOf(id);
      if (where) setTab(where);
      const tile = tiles.get(id);
      if (tile && tile.isConnected) tile.scrollIntoView({ block: "nearest", behavior: "smooth" });
    },
  };
}

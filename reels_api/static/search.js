import { icon } from "./icons.js";

// Case and accents don't count: "cafe" finds "Café" (search spec 3.2).
function fold(text) {
  return String(text || "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

// null when there is nothing to filter by; otherwise true for a reel from that source ("" is all)
// whose caption or title has every word, in any order (search spec 3.2).
export function makeMatch(text, source) {
  const words = fold(text).split(/\s+/).filter(Boolean);
  if (!words.length && !source) return null;
  return (reel) => {
    if (source && reel.source !== source) return false;
    const haystack = fold(`${reel.caption || ""} ${reel.title || ""}`);
    return words.every((word) => haystack.includes(word));
  };
}

// The search row under the tabs: behind a toggle on a phone, always shown on a desktop (search spec 3.1, 5.1).
// It never touches the board: every change goes out through onChange(match).
export function createSearch({ row, toggle, input, chips, clearButton, onChange }) {
  let source = "";

  function changed() {
    const match = makeMatch(input.value, source);
    if (match) setOpen(true); // a filter set in the desktop layout stays visible if the page narrows (phone rotated)
    onChange(match);
  }

  function setOpen(open) {
    row.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "close search" : "search");
    toggle.innerHTML = icon(open ? "x" : "search");
  }

  function setSource(next) {
    source = next;
    for (const chip of chips) chip.setAttribute("aria-pressed", String(chip.dataset.source === next));
  }

  function reset() {
    input.value = "";
    setSource("");
  }

  // Everything back as it was, row closed: the ✕, and a paste starting (search spec 3.5).
  function clear() {
    reset();
    setOpen(false);
    changed();
  }

  toggle.addEventListener("click", () => {
    if (row.classList.contains("is-open")) {
      clear();
      return;
    }
    setOpen(true);
    input.focus(); // inside the tap, so a phone brings up its keyboard
  });
  input.addEventListener("input", changed);
  input.addEventListener("search", changed); // the field's own clear button, in browsers that have one
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") input.blur(); // drops the phone keyboard; the filter stays
  });
  for (const chip of chips) {
    chip.addEventListener("click", () => {
      if (chip.dataset.source === source) return;
      setSource(chip.dataset.source);
      changed();
    });
  }
  // "clear search" under "nothing matches": the row stays open for the next try (search spec 3.4).
  clearButton.addEventListener("click", () => {
    reset();
    changed();
    input.focus(); // the button hides itself; keep keyboard and screen-reader users in the search
  });

  setOpen(false);
  return { clear };
}

import { icon } from "./icons.js";

const VISIBLE_MS = 2500;
const ACTION_MS = 5000; // long enough to reach "undo" (favorites spec 8)
let hideTimer = 0;
let active = null; // the action of the toast on screen, until it is tapped or its toast ends

// The toast on screen ended without its button being tapped: it timed out or was replaced.
function endActive() {
  const ended = active;
  active = null;
  if (ended && ended.onEnd) ended.onEnd();
}

// One toast at a time; a new one replaces the current one and restarts the timer (spec 8.1).
// action {label, onClick, onEnd}: a button, and 5 seconds instead of 2.5 (favorites spec 8).
// onClick runs on a tap; onEnd runs instead when the toast times out or another replaces it.
export function showToast(message, { error = false, action = null } = {}) {
  const root = document.getElementById("toast");
  endActive();
  const mark = document.createElement("span");
  mark.className = error ? "toast-mark error" : "toast-mark";
  mark.innerHTML = icon(error ? "circleAlert" : "check");
  const label = document.createElement("span");
  label.className = "toast-label";
  label.textContent = message;
  root.replaceChildren(mark, label);
  if (action) {
    active = action;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "toast-action";
    button.textContent = action.label;
    button.addEventListener("click", () => {
      if (active !== action) return;
      active = null;
      clearTimeout(hideTimer);
      root.classList.remove("show");
      action.onClick();
    });
    root.append(button);
  }
  root.classList.add("show");
  clearTimeout(hideTimer);
  hideTimer = setTimeout(
    () => {
      root.classList.remove("show");
      endActive();
    },
    action ? ACTION_MS : VISIBLE_MS,
  );
}

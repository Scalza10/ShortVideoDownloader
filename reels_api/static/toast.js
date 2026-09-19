import { icon } from "./icons.js";

const VISIBLE_MS = 2500;
let hideTimer = 0;

// One toast at a time; a new one replaces the current one and restarts the timer (spec 8.1).
export function showToast(message, { error = false } = {}) {
  const root = document.getElementById("toast");
  const mark = document.createElement("span");
  mark.className = error ? "toast-mark error" : "toast-mark";
  mark.innerHTML = icon(error ? "circleAlert" : "check");
  const label = document.createElement("span");
  label.textContent = message;
  root.replaceChildren(mark, label);
  root.classList.add("show");
  clearTimeout(hideTimer);
  hideTimer = setTimeout(() => root.classList.remove("show"), VISIBLE_MS);
}

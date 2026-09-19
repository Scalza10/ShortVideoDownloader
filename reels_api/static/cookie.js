import { Unauthorized, agreeToCookie, logout } from "./api.js";

// The same key and value as login.js, which is not a module and cannot import them. Keep them identical.
const CHOICE_KEY = "reels-cookie-choice";
const DECLINED = "declined";

// Storage throws in some private windows and when site data is blocked: then nothing is remembered.
function saveDeclined() {
  try {
    localStorage.setItem(CHOICE_KEY, DECLINED);
  } catch (_) {
    // the login page will ask instead of showing the declined state
  }
}

function forgetChoice() {
  try {
    localStorage.removeItem(CHOICE_KEY);
  } catch (_) {
    // nothing was saved
  }
}

// Asks a phone whose cookie was set before the login page asked (pop-up spec 6.2).
// It cannot be dismissed: the only ways out are "allow cookie" and "no thanks, log me out".
export function createCookieAsk({ dialog, onAccepted }) {
  const allow = dialog.querySelector("#cookie-allow");
  const decline = dialog.querySelector("#cookie-decline");
  const error = dialog.querySelector("#cookie-error");
  let agreed = false;

  function setBusy(busy) {
    allow.disabled = busy;
    decline.disabled = busy;
    if (busy) error.hidden = true;
  }

  function showError(message) {
    error.textContent = message;
    error.hidden = false;
    setBusy(false);
  }

  dialog.addEventListener("cancel", (event) => event.preventDefault()); // Esc
  // Chrome still closes a modal dialog on a repeated Esc; open it again until the person agrees.
  dialog.addEventListener("close", () => {
    if (!agreed) dialog.showModal();
  });

  allow.addEventListener("click", async () => {
    setBusy(true);
    try {
      await agreeToCookie();
    } catch (err) {
      if (err instanceof Unauthorized) return; // api() is already reloading
      showError("couldn't save that. try again.");
      return;
    }
    agreed = true;
    dialog.close();
    onAccepted();
  });

  decline.addEventListener("click", async () => {
    setBusy(true);
    saveDeclined(); // first, so a reload after a 401 still lands on the declined state
    try {
      await logout();
    } catch (err) {
      if (err instanceof Unauthorized) return; // api() is already reloading
      forgetChoice(); // the cookie is still there, so no "no" was given
      showError("couldn't log out. try again.");
      return;
    }
    location.replace("/"); // the login page there shows the declined state (cookie spec 4.2)
  });

  return {
    open() {
      dialog.showModal();
    },
  };
}

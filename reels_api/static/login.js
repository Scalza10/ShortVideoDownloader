(() => {
  "use strict";
  // Asks before the one cookie is set (cookie spec 4). A "yes" is the login cookie itself;
  // a "no" is remembered in this browser only and never sent to the server.
  const CHOICE_KEY = "reels-cookie-choice";
  const DECLINED = "declined";
  const GENERIC_ERROR = "Something went wrong. Try again.";
  const $ = (id) => document.getElementById(id);
  const ask = $("ask");
  const declined = $("declined");
  const lead = $("login-lead");
  const form = $("login-form");
  const input = $("passcode");
  const button = $("continue");
  const error = $("login-error");
  // The server only serves this page at /join/<token> for the right token (cookie spec 5.1).
  const inviteMode = location.pathname.startsWith("/join/");

  // Storage throws in some private windows and when site data is blocked: then nothing is remembered.
  function savedChoice() {
    try {
      return localStorage.getItem(CHOICE_KEY);
    } catch (_) {
      return null;
    }
  }

  function saveDeclined() {
    try {
      localStorage.setItem(CHOICE_KEY, DECLINED);
    } catch (_) {
      // declined for this visit only
    }
  }

  function forgetChoice() {
    try {
      localStorage.removeItem(CHOICE_KEY);
    } catch (_) {
      // nothing was saved
    }
  }

  function showAsk() {
    declined.hidden = true;
    ask.hidden = false;
    if (!inviteMode) input.focus();
  }

  function showDeclined() {
    ask.hidden = true;
    declined.hidden = false;
  }

  function showError(message) {
    error.textContent = message;
    error.hidden = false;
  }

  async function errorMessage(response) {
    try {
      return (await response.json()).message || GENERIC_ERROR;
    } catch (_) {
      return GENERIC_ERROR; // non-JSON body
    }
  }

  function sendAgreement() {
    if (inviteMode) return fetch(location.pathname, { method: "POST" });
    return fetch("/web/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passcode: input.value }),
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    button.disabled = true;
    try {
      const r = await sendAgreement();
      if (r.status === 204) {
        forgetChoice();
        if (inviteMode) {
          location.replace("/"); // the token leaves the address bar and the history entry
        } else {
          location.reload(); // keeps the query string, so a shared link still starts after login
        }
        return;
      }
      showError(await errorMessage(r));
    } catch (_) {
      showError("Network error. Try again.");
    } finally {
      button.disabled = false;
    }
  });

  $("decline").addEventListener("click", () => {
    saveDeclined();
    if (inviteMode) {
      location.replace("/"); // the login page there shows the declined state
    } else {
      showDeclined();
    }
  });

  $("reconsider").addEventListener("click", () => {
    forgetChoice();
    showAsk();
  });

  if (inviteMode) {
    // Opening an invite link is a fresh request: always ask, even after an earlier "no".
    lead.textContent = "you're invited";
    button.textContent = "allow cookie & join";
    input.hidden = true;
    input.disabled = true; // a disabled field is skipped by form validation
    showAsk();
  } else if (savedChoice() === DECLINED) {
    showDeclined();
  } else {
    showAsk();
  }
})();

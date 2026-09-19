import { Unauthorized, createJob, getJob } from "./api.js";
import { icon } from "./icons.js";
import { showToast } from "./toast.js";

const POLL_MS = 1500;
const desktop = matchMedia("(min-width: 700px)");

// The grey half of the error message, by the server's error code (spec 6.5).
const HINTS = {
  unsupported_url: "try the share link.",
  private_or_removed: "it's private or gone.",
  no_video: "there's no video in that one.",
  login_required: "that one needs a login.",
  platform_blocked: "got blocked. try again in a bit.",
  too_many_jobs: "too busy right now. try again in a minute.",
  network: "no connection. try again.",
};
const DEFAULT_HINT = "try again.";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Poll until the job settles: the done job, or {error: code}.
async function waitForJob(id) {
  for (;;) {
    try {
      const job = await getJob(id);
      if (job === null) return { error: "processing_failed" };
      if (job.status === "done") return job;
      if (job.status === "failed") return { error: job.error || "processing_failed" };
    } catch (err) {
      if (err instanceof Unauthorized) throw err;
      // network error: keep polling
    }
    await sleep(POLL_MS);
  }
}

// The paste field: idle, fetching and error (spec 6.5). One paste at a time, but one
// paste of an X post can bring several videos: onMore asks for their extra tiles, and
// onDone or onFail runs once per video (X links spec 7).
export function createPaste({ form, onStart, onMore, onDone, onFail, onStateChange }) {
  const input = form.querySelector("#paste-input");
  const submitButton = form.querySelector("#paste-submit");
  const iconSlot = form.querySelector("#paste-icon");
  const urlLine = form.querySelector("#paste-url");
  const errorRow = form.querySelector("#paste-error");
  const hint = form.querySelector("#paste-error-hint");
  let state = "idle";
  let submitted = "";

  function setState(next, code) {
    state = next;
    form.dataset.state = next;
    const fetching = next === "fetching";
    const error = next === "error";
    input.readOnly = fetching;
    submitButton.hidden = fetching;
    submitButton.disabled = error;
    iconSlot.innerHTML = fetching ? '<span class="spinner" aria-hidden="true"></span>' : icon(error ? "circleAlert" : "clipboard");
    if (fetching) input.value = "pulling it down…";
    if (error) input.value = submitted;
    urlLine.textContent = fetching ? submitted : "";
    urlLine.hidden = !fetching;
    hint.textContent = error ? HINTS[code] || DEFAULT_HINT : "";
    errorRow.hidden = !error;
    onStateChange(next);
  }

  async function run(text) {
    submitted = text;
    setState("fetching");
    input.blur(); // drop the phone keyboard
    onStart();
    let created;
    try {
      created = await createJob(text);
    } catch (err) {
      if (err instanceof Unauthorized) return; // the page is reloading to the login screen
      created = { error: "network" };
    }
    if (created.error) {
      onFail();
      setState("error", created.error);
      return;
    }
    const ids = created.ids || [created.id];
    if (ids.length > 1) onMore(ids.length - 1);
    // One at a time, so a slower pile reload never overwrites a newer one.
    let settled = Promise.resolve();
    let results;
    try {
      results = await Promise.all(
        ids.map(async (id) => {
          const result = await waitForJob(id);
          settled = settled.then(() => (result.error ? onFail() : onDone(result)));
          await settled;
          return result;
        }),
      );
    } catch (err) {
      if (err instanceof Unauthorized) return;
      throw err;
    }
    const failed = results.filter((result) => result.error);
    if (failed.length === results.length) {
      setState("error", failed[0].error);
      return;
    }
    if (failed.length) showToast(`${failed.length} of ${results.length} didn't come through`, { error: true });
    input.value = "";
    setState("idle");
  }

  function updatePlaceholder() {
    input.placeholder = desktop.matches ? "paste a link, hit enter" : "paste a link";
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (state !== "idle" || !text) return;
    run(text);
  });
  input.addEventListener("input", () => {
    if (state === "error") setState("idle"); // keeps what the user typed
  });
  desktop.addEventListener("change", updatePlaceholder);
  updatePlaceholder();
  setState("idle");

  return {
    // Start a paste from outside the form (the Android share target).
    submit(text) {
      const trimmed = text.trim();
      if (state === "fetching" || !trimmed) return;
      input.value = trimmed;
      run(trimmed);
    },
  };
}

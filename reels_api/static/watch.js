import { hydrateIcons } from "./icons.js";
import { createPlayer } from "./player.js";
import { showToast } from "./toast.js";

// The view-only page: one reel from a share link, no pile (links spec 6.1).
const reel = JSON.parse(document.getElementById("reel-data").textContent);

hydrateIcons(document);

// The video failed. If the reel is gone, reload so the server shows the expired page.
// Otherwise stay: reloading a clip the browser cannot play would loop forever.
async function onGone() {
  try {
    const response = await fetch(reel.file_url, { headers: { Range: "bytes=0-0" } });
    if (response.status === 401 || response.status === 404) {
      location.reload();
      return;
    }
  } catch (_) {
    // network error: say so below
  }
  showToast("couldn't play that one", { error: true });
}

const player = createPlayer({ root: document.getElementById("player"), onGone, standalone: true });
player.open([reel], reel.id, { gesture: false, push: false });

// Asks whoever pasted a reel X marks sensitive whether it goes on the pile (NSFW ask spec 3).
// Esc, or anything else that closes the dialog, counts as no.
export function createNsfwAsk({ dialog }) {
  const yes = dialog.querySelector("#nsfw-yes");
  const no = dialog.querySelector("#nsfw-no");
  let answer = null; // the waiting ask's resolve
  let said = false;

  yes.addEventListener("click", () => {
    said = true;
    dialog.close();
  });
  no.addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    const resolve = answer;
    answer = null;
    if (resolve) resolve(said);
  });

  return {
    // true for yes, false for no.
    ask() {
      said = false;
      dialog.showModal();
      return new Promise((resolve) => {
        answer = resolve;
      });
    },
  };
}

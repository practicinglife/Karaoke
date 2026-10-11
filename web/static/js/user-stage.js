// Shows START MY SONG while the stage screen is waiting for this singer.
const stageReadyBtn = document.getElementById("stage-ready-btn");

if (stageReadyBtn instanceof HTMLButtonElement) {
  const myName = String(stageReadyBtn.dataset.userName || "").trim().toLowerCase();
  const csrfInput = document.getElementById("user-csrf-token");

  function syncStageReady(state) {
    const next = state && state.next;
    const isMyTurn = Boolean(
      state &&
        state.state === "INTERMISSION" &&
        next &&
        String(next.user || "").trim().toLowerCase() === myName
    );
    stageReadyBtn.hidden = !isMyTurn;
    stageReadyBtn.disabled = false;
  }

  stageReadyBtn.addEventListener("click", async () => {
    stageReadyBtn.disabled = true;
    const form = new URLSearchParams();
    form.set("csrf_token", csrfInput instanceof HTMLInputElement ? csrfInput.value : "");
    try {
      const res = await fetch(stageReadyBtn.dataset.readyUrl, { method: "POST", body: form });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        alert(data.message || "Couldn't start your song. Ask the host.");
        stageReadyBtn.disabled = false;
        return;
      }
      stageReadyBtn.hidden = true;
    } catch (_error) {
      alert("Couldn't reach the karaoke host. Try again.");
      stageReadyBtn.disabled = false;
    }
  });

  syncStageReady(window.KT_STAGE_STATE || null);
  window.addEventListener("karaoke:stage-state", (event) => syncStageReady(event.detail));
}

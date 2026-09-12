/**
 * Member 3 — Automatic Sync Daemon.
 *
 * Watches connectivity (window.ononline) and tab visibility
 * (visibilitychange) to automatically flush any queued offline drafts the
 * moment a connection becomes available, without the artisan having to do
 * anything. Talks to Member 4's resumable chunk-upload + sync-batch-state
 * endpoints.
 */
const SyncDaemon = (() => {
  const API_BASE = window.KAARIGAR_API_BASE || "http://localhost:8000";
  const CHUNK_SIZE = 32 * 1024; // 32KB chunks — safe for 2G upload windows
  let syncing = false;
  let listeners = [];

  function onStateChange(cb) { listeners.push(cb); }
  function emitState(state, extra = {}) {
    listeners.forEach((cb) => cb({ state, ...extra }));
  }

  function init() {
    window.addEventListener("online", () => trySync("connectivity restored"));
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && navigator.onLine) {
        trySync("tab foregrounded");
      }
    });
    // Also poll gently in case 'online' events are unreliable on flaky 2G modems.
    setInterval(() => { if (navigator.onLine) trySync("periodic check"); }, 20000);

    emitState(navigator.onLine ? "online" : "offline");
    if (navigator.onLine) trySync("initial load");
  }

  async function trySync(reason) {
    if (syncing || !navigator.onLine) return;
    const drafts = await ArtisanDB.getQueuedDrafts();
    if (drafts.length === 0) {
      emitState("online", { queueCount: 0 });
      return;
    }

    syncing = true;
    emitState("syncing", { queueCount: drafts.length, reason });

    for (const draft of drafts) {
      try {
        await syncOneDraft(draft);
      } catch (err) {
        console.warn("Sync failed for draft, will retry later:", draft.clientBatchId, err);
        // leave draft queued — next trySync() call retries automatically
      }
    }

    syncing = false;
    const remaining = await ArtisanDB.getQueuedDrafts();
    emitState(remaining.length > 0 ? "offline" : "online", { queueCount: remaining.length });
  }

  async function syncOneDraft(draft) {
    // 1. ensure a SyncBatch row exists server-side
    await fetch(`${API_BASE}/sync/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_batch_id: draft.clientBatchId,
        artisan_id: draft.artisanId,
        total_chunks_expected: draft.totalChunksExpected,
      }),
    });

    // 2. upload every media file in chunks, resuming from what the server
    //    already has (so a mid-upload disconnect never restarts from zero)
    for (const fileMeta of draft.files) {
      const blobRecord = await ArtisanDB.getMediaBlob(fileMeta.blobKey);
      if (!blobRecord) continue;
      await uploadFileResumable(draft.clientBatchId, fileMeta, blobRecord.blob);
    }

    // 3. create the Product record from the uploaded files, then trigger the
    // AI pipeline (ASR -> extraction -> vision -> pricing). Both endpoints
    // take query params, not a JSON body.
    await ArtisanDB.updateDraftState(draft.clientBatchId, { syncState: "processing" });

    const audioFile = draft.files.find((f) => f.mediaType === "audio");
    const photoFiles = draft.files.filter((f) => f.mediaType === "photo");

    const params = new URLSearchParams();
    params.set("audio_file_id", audioFile.fileId);
    photoFiles.forEach((f) => params.append("photo_file_ids", f.fileId));

    const productResp = await fetch(
      `${API_BASE}/products/from-batch/${draft.clientBatchId}?${params.toString()}`,
      { method: "POST" }
    );
    if (!productResp.ok) throw new Error("Failed to create product from batch");
    const product = await productResp.json();

    const pipelineResp = await fetch(`${API_BASE}/pipeline/run/${product.id}`, {
      method: "POST",
    });
    if (!pipelineResp.ok) throw new Error("Pipeline run failed");
  }

  async function uploadFileResumable(clientBatchId, fileMeta, blob) {
    const totalChunks = Math.ceil(blob.size / CHUNK_SIZE);

    // ask server which chunks it already has, so a resumed upload skips them
    let alreadyReceived = [];
    try {
      const statusResp = await fetch(
        `${API_BASE}/upload/status/${clientBatchId}/${fileMeta.fileId}`
      );
      if (statusResp.ok) {
        alreadyReceived = (await statusResp.json()).received_chunk_indices || [];
      }
    } catch (_) { /* fine — assume none received, will re-upload everything */ }

    for (let i = 0; i < totalChunks; i++) {
      if (alreadyReceived.includes(i)) continue;

      const start = i * CHUNK_SIZE;
      const chunkBlob = blob.slice(start, start + CHUNK_SIZE);
      const form = new FormData();
      form.append("client_batch_id", clientBatchId);
      form.append("file_id", fileMeta.fileId);
      form.append("chunk_index", i);
      form.append("total_chunks", totalChunks);
      form.append("media_type", fileMeta.mediaType);
      form.append("chunk", chunkBlob);

      // eslint-disable-next-line no-await-in-loop
      const resp = await fetch(`${API_BASE}/upload/chunk`, { method: "POST", body: form });
      if (!resp.ok) throw new Error(`Chunk ${i} upload failed for ${fileMeta.fileId}`);
    }
  }

  return { init, onStateChange, trySync };
})();

document.addEventListener("DOMContentLoaded", () => SyncDaemon.init());

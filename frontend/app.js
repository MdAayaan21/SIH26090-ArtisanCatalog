/**
 * Member 2 — Frontend UI Lead.
 * Drives the camera capture screen, the large mic recording button, and the
 * full-screen readback confirmation card. Delegates persistence to
 * ArtisanDB (Member 3), compression to ImageCompression (Member 3), and
 * upload/sync to SyncDaemon (Member 3) / the backend pipeline (Members 1/4/5/6).
 */
(() => {
  const API_BASE = window.KAARIGAR_API_BASE || "http://localhost:8000";

  // TODO(onboarding): in the real app this comes from a login/registration
  // step. Hardcoded here so the capture flow can be exercised standalone.
  const CURRENT_ARTISAN_ID = window.KAARIGAR_ARTISAN_ID || "demo-artisan-id";

  const state = {
    photos: [],          // [{ fileId, blob }]
    audioBlob: null,
    audioFileId: null,
    mediaRecorder: null,
    recordedChunks: [],
    recordingStartedAt: null,
    timerInterval: null,
    currentClientBatchId: null,
    currentProductId: null,
  };

  // ---- element refs -------------------------------------------------------
  const $ = (id) => document.getElementById(id);
  const cameraFeed = $("camera-feed");
  const captureCanvas = $("capture-canvas");
  const shotStrip = $("shot-strip");
  const shotCount = $("shot-count");
  const btnShutter = $("btn-shutter");
  const btnReview = $("btn-review");
  const btnNextToMic = $("btn-next-to-mic");
  const btnMic = $("btn-mic");
  const micStatus = $("mic-status");
  const micWaveform = $("mic-waveform");
  const micTimer = $("mic-timer");
  const btnSubmitListing = $("btn-submit-listing");
  const readbackAudio = $("readback-audio");

  // ==========================================================================
  // Screen navigation
  // ==========================================================================
  function showScreen(id) {
    document.querySelectorAll(".screen").forEach((el) => el.classList.remove("active"));
    $(id).classList.add("active");
  }
  document.querySelectorAll(".back-button").forEach((btn) => {
    btn.addEventListener("click", () => showScreen(btn.dataset.target));
  });

  // ==========================================================================
  // Camera capture
  // ==========================================================================
  async function initCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1280 } },
        audio: false,
      });
      cameraFeed.srcObject = stream;
    } catch (err) {
      micStatus && (micStatus.textContent = "Camera access nahi mil paya");
      console.error("Camera init failed:", err);
    }
  }

  btnShutter.addEventListener("click", async () => {
    const ctx = captureCanvas.getContext("2d");
    captureCanvas.width = cameraFeed.videoWidth;
    captureCanvas.height = cameraFeed.videoHeight;
    ctx.drawImage(cameraFeed, 0, 0);

    const blob = await ImageCompression.compressCanvasToWebP(captureCanvas);
    const fileId = `photo_${Date.now()}_${state.photos.length}`;
    state.photos.push({ fileId, blob });

    renderShotStrip();
    flashShutter();
  });

  function renderShotStrip() {
    shotStrip.innerHTML = "";
    state.photos.forEach(({ blob }) => {
      const img = document.createElement("img");
      img.src = URL.createObjectURL(blob);
      shotStrip.appendChild(img);
    });
    shotCount.textContent = state.photos.length;
    btnReview.disabled = state.photos.length === 0;
    btnNextToMic.disabled = state.photos.length === 0;
  }

  function flashShutter() {
    btnShutter.animate(
      [{ transform: "scale(0.92)" }, { transform: "scale(1)" }],
      { duration: 150, easing: "ease-out" }
    );
  }

  btnNextToMic.addEventListener("click", () => showScreen("screen-voice"));

  // ==========================================================================
  // Mic recording
  // ==========================================================================
  btnMic.addEventListener("click", async () => {
    if (state.mediaRecorder && state.mediaRecorder.state === "recording") {
      stopRecording();
    } else {
      await startRecording();
    }
  });

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      state.recordedChunks = [];
      state.mediaRecorder = new MediaRecorder(stream, { mimeType: pickAudioMime() });
      state.mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) state.recordedChunks.push(e.data);
      };
      state.mediaRecorder.onstop = onRecordingStopped;
      state.mediaRecorder.start();

      state.recordingStartedAt = Date.now();
      startTimer();

      btnMic.classList.add("recording");
      micStatus.textContent = "Sun rahe hain... phir se dabaayein rokne ke liye";
      micWaveform.hidden = false;
      micTimer.hidden = false;
    } catch (err) {
      micStatus.textContent = "Microphone access nahi mil paya";
      console.error("Mic init failed:", err);
    }
  }

  function stopRecording() {
    if (state.mediaRecorder && state.mediaRecorder.state === "recording") {
      state.mediaRecorder.stop();
    }
    clearInterval(state.timerInterval);
    btnMic.classList.remove("recording");
    micWaveform.hidden = true;
  }

  function onRecordingStopped() {
    const mimeType = state.mediaRecorder.mimeType || "audio/webm";
    state.audioBlob = new Blob(state.recordedChunks, { type: mimeType });
    state.audioFileId = `audio_${Date.now()}`;
    micStatus.textContent = "Recording ho gayi ✓ — dubara record karne ke liye dabaayein";
    btnSubmitListing.disabled = false;
  }

  function pickAudioMime() {
    const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
    return candidates.find((m) => MediaRecorder.isTypeSupported(m)) || "";
  }

  function startTimer() {
    micTimer.textContent = "00:00";
    state.timerInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - state.recordingStartedAt) / 1000);
      const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
      const ss = String(elapsed % 60).padStart(2, "0");
      micTimer.textContent = `${mm}:${ss}`;
    }, 500);
  }

  // ==========================================================================
  // Submit listing: persist atomically to IndexedDB, then let SyncDaemon
  // handle upload whenever connectivity allows.
  // ==========================================================================
  btnSubmitListing.addEventListener("click", async () => {
    const clientBatchId = `batch_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    state.currentClientBatchId = clientBatchId;

    const files = [
      ...state.photos.map(({ fileId }) => ({ fileId, mediaType: "photo", blobKey: `${clientBatchId}:${fileId}` })),
      { fileId: state.audioFileId, mediaType: "audio", blobKey: `${clientBatchId}:${state.audioFileId}` },
    ];

    const mediaBlobs = [
      ...state.photos.map(({ fileId, blob }) => ({ blobKey: `${clientBatchId}:${fileId}`, blob })),
      { blobKey: `${clientBatchId}:${state.audioFileId}`, blob: state.audioBlob },
    ];

    const draft = {
      clientBatchId,
      artisanId: CURRENT_ARTISAN_ID,
      files,
      totalChunksExpected: files.length, // per-file chunk counts are computed at upload time
      syncState: "queued",
      createdAt: Date.now(),
    };

    await ArtisanDB.saveDraftAtomic(draft, mediaBlobs);

    showScreen("screen-processing");
    SyncDaemon.trySync("listing submitted");
    pollForPipelineResult(clientBatchId);
  });

  // ==========================================================================
  // Poll backend for pipeline completion, then show the readback card.
  // In production this could instead be a WebSocket push from the server;
  // polling keeps the 2G-friendly implementation simple and resumable.
  // ==========================================================================
  async function pollForPipelineResult(clientBatchId) {
    const maxAttempts = 40;
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const resp = await fetch(`${API_BASE}/sync/${clientBatchId}`);
        if (resp.ok) {
          const batch = await resp.json();
          if (batch.status === "awaiting_confirmation") {
            const product = await fetchProductForBatch(clientBatchId);
            if (product) return showReadback(product);
          }
          if (batch.status === "failed") {
            $("processing-label").textContent = "Kuch gadbad hui — dobara koshish karein";
            return;
          }
        }
      } catch (_) { /* offline mid-poll — keep trying, SyncDaemon will resume upload */ }
      // eslint-disable-next-line no-await-in-loop
      await new Promise((r) => setTimeout(r, 3000));
    }
  }

  async function fetchProductForBatch(clientBatchId) {
    const resp = await fetch(`${API_BASE}/products/artisan/${CURRENT_ARTISAN_ID}`);
    if (!resp.ok) return null;
    const products = await resp.json();
    // most recently updated product for this artisan is our candidate;
    // a production build would key this by sync_batch_id directly
    return products.sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))[0] || null;
  }

  // ==========================================================================
  // Readback confirmation card
  // ==========================================================================
  function showReadback(product) {
    state.currentProductId = product.id;
    $("readback-title").textContent = product.title || "Aapka utpaad";
    $("readback-desc").textContent = product.description || "";
    $("readback-price-value").textContent = `₹${Math.round(product.suggested_price || 0)}`;
    $("readback-fallback-note").hidden = !product.used_benchmark_fallback;

    const firstPhoto = (product.processed_photo_paths || [])[0];
    $("readback-photo").src = firstPhoto ? `${API_BASE}/media/${encodeURIComponent(firstPhoto)}` : "";

    showScreen("screen-readback");
  }

  $("btn-play-readback").addEventListener("click", () => {
    // Prefers a server-generated TTS clip when available; otherwise falls
    // back to the browser's built-in speech synthesis so playback never
    // depends on network availability at confirmation time.
    const title = $("readback-title").textContent;
    const price = $("readback-price-value").textContent;
    const desc = $("readback-desc").textContent;
    const utterance = new SpeechSynthesisUtterance(`${title}. ${desc}. Suggested price ${price}.`);
    speechSynthesis.speak(utterance);
  });

  $("btn-confirm").addEventListener("click", async () => {
    await fetch(`${API_BASE}/products/${state.currentProductId}/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmed: true }),
    });
    await ArtisanDB.updateDraftState(state.currentClientBatchId, { syncState: "committed" });
    showScreen("screen-done");
  });

  $("btn-reject").addEventListener("click", () => {
    resetCaptureState();
    showScreen("screen-camera");
  });

  $("btn-new-listing").addEventListener("click", () => {
    resetCaptureState();
    showScreen("screen-camera");
  });

  function resetCaptureState() {
    state.photos = [];
    state.audioBlob = null;
    state.audioFileId = null;
    state.currentClientBatchId = null;
    state.currentProductId = null;
    renderShotStrip();
    btnSubmitListing.disabled = true;
    micStatus.textContent = "Bolne ke liye button dabaayein";
    micTimer.hidden = true;
  }

  // ==========================================================================
  // Sync status bar wiring
  // ==========================================================================
  SyncDaemon.onStateChange(({ state: syncState, queueCount }) => {
    const bar = $("sync-bar");
    const label = $("sync-label");
    const count = $("queue-count");
    bar.dataset.state = syncState;
    label.textContent = {
      offline: "Offline — is phone par surakshit",
      syncing: "Sync ho raha hai...",
      online: "Online — sab sync ho gaya",
    }[syncState] || syncState;

    if (queueCount > 0) {
      count.hidden = false;
      count.textContent = `${queueCount} pending`;
    } else {
      count.hidden = true;
    }
  });

  // ==========================================================================
  // Boot
  // ==========================================================================
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("./sw.js").catch((err) => console.warn("SW register failed:", err));
  }
  initCamera();
})();

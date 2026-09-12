/**
 * Member 3 — Client-Side Image Compression.
 *
 * Converts a raw camera capture (canvas ImageData / Blob) into a WebP blob
 * under ~300 KB, iteratively lowering quality if needed. Runs entirely
 * client-side so a 2G upload never has to move a multi-MB JPEG.
 */
const ImageCompression = (() => {
  const TARGET_MAX_BYTES = 300 * 1024;
  const MIN_QUALITY = 0.4;
  const QUALITY_STEP = 0.1;

  /** @param {HTMLCanvasElement} canvas */
  async function compressCanvasToWebP(canvas, startQuality = 0.85) {
    let quality = startQuality;
    let blob = await canvasToBlob(canvas, quality);

    while (blob.size > TARGET_MAX_BYTES && quality > MIN_QUALITY) {
      quality -= QUALITY_STEP;
      blob = await canvasToBlob(canvas, quality);
    }

    // If still too large at minimum quality, downscale dimensions and retry once.
    if (blob.size > TARGET_MAX_BYTES) {
      const scaled = downscaleCanvas(canvas, 0.75);
      blob = await canvasToBlob(scaled, MIN_QUALITY);
    }

    return blob;
  }

  function canvasToBlob(canvas, quality) {
    return new Promise((resolve) => {
      canvas.toBlob((blob) => resolve(blob), "image/webp", quality);
    });
  }

  function downscaleCanvas(canvas, factor) {
    const scaled = document.createElement("canvas");
    scaled.width = Math.round(canvas.width * factor);
    scaled.height = Math.round(canvas.height * factor);
    const ctx = scaled.getContext("2d");
    ctx.drawImage(canvas, 0, 0, scaled.width, scaled.height);
    return scaled;
  }

  return { compressCanvasToWebP };
})();

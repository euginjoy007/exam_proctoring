let proctorStatus;
let violationCount;
let proctorVideo;
let proctorCanvas;
let violationBanner;
let centerMessage;
let debugBox;
let examForm;

let violations = 0;
let stream;
let audioContext;
let analyser;
let lastAnalyzeSuccessAt = Date.now();
let isAnalyzing = false;
let examStopped = false;
let latestFrameImageData = null;
let latestScreenImageData = null;
let screenStream = null;
let screenVideo = null;
let screenCaptureTimer = null;
let fullscreenEverEntered = false;
let phoneDetectionStreak = 0;
let movementScore = 0;
let previousMotionFrame = null;

const ENABLE_AUDIO_MONITORING = false;
const MOVEMENT_PULSE_MAX = 20;

const motionCanvas = document.createElement("canvas");
motionCanvas.width = 64;
motionCanvas.height = 48;
const motionCtx = motionCanvas.getContext("2d");

const violationLastSentAt = {};
const violationCooldownMs = {
  phone_detected: 1000,
  audio_noise: 10000,
  gaze_left: 4000,
  gaze_right: 4000,
};

function bindElements() {
  proctorStatus = document.getElementById("proctorStatus");
  violationCount = document.getElementById("violationCount");
  proctorVideo = document.getElementById("proctorVideo");
  proctorCanvas = document.getElementById("proctorCanvas");
  violationBanner = document.getElementById("violationBanner");
  centerMessage = document.getElementById("centerMessage");
  debugBox = document.getElementById("proctorDebug");
  examForm = document.getElementById("examForm");
}

function updateDebug(msg) {
  if (debugBox) {
    debugBox.innerText = `Proctor: ${msg}`;
  }
}

function canSendViolation(type) {
  const cooldown = violationCooldownMs[type] || 0;
  const now = Date.now();
  const last = violationLastSentAt[type] || 0;
  if (now - last < cooldown) {
    return false;
  }
  violationLastSentAt[type] = now;
  return true;
}

async function initProctoring() {
  bindElements();

  if (!proctorVideo || !proctorStatus) {
    return;
  }

  proctorStatus.textContent = "Starting...";
  updateDebug("Requesting camera...");

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: true,
      // Keep mic off during exam page load to avoid OS-level popups.
      audio: ENABLE_AUDIO_MONITORING,
    });
    if (ENABLE_AUDIO_MONITORING) {
      setupAudioMonitoring();
    }
    setupVideoPreview();
    // Do not auto-trigger getDisplayMedia on exam load; it causes browser share popup.
    // Screen checks are handled in the permissions step before exam start.
    requestFullscreen();
    watchVisibilityChanges();
    startFrameAnalysis();
    startHeartbeat();
    startLivenessWatchdog();

    proctorStatus.textContent = "Active";
    updateDebug("Camera ON ✅");
  } catch (error) {
    proctorStatus.textContent = "Permissions required";
    updateDebug(`Camera FAILED ❌ ${error.message}`);
    reportViolation("permissions_blocked");
  }
}

function setupVideoPreview() {
  if (!proctorVideo) return;
  proctorVideo.srcObject = stream;
  proctorVideo.play().catch(() => {});
  drawTrackingPoints();
}

async function initScreenMonitoring() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
    updateDebug("Screen capture API unavailable");
    return;
  }

  try {
    screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
    screenVideo = document.createElement("video");
    screenVideo.srcObject = screenStream;
    screenVideo.muted = true;
    screenVideo.playsInline = true;
    await screenVideo.play();

    const track = screenStream.getVideoTracks()[0];
    if (track) {
      track.onended = () => {
        screenStream = null;
        screenVideo = null;
        latestScreenImageData = null;
        if (screenCaptureTimer) {
          clearInterval(screenCaptureTimer);
          screenCaptureTimer = null;
        }
      };
    }

    screenCaptureTimer = setInterval(() => {
      if (examStopped) return;
      const screenShot = captureScreenSnapshot();
      if (screenShot) {
        latestScreenImageData = screenShot;
      }
    }, 1000);

    updateDebug("Screen monitoring ON ✅");
  } catch (_error) {
    updateDebug("Screen monitoring skipped");
  }
}

function setupAudioMonitoring() {
  audioContext = new (window.AudioContext || window.webkitAudioContext)();
  const source = audioContext.createMediaStreamSource(stream);
  analyser = audioContext.createAnalyser();
  analyser.fftSize = 256;
  source.connect(analyser);

  const data = new Uint8Array(analyser.frequencyBinCount);
  setInterval(() => {
    if (examStopped) return;
    analyser.getByteFrequencyData(data);
    const avg = data.reduce((a, b) => a + b, 0) / data.length;
    if (avg > 60) {
      reportViolation("audio_noise");
    }
  }, 3000);
}

async function enterFullscreen() {
  if (!document.documentElement.requestFullscreen || examStopped) return;
  try {
    await document.documentElement.requestFullscreen();
  } catch (_error) {
    // Browser can deny if this call is not in a user-gesture context.
    // We retry on later user interactions and do not auto-log fullscreen_denied.
  }
}

function requestFullscreen() {
  // Try immediately
  enterFullscreen();

  // Retry when user interacts (browser policies allow fullscreen on gestures)
  const retryOnGesture = () => {
    if (!document.fullscreenElement && !examStopped) {
      enterFullscreen();
    }
  };
  window.addEventListener("click", retryOnGesture, { passive: true });
  window.addEventListener("keydown", retryOnGesture);

  document.addEventListener("fullscreenchange", () => {
    if (document.fullscreenElement) {
      fullscreenEverEntered = true;
      return;
    }

    // Log exit only if fullscreen had actually been entered before.
    if (fullscreenEverEntered && !examStopped) {
      reportViolation("fullscreen_exit", captureScreenSnapshot());
      setTimeout(() => enterFullscreen(), 150);
    }
  });

  setInterval(() => {
    if (!examStopped && !document.fullscreenElement) {
      enterFullscreen();
    }
  }, 2000);
}

function watchVisibilityChanges() {
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      reportViolation("tab_hidden", captureScreenSnapshot());
    }
  });
  window.addEventListener("blur", () => reportViolation("window_blur", captureScreenSnapshot()));
}

function startFrameAnalysis() {
  const frameVideo = document.createElement("video");
  frameVideo.srcObject = stream;
  frameVideo.play().catch(() => {});

  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");

  async function sendFrame() {
    if (!stream || isAnalyzing || examStopped) return;
    if (frameVideo.readyState !== 4) return;

    isAnalyzing = true;
    updateDebug("Sending frame...");

    try {
      canvas.width = 320;
      canvas.height = 240;
      context.drawImage(frameVideo, 0, 0, canvas.width, canvas.height);
      const imageData = canvas.toDataURL("image/jpeg", 0.7);
      latestFrameImageData = imageData;

      const motion = detectMinuteMovement(canvas);
      movementScore = motion.score;

      const enablePhone = true;

      const response = await fetch("/proctor/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image: imageData, enable_phone: enablePhone }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();
      lastAnalyzeSuccessAt = Date.now();
      const resultViolations = result.violations || [];
      const faceDetected = !resultViolations.includes("no_face");
      updateDebug(`Analyze OK: Face=${faceDetected} | Motion=${movementScore.toFixed(1)}`);

      const phoneDetected = resultViolations.includes("phone_detected");
      if (phoneDetected) {
        phoneDetectionStreak += 1;
      } else {
        phoneDetectionStreak = 0;
      }

      const filteredViolations = resultViolations.filter((type) => {
        if (type !== "phone_detected") return true;
        // Require repeated phone detection across consecutive frames
        // to reduce false positives from single-frame misclassifications.
        return phoneDetectionStreak >= 1;
      });

      if (filteredViolations.length > 0) {
        filteredViolations.forEach((type) => reportViolation(type, imageData));
      }
      updateCenteringHint(filteredViolations);
    } catch (err) {
      updateDebug(`Analyze FAILED ❌ ${err.message}`);
      console.error("Proctor analyze error:", err);
    } finally {
      isAnalyzing = false;
    }
  }

  async function proctorLoop() {
    try {
      await sendFrame();
    } catch (err) {
      console.error("Loop error:", err);
    }

    if (!examStopped) {
      setTimeout(proctorLoop, 450);
    }
  }

  proctorLoop();
}

function startHeartbeat() {
  setInterval(async () => {
    if (examStopped) return;

    try {
      await fetch("/proctor/heartbeat", { method: "POST" });
    } catch (err) {
      console.error("Heartbeat error:", err);
    }
  }, 10000);
}

function startLivenessWatchdog() {
  setInterval(() => {
    if (examStopped) return;

    const inactiveFor = Date.now() - lastAnalyzeSuccessAt;
    if (inactiveFor > 15000) {
      examStopped = true;
      if (proctorStatus) {
        proctorStatus.textContent = "Disconnected";
      }
      updateDebug("Disconnected >15s, auto-submitting");
      alert("Proctor disconnected. Exam ending.");
      if (examForm) {
        examForm.submit();
      }
    }
  }, 2000);
}

function drawTrackingPoints() {
  if (!proctorCanvas || !proctorVideo) return;
  const ctx = proctorCanvas.getContext("2d");

  const render = () => {
    if (proctorVideo.readyState >= 2) {
      proctorCanvas.width = proctorVideo.videoWidth;
      proctorCanvas.height = proctorVideo.videoHeight;
      ctx.clearRect(0, 0, proctorCanvas.width, proctorCanvas.height);

      const cols = 20;
      const rows = 14;
      const marginX = proctorCanvas.width * 0.06;
      const marginY = proctorCanvas.height * 0.08;
      const usableW = proctorCanvas.width - marginX * 2;
      const usableH = proctorCanvas.height - marginY * 2;

      const pulse = Math.min(1, movementScore / MOVEMENT_PULSE_MAX);
      const radius = 1.2 + pulse * 1.6;
      const alpha = 0.28 + pulse * 0.6;
      ctx.fillStyle = `rgba(56, 189, 248, ${alpha})`;

      for (let r = 0; r < rows; r += 1) {
        for (let c = 0; c < cols; c += 1) {
          const x = marginX + (c / (cols - 1)) * usableW;
          const y = marginY + (r / (rows - 1)) * usableH;
          ctx.beginPath();
          ctx.arc(x, y, radius, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      ctx.strokeStyle = `rgba(56, 189, 248, ${0.2 + pulse * 0.25})`;
      ctx.lineWidth = 1;
      ctx.strokeRect(marginX, marginY, usableW, usableH);
    }

    requestAnimationFrame(render);
  };

  render();
}


function detectMinuteMovement(frameCanvas) {
  motionCtx.drawImage(frameCanvas, 0, 0, motionCanvas.width, motionCanvas.height);

  const data = motionCtx.getImageData(0, 0, motionCanvas.width, motionCanvas.height).data;
  const currentFrame = new Uint8Array(motionCanvas.width * motionCanvas.height);

  for (let i = 0, p = 0; i < data.length; i += 4, p += 1) {
    const gray = (data[i] * 0.299) + (data[i + 1] * 0.587) + (data[i + 2] * 0.114);
    currentFrame[p] = gray;
  }

  if (!previousMotionFrame) {
    previousMotionFrame = currentFrame;
    return { score: 0 };
  }

  let diffSum = 0;
  for (let i = 0; i < currentFrame.length; i += 1) {
    diffSum += Math.abs(currentFrame[i] - previousMotionFrame[i]);
  }
  previousMotionFrame = currentFrame;

  const avgDiff = diffSum / currentFrame.length;
  return { score: avgDiff };
}


function updateCenteringHint(violationsList) {
  if (!centerMessage) return;
  if (violationsList.includes("no_face")) {
    centerMessage.textContent = "No face detected - center yourself";
  } else if (violationsList.includes("multiple_faces")) {
    centerMessage.textContent = "Multiple faces detected";
  } else {
    centerMessage.textContent = "Face centered";
  }
}

function isSevereViolation(type) {
  return new Set([
    "phone_detected",
    "multiple_faces",
    "no_face",
    "permissions_blocked",
    "fullscreen_exit",
    "fullscreen_denied",
    "tab_hidden",
    "window_blur",
    "notes_detected",
    "book_detected",
    "paper_detected",
  ]).has(type);
}

function captureScreenSnapshot() {
  if (latestScreenImageData) return latestScreenImageData;
  if (!screenVideo || screenVideo.readyState < 2) return null;

  const canvas = document.createElement("canvas");
  canvas.width = 640;
  canvas.height = 360;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(screenVideo, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.75);
}

function shouldUseScreenSnapshot(type) {
  return new Set(["tab_hidden", "window_blur", "fullscreen_exit", "fullscreen_denied"]).has(type);
}

function captureViolationSnapshot(type = null) {
  if (type && shouldUseScreenSnapshot(type)) {
    return captureScreenSnapshot() || latestFrameImageData || null;
  }

  if (latestFrameImageData) return latestFrameImageData;
  if (!proctorVideo || proctorVideo.readyState < 2) return null;

  const canvas = document.createElement("canvas");
  canvas.width = 320;
  canvas.height = 240;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(proctorVideo, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.7);
}

async function reportViolation(type, screenshot = null) {
  if (!canSendViolation(type)) {
    return;
  }

  violations += 1;
  if (violationCount) {
    violationCount.textContent = violations.toString();
  }

  if (violationBanner) {
    violationBanner.textContent = `Violation: ${type.replaceAll("_", " ")}`;
  }

  try {
    const payload = { type };

    if (isSevereViolation(type)) {
      // Capture evidence for every severe event, including every phone detection.
      payload.screenshot = screenshot || captureViolationSnapshot(type);
    }

    await fetch("/proctor/violation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    console.error("Violation logging error:", err);
  }
}

window.addEventListener("DOMContentLoaded", () => {
  bindElements();
  const permissionsReady = localStorage.getItem("proctorPermissionsReady") === "true";
  if (!permissionsReady && proctorStatus) {
    proctorStatus.textContent = "Requesting permissions...";
  }
  initProctoring();
});

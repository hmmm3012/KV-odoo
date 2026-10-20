(function () {
    const MESSAGES = {
        invalid_credentials: "Mã nhân viên hoặc PIN không đúng.",
        too_many_attempts: "Quá nhiều lần thử. Vui lòng thử lại sau.",
        invalid_session: "Phiên làm việc đã hết hạn. Vui lòng đăng nhập lại.",
        missing_gps: "Không lấy được vị trí GPS. Hãy bật định vị và thử lại.",
        gps_inaccurate: "Tín hiệu GPS chưa đủ chính xác. HR sẽ xem xét.",
        outside_geofence: "Bạn đang ngoài phạm vi nơi làm việc.",
        no_location_configured: "Chưa cấu hình nơi làm việc.",
        unknown_location: "Không xác định được nơi làm việc. HR sẽ xem xét.",
        already_checked_in: "Bạn đã chấm công vào.",
        not_checked_in: "Bạn chưa chấm công vào.",
        device_revoked: "Thiết bị kiosk không còn hiệu lực.",
        duplicate_request: "Yêu cầu đã được xử lý.",
        invalid_event_type: "Loại chấm công không hợp lệ.",
        geolocation_denied: "Trình duyệt đã từ chối quyền vị trí. Mở cài đặt trang → Quyền → Vị trí → Cho phép, rồi nhấn Chấm công lại.",
        geolocation_insecure: "Trình duyệt chỉ cho phép GPS trên HTTPS. Hãy mở trang bằng https://.",
        missing_photo: "Không chụp được ảnh. Hãy cho phép camera và thử lại.",
        no_face: "Không thấy khuôn mặt trong ảnh. Hãy nhìn thẳng vào camera và chấm công lại.",
        multiple_faces: "Có nhiều khuôn mặt trong ảnh. Hãy để một mình trong khung hình và chụp lại.",
        face_too_small: "Khuôn mặt quá nhỏ. Hãy lại gần camera và chụp lại.",
        face_tilted: "Khuôn mặt bị nghiêng. Hãy giữ đầu thẳng và chụp lại.",
        face_turned: "Hãy nhìn thẳng vào camera và chụp lại.",
        face_mismatch: "Độ khớp chưa cao. HR sẽ xác minh.",
        face_low_match: "Độ khớp quá thấp. Hãy nhìn thẳng vào camera và chụp lại.",
        face_not_enrolled: "Chưa đăng ký khuôn mặt. HR sẽ xem xét.",
        face_check_unavailable: "Không kiểm tra được khuôn mặt. HR sẽ xem xét.",
        server_busy: "Máy chủ đang bận. Đang thử lại…",
        camera_denied: "Trình duyệt đã từ chối quyền camera. Mở cài đặt trang → Quyền → Camera → Cho phép, rồi nhấn Chấm công lại.",
        camera_insecure: "Trình duyệt chỉ cho phép camera trên HTTPS. Hãy mở trang bằng https://.",
        network: "Không kết nối được máy chủ.",
    };

    const app = document.getElementById("kv-attendance-app");
    if (!app) {
        return;
    }

    const loginPanel = app.querySelector('[data-panel="login"]');
    const statusPanel = app.querySelector('[data-panel="status"]');
    const loginForm = document.getElementById("kv-login-form");
    const loginBtn = document.getElementById("kv-login-btn");
    const checkBtn = document.getElementById("kv-check-btn");
    const logoutBtn = document.getElementById("kv-logout-btn");
    const messageEl = document.getElementById("kv-message");
    const clockEl = document.getElementById("kv-clock");
    const employeeEl = document.getElementById("kv-employee-name");
    const stateEl = document.getElementById("kv-state-label");
    const lastPunchEl = document.getElementById("kv-last-punch");
    let locationHintEl = document.getElementById("kv-location-hint");
    if (!locationHintEl && lastPunchEl) {
        locationHintEl = document.createElement("p");
        locationHintEl.id = "kv-location-hint";
        locationHintEl.className = "kv-location-hint";
        lastPunchEl.insertAdjacentElement("afterend", locationHintEl);
    }
    let videoEl = document.getElementById("kv-camera");
    let previewEl = document.getElementById("kv-camera-preview");
    let canvasEl = document.getElementById("kv-camera-canvas");
    let cameraHintEl = document.getElementById("kv-camera-hint");
    let cameraStream = null;
    let cameraRequestId = 0;
    let previewFrame = 0;

    function ensureCameraUi() {
        if (!statusPanel) {
            return;
        }
        let wrap = statusPanel.querySelector(".kv-camera-wrap");
        if (!wrap) {
            wrap = document.createElement("div");
            wrap.className = "kv-camera-wrap";
            const anchor = checkBtn || statusPanel.lastElementChild;
            if (anchor && anchor.parentNode === statusPanel) {
                statusPanel.insertBefore(wrap, anchor);
            } else {
                statusPanel.appendChild(wrap);
            }
        }
        videoEl = wrap.querySelector("video") || videoEl;
        if (!videoEl) {
            videoEl = document.createElement("video");
            videoEl.id = "kv-camera";
            wrap.appendChild(videoEl);
        }
        videoEl.setAttribute("autoplay", "autoplay");
        videoEl.setAttribute("playsinline", "true");
        videoEl.setAttribute("webkit-playsinline", "true");
        videoEl.setAttribute("muted", "muted");
        videoEl.setAttribute("x5-playsinline", "true");
        videoEl.setAttribute("x5-video-player-type", "h5");
        videoEl.setAttribute("x5-video-player-fullscreen", "false");
        videoEl.autoplay = true;
        videoEl.muted = true;
        videoEl.playsInline = true;
        videoEl.controls = false;
        videoEl.disablePictureInPicture = true;
        previewEl = wrap.querySelector(".kv-camera-preview");
        if (!previewEl) {
            previewEl = document.createElement("canvas");
            previewEl.id = "kv-camera-preview";
            previewEl.className = "kv-camera-preview";
            wrap.appendChild(previewEl);
        }
        if (!wrap.dataset.previewBound) {
            wrap.dataset.previewBound = "1";
            wrap.addEventListener("click", () => {
                keepVideoPlaying();
            });
        }
        if (!canvasEl) {
            canvasEl = document.createElement("canvas");
            canvasEl.id = "kv-camera-canvas";
            canvasEl.className = "kv-hidden";
            wrap.insertAdjacentElement("afterend", canvasEl);
        }
        if (!cameraHintEl) {
            cameraHintEl = document.createElement("p");
            cameraHintEl.id = "kv-camera-hint";
            cameraHintEl.className = "kv-location-hint";
            cameraHintEl.textContent = "Nhìn thẳng vào camera. Ảnh sẽ được kiểm tra trước khi chấm công.";
            (canvasEl || wrap).insertAdjacentElement("afterend", cameraHintEl);
        }
    }

    const DISPLAY_TZ = "Asia/Ho_Chi_Minh";

    function parseOdooDatetime(value) {
        if (!value) {
            return new Date();
        }
        if (value instanceof Date) {
            return value;
        }
        const raw = String(value).trim();
        const iso = raw.includes("T") ? raw : raw.replace(" ", "T");
        if (/[zZ]$/.test(iso) || /[+-]\d{2}:?\d{2}$/.test(iso)) {
            return new Date(iso);
        }
        return new Date(iso + "Z");
    }

    function formatTime(value) {
        const date = value ? parseOdooDatetime(value) : new Date();
        return date.toLocaleString("vi-VN", { hour12: false, timeZone: DISPLAY_TZ });
    }

    function showMessage(code, kind) {
        if (!code) {
            messageEl.hidden = true;
            messageEl.textContent = "";
            messageEl.className = "kv-message";
            return;
        }
        messageEl.hidden = false;
        messageEl.className = "kv-message is-" + (kind || "error");
        messageEl.textContent = MESSAGES[code] || code;
    }

    async function rpc(route, params) {
        const response = await fetch(route, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params: params || {},
                id: Date.now(),
            }),
        });
        if (!response.ok) {
            const error = new Error(response.status >= 500 ? "server_busy" : "network");
            error.retryable = response.status >= 500 || response.status === 429;
            throw error;
        }
        let payload;
        try {
            payload = await response.json();
        } catch (_err) {
            const error = new Error("server_busy");
            error.retryable = true;
            throw error;
        }
        if (payload.error) {
            throw new Error(payload.error.message || "Request failed");
        }
        return payload.result;
    }

    function sleep(ms) {
        return new Promise((resolve) => window.setTimeout(resolve, ms));
    }

    function retryDelayMs(retryAfter, attempt) {
        const base = Number(retryAfter) > 0 ? Number(retryAfter) : 2;
        return Math.min(8, base + attempt) * 1000;
    }

    async function punchWithRetry(params) {
        const maxTries = 6;
        let lastError;
        for (let attempt = 0; attempt < maxTries; attempt++) {
            try {
                const result = await rpc("/attendance/api/check", params);
                if (result && result.error === "server_busy") {
                    showMessage("server_busy", "warn");
                    await sleep(retryDelayMs(result.retry_after, attempt));
                    continue;
                }
                return result;
            } catch (error) {
                lastError = error;
                if (!error.retryable || attempt === maxTries - 1) {
                    throw error;
                }
                showMessage("server_busy", "warn");
                await sleep(retryDelayMs(3, attempt));
            }
        }
        throw lastError || new Error("server_busy");
    }

    function renderStatus(result) {
        const checkedIn = result.attendance_state === "checked_in";
        loginPanel.classList.add("kv-hidden");
        statusPanel.classList.remove("kv-hidden");
        employeeEl.textContent = result.employee_name || "";
        stateEl.textContent = checkedIn ? "Đang làm việc" : "Chưa chấm công vào";
        lastPunchEl.textContent = checkedIn
            ? "Vào lúc " + formatTime(result.check_in)
            : result.check_out
                ? "Ra lúc " + formatTime(result.check_out)
                : "";
        checkBtn.textContent = checkedIn ? "Chấm công ra" : "Chấm công vào";
        checkBtn.dataset.eventType = checkedIn ? "check_out" : "check_in";
        ensureCameraUi();
    }

    function renderLogin() {
        statusPanel.classList.add("kv-hidden");
        loginPanel.classList.remove("kv-hidden");
        document.getElementById("pin").value = "";
        setLocationHint("");
        stopCamera();
        setCameraHint("");
    }

    function setLocationHint(text, kind) {
        if (!locationHintEl) {
            return;
        }
        if (!text) {
            locationHintEl.hidden = true;
            locationHintEl.textContent = "";
            return;
        }
        locationHintEl.hidden = false;
        locationHintEl.className = "kv-location-hint" + (kind ? " is-" + kind : "");
        locationHintEl.textContent = text;
    }

    function locationErrorCode(error) {
        if (!window.isSecureContext) {
            return "geolocation_insecure";
        }
        if (error && error.code === 1) {
            return "geolocation_denied";
        }
        return "missing_gps";
    }

    function getPosition() {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) {
                reject(new Error("missing_gps"));
                return;
            }
            if (!window.isSecureContext) {
                reject(new Error("geolocation_insecure"));
                return;
            }
            navigator.geolocation.getCurrentPosition(
                (pos) => resolve(pos),
                (error) => reject(new Error(locationErrorCode(error))),
                { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
            );
        });
    }

    function workplaceHintFromResult(result) {
        if (!result || (result.ok === false && result.error === "invalid_session")) {
            return { text: MESSAGES.invalid_session, kind: "error" };
        }
        const name = result && result.location_name;
        const reason = result && result.error;
        if (name && reason === "outside_geofence") {
            return { text: "Vị trí gần nhất: " + name, kind: "warn" };
        }
        if (name) {
            return { text: "Vị trí hiện tại: " + name, kind: "ok" };
        }
        return { text: "Không xác định được nơi hiện tại", kind: "warn" };
    }

    async function applyWorkplaceHint(position) {
        if (!position || !position.coords) {
            return;
        }
        setLocationHint("Đang xác định vị trí…");
        const result = await rpc("/attendance/api/location", {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            gps_accuracy: position.coords.accuracy,
        });
        const hint = workplaceHintFromResult(result);
        setLocationHint(hint.text, hint.kind);
        return result;
    }

    async function requestClientLocation() {
        setLocationHint("Đang xin quyền vị trí từ trình duyệt…");
        return getPosition();
    }

    function setCameraHint(text, kind) {
        if (!cameraHintEl) {
            return;
        }
        if (!text) {
            cameraHintEl.hidden = true;
            cameraHintEl.textContent = "";
            return;
        }
        cameraHintEl.hidden = false;
        cameraHintEl.className = "kv-location-hint" + (kind ? " is-" + kind : "");
        cameraHintEl.textContent = text;
    }

    function cameraErrorCode(error) {
        if (!window.isSecureContext) {
            return "camera_insecure";
        }
        const name = error && (error.name || error.message) || "";
        if (name === "NotAllowedError" || name === "PermissionDeniedError" || name === "camera_denied") {
            return "camera_denied";
        }
        if (name === "camera_insecure") {
            return "camera_insecure";
        }
        return "missing_photo";
    }

    function stopPreviewLoop() {
        if (previewFrame) {
            window.cancelAnimationFrame(previewFrame);
            previewFrame = 0;
        }
    }

    function drawPreviewFrame() {
        previewFrame = window.requestAnimationFrame(drawPreviewFrame);
        if (!previewEl || !videoEl || !videoEl.videoWidth || !videoEl.videoHeight) {
            return;
        }
        if (previewEl.width !== videoEl.videoWidth || previewEl.height !== videoEl.videoHeight) {
            previewEl.width = videoEl.videoWidth;
            previewEl.height = videoEl.videoHeight;
        }
        const context = previewEl.getContext("2d");
        if (!context) {
            return;
        }
        context.drawImage(videoEl, 0, 0, previewEl.width, previewEl.height);
    }

    function startPreviewLoop() {
        stopPreviewLoop();
        drawPreviewFrame();
    }

    function keepVideoPlaying() {
        if (!videoEl || !cameraStream || !cameraStream.active) {
            return;
        }
        if (typeof videoEl.webkitExitFullscreen === "function" && videoEl.webkitDisplayingFullscreen) {
            videoEl.webkitExitFullscreen();
        }
        if (videoEl.paused) {
            videoEl.play().catch(() => {});
        }
    }

    function stopCamera() {
        cameraRequestId += 1;
        stopPreviewLoop();
        if (cameraStream) {
            cameraStream.getTracks().forEach((track) => track.stop());
            cameraStream = null;
        }
        if (videoEl) {
            videoEl.srcObject = null;
        }
    }

    function waitForVideoFrame() {
        if (videoEl && videoEl.videoWidth) {
            return Promise.resolve();
        }
        return new Promise((resolve) => {
            if (!videoEl) {
                resolve();
                return;
            }
            const timeout = window.setTimeout(() => {
                videoEl.removeEventListener("loadedmetadata", onReady);
                resolve();
            }, 2500);
            const onReady = () => {
                window.clearTimeout(timeout);
                videoEl.removeEventListener("loadedmetadata", onReady);
                resolve();
            };
            videoEl.addEventListener("loadedmetadata", onReady);
        });
    }

    async function acquireCameraStream() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error("missing_photo");
        }
        if (!window.isSecureContext) {
            throw new Error("camera_insecure");
        }
        if (cameraStream && cameraStream.active) {
            return cameraStream;
        }
        const requestId = ++cameraRequestId;
        setCameraHint("Đang xin quyền camera từ trình duyệt…");
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: false,
                video: {
                    facingMode: "user",
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                },
            });
            if (requestId !== cameraRequestId) {
                stream.getTracks().forEach((track) => track.stop());
                throw new Error("missing_photo");
            }
            if (cameraStream) {
                cameraStream.getTracks().forEach((track) => track.stop());
            }
            cameraStream = stream;
            return stream;
        } catch (error) {
            if (requestId === cameraRequestId) {
                const code = cameraErrorCode(error);
                setCameraHint(MESSAGES[code] || code, "error");
                throw new Error(code);
            }
            throw error;
        }
    }

    async function showCameraPreview() {
        ensureCameraUi();
        if (!cameraStream || !cameraStream.active) {
            await acquireCameraStream();
        }
        if (!videoEl || !cameraStream) {
            throw new Error("missing_photo");
        }
        if (videoEl.srcObject !== cameraStream) {
            videoEl.srcObject = cameraStream;
        }
        videoEl.muted = true;
        videoEl.playsInline = true;
        videoEl.setAttribute("playsinline", "true");
        videoEl.setAttribute("webkit-playsinline", "true");
        if (!videoEl.dataset.inlineBound) {
            videoEl.dataset.inlineBound = "1";
            const resume = () => keepVideoPlaying();
            videoEl.addEventListener("pause", resume);
            videoEl.addEventListener("webkitendfullscreen", resume);
            videoEl.addEventListener("ended", resume);
        }
        try {
            await videoEl.play();
        } catch (_error) {
            /* Autoplay can fail until the punch screen is visible; stream is still live. */
        }
        startPreviewLoop();
        await waitForVideoFrame();
        setCameraHint("Camera đã sẵn sàng. Hãy nhìn thẳng, rồi nhấn chấm công.", "ok");
        return cameraStream;
    }

    async function startCamera() {
        await acquireCameraStream();
        await showCameraPreview();
        return cameraStream;
    }

    function captureFaceImage() {
        if (!videoEl || !canvasEl || !videoEl.videoWidth) {
            throw new Error("missing_photo");
        }
        const maxWidth = 512;
        const scale = Math.min(1, maxWidth / videoEl.videoWidth);
        canvasEl.width = Math.max(1, Math.round(videoEl.videoWidth * scale));
        canvasEl.height = Math.max(1, Math.round(videoEl.videoHeight * scale));
        const context = canvasEl.getContext("2d");
        context.drawImage(videoEl, 0, 0, canvasEl.width, canvasEl.height);
        return canvasEl.toDataURL("image/jpeg", 0.62);
    }

    async function requestClientPhoto() {
        await startCamera();
        return captureFaceImage();
    }

    async function refreshStatus() {
        const result = await rpc("/attendance/api/status", {});
        if (!result.ok) {
            renderLogin();
            if (result.error && result.error !== "invalid_session") {
                showMessage(result.error, "error");
            }
            return result;
        }
        renderStatus(result);
        startCamera().catch(() => {});
        requestClientLocation()
            .then((position) => applyWorkplaceHint(position))
            .catch((error) => {
                setLocationHint(MESSAGES[(error && error.message)] || MESSAGES.missing_gps, "error");
            });
        return result;
    }

    loginForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        loginBtn.disabled = true;
        showMessage(false);
        ensureCameraUi();
        const locationPromise = requestClientLocation().catch((error) => error);
        const cameraPromise = acquireCameraStream().catch((error) => error);
        try {
            const result = await rpc("/attendance/api/login", {
                employee_code: document.getElementById("employee_code").value,
                pin: document.getElementById("pin").value,
                source: "personal_web",
            });
            if (!result.ok) {
                showMessage(result.error, "error");
                stopCamera();
                return;
            }
            renderStatus(result);
            const location = await locationPromise;
            const camera = await cameraPromise;
            if (location && location.message) {
                showMessage(location.message, "error");
            } else if (location && location.coords) {
                await applyWorkplaceHint(location).catch(() => {
                    setLocationHint(MESSAGES.network, "error");
                });
            }
            if (camera && camera.message) {
                showMessage(camera.message, "error");
            } else {
                await showCameraPreview().catch((error) => {
                    showMessage((error && error.message) || "missing_photo", "error");
                });
            }
        } catch (error) {
            showMessage("network", "error");
        } finally {
            loginBtn.disabled = false;
        }
    });

    checkBtn.addEventListener("click", async () => {
        checkBtn.disabled = true;
        showMessage(false);
        try {
            const [position, faceImage] = await Promise.all([
                requestClientLocation(),
                requestClientPhoto(),
            ]);
            const result = await punchWithRetry({
                event_type: checkBtn.dataset.eventType,
                latitude: position.coords.latitude,
                longitude: position.coords.longitude,
                gps_accuracy: position.coords.accuracy,
                face_image: faceImage,
                request_id: (crypto.randomUUID && crypto.randomUUID()) || String(Date.now()) + "-" + Math.random(),
                source: "personal_web",
            });
            if (result.error === "invalid_session") {
                renderLogin();
                showMessage("invalid_session", "error");
                return;
            }
            if (result.attendance_state) {
                renderStatus(result);
            }
            if (result.location_name || result.error) {
                const hint = workplaceHintFromResult(result);
                setLocationHint(hint.text, hint.kind);
            }
            if (result.result === "success") {
                showMessage(result.event_type === "check_out" ? "Đã chấm công ra." : "Đã chấm công vào.", "ok");
            } else if (result.result === "needs_review") {
                showMessage(result.error, "warn");
            } else {
                showMessage(result.error, "error");
            }
        } catch (error) {
            showMessage((error && error.message) || "network", "error");
        } finally {
            checkBtn.disabled = false;
        }
    });

    logoutBtn.addEventListener("click", async () => {
        stopCamera();
        await rpc("/attendance/api/logout", {});
        renderLogin();
        showMessage(false);
    });

    setInterval(() => {
        clockEl.textContent = formatTime();
    }, 1000);
    clockEl.textContent = formatTime();

    refreshStatus().catch(() => renderLogin());
})();

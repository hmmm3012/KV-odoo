(function () {
    const MESSAGES = {
        invalid_credentials: "Mã nhân viên hoặc PIN không đúng.",
        too_many_attempts: "Quá nhiều lần thử. Vui lòng thử lại sau.",
        invalid_session: "Phiên làm việc đã hết hạn. Vui lòng đăng nhập lại.",
        invalid_month: "Tháng không hợp lệ.",
        missing_gps: "Không lấy được vị trí GPS. Hãy bật định vị và thử lại.",
        gps_inaccurate: "Tín hiệu GPS chưa đủ chính xác. HR sẽ xem xét.",
        outside_geofence: "Bạn đang ngoài phạm vi nơi làm việc.",
        no_location_configured: "Chưa cấu hình nơi làm việc.",
        unknown_location: "Không thành công",
        already_checked_in: "Bạn đã chấm công vào.",
        not_checked_in: "Bạn chưa chấm công vào.",
        device_revoked: "Thiết bị kiosk không còn hiệu lực.",
        duplicate_request: "Yêu cầu đã được xử lý.",
        invalid_event_type: "Loại chấm công không hợp lệ.",
        geolocation_denied: "Trình duyệt đã từ chối quyền vị trí. Mở cài đặt trang → Quyền → Vị trí → Cho phép, rồi nhấn Chấm công lại.",
        geolocation_insecure: "Trình duyệt chỉ cho phép GPS trên HTTPS. Hãy mở trang bằng https://.",
        geolocation_timeout: "Chưa lấy được vị trí. Hãy tải lại trang hoặc mở bằng trình duyệt khác.",
        wifi_location_confirmed: "Đã xác nhận vị trí qua WiFi",
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
    const sheetPanel = app.querySelector('[data-panel="sheet"]');
    const loginForm = document.getElementById("kv-login-form");
    const loginBtn = document.getElementById("kv-login-btn");
    const checkBtn = document.getElementById("kv-check-btn");
    const logoutBtn = document.getElementById("kv-logout-btn");
    const messageEl = document.getElementById("kv-message");
    const messageTextEl = document.getElementById("kv-message-text");
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
    let wifiHintEl = document.getElementById("kv-wifi-hint");
    if (!wifiHintEl && locationHintEl) {
        wifiHintEl = document.createElement("p");
        wifiHintEl.id = "kv-wifi-hint";
        wifiHintEl.className = "kv-wifi-subtext";
        wifiHintEl.hidden = true;
        locationHintEl.insertAdjacentElement("afterend", wifiHintEl);
    }
    let videoEl = document.getElementById("kv-camera");
    let previewEl = document.getElementById("kv-camera-preview");
    let canvasEl = document.getElementById("kv-camera-canvas");
    let cameraHintEl = document.getElementById("kv-camera-hint");
    let cameraTapEl = document.getElementById("kv-camera-tap");
    let cameraWrapEl = null;
    let cameraStream = null;
    let cameraRequestId = 0;
    let cameraAcquirePending = false;
    let cameraFailed = false;
    let previewFrame = 0;

    function ensureCameraUi() {
        if (!statusPanel) {
            return;
        }
        let wrap = statusPanel.querySelector(".kv-camera-wrap");
        if (!wrap) {
            wrap = document.createElement("div");
            wrap.className = "kv-camera-wrap is-closed";
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
        cameraTapEl = wrap.querySelector(".kv-camera-tap");
        if (!cameraTapEl) {
            cameraTapEl = document.createElement("p");
            cameraTapEl.id = "kv-camera-tap";
            cameraTapEl.className = "kv-camera-tap";
            cameraTapEl.textContent = "Nhấn để mở camera";
            wrap.appendChild(cameraTapEl);
        }
        cameraWrapEl = wrap;
        if (!wrap.dataset.previewBound) {
            wrap.dataset.previewBound = "1";
            wrap.addEventListener("click", () => {
                if (!cameraStream || !cameraStream.active) {
                    if (!cameraAcquirePending) {
                        startCamera().catch(() => {});
                    }
                    return;
                }
                keepVideoPlaying();
            });
        }
        syncCameraTap();
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
            cameraHintEl.textContent = "Hãy nhìn vào camera và nhấn chấm công.";
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

    function formatPunchTime(value) {
        return parseOdooDatetime(value).toLocaleString("vi-VN", {
            hour12: false,
            timeZone: DISPLAY_TZ,
            hour: "2-digit",
            minute: "2-digit",
            day: "numeric",
            month: "numeric",
        });
    }

    function showMessage(code, kind) {
        if (!messageEl || !messageTextEl) {
            return;
        }
        if (!code) {
            messageEl.hidden = true;
            messageTextEl.textContent = "";
            messageEl.className = "kv-message";
            return;
        }
        messageEl.hidden = false;
        messageEl.className = "kv-message is-" + (kind || "error");
        messageTextEl.textContent = MESSAGES[code] || code;
    }

    const messageCloseBtn = document.getElementById("kv-message-close");
    if (messageCloseBtn) {
        messageCloseBtn.addEventListener("click", () => showMessage(false));
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

    let statusSnapshot = null;

    function formatWorkedDuration(checkIn) {
        const start = parseOdooDatetime(checkIn);
        if (!start || Number.isNaN(start.getTime())) {
            return "";
        }
        const totalMinutes = Math.max(0, Math.floor((Date.now() - start.getTime()) / 60000));
        const hours = Math.floor(totalMinutes / 60);
        const minutes = totalMinutes - hours * 60;
        const parts = [];
        if (hours) {
            parts.push(hours + " giờ");
        }
        parts.push(minutes + " phút");
        return "Đã làm " + parts.join(" ");
    }

    function renderWorkedTime() {
        if (!statusSnapshot || statusSnapshot.attendance_state !== "checked_in" || !statusSnapshot.check_in) {
            return;
        }
        lastPunchEl.textContent = "Vào lúc " + formatPunchTime(statusSnapshot.check_in) + ". " + formatWorkedDuration(statusSnapshot.check_in) + ".";
    }

    function renderStatus(result) {
        const checkedIn = result.attendance_state === "checked_in";
        statusSnapshot = result;
        loginPanel.classList.add("kv-hidden");
        if (sheetPanel) {
            sheetPanel.classList.add("kv-hidden");
        }
        statusPanel.classList.remove("kv-hidden");
        employeeEl.textContent = result.employee_name || "";
        stateEl.textContent = checkedIn ? "Đang làm việc" : "Chưa chấm công vào";
        if (checkedIn) {
            renderWorkedTime();
        } else {
            lastPunchEl.textContent = result.check_out
                ? "Ra lúc " + formatPunchTime(result.check_out)
                : "";
        }
        checkBtn.textContent = checkedIn ? "Chấm công ra" : "Chấm công vào";
        checkBtn.dataset.eventType = checkedIn ? "check_out" : "check_in";
        ensureCameraUi();
        startLocationPolling();
    }

    function renderLogin() {
        stopLocationPolling();
        statusPanel.classList.add("kv-hidden");
        if (sheetPanel) {
            sheetPanel.classList.add("kv-hidden");
        }
        loginPanel.classList.remove("kv-hidden");
        statusSnapshot = null;
        document.getElementById("pin").value = "";
        setLocationHint("");
        setWifiFallbackHint(false);
        stopCamera();
        setCameraHint("");
    }

    function setWifiFallbackHint(visible) {
        if (!wifiHintEl) {
            return;
        }
        if (!visible) {
            wifiHintEl.hidden = true;
            return;
        }
        wifiHintEl.hidden = false;
        wifiHintEl.textContent = "(đang lấy vị trí qua wifi)";
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

    const USER_AGENT = navigator.userAgent || "";
    const IN_APP_BROWSER = /Zalo|FBAN|FBAV|FB_IAB|FBIOS|Messenger|Instagram|Line\/|MicroMessenger|TikTok|musical_ly|BytedanceWebview|; wv\)/i.test(USER_AGENT)
        || (/iPhone|iPad|iPod/i.test(USER_AGENT) && !/Safari\//i.test(USER_AGENT));

    function showLocationError(code) {
        setWifiFallbackHint(false);
        const permissionIssue = code === "geolocation_timeout" || code === "geolocation_denied";
        if (IN_APP_BROWSER && permissionIssue) {
            setLocationHint("Chưa lấy được vị trí. Hãy tải lại trang hoặc mở bằng trình duyệt.", "error");
            return;
        }
        setLocationHint(MESSAGES[code] || MESSAGES.missing_gps, "error");
    }

    const REPORTED_LOCATION_ISSUES = ["geolocation_timeout", "geolocation_denied", "missing_gps", "geolocation_insecure"];

    function reportLocationIssue(code) {
        if (!REPORTED_LOCATION_ISSUES.includes(code)) {
            return;
        }
        rpc("/attendance/api/client_issue", { issue_code: code }).catch(() => {});
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

    /* getCurrentPosition's own timeout ignores the time spent on the permission prompt,
       and some in-app WebViews never answer it, so the wait is capped here. */
    const LOCATION_TIMEOUT_MS = 10000;
    const POLL_LOCATION_MAX_AGE_MS = 15000;
    let nativeLocation = null;
    let nativeLocationStartedAt = 0;

    function requestNativePosition(allowRestart, maximumAge) {
        const stale = Date.now() - nativeLocationStartedAt >= LOCATION_TIMEOUT_MS;
        if (nativeLocation && !(allowRestart && stale)) {
            return nativeLocation;
        }
        const request = new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(
                (pos) => resolve(pos),
                (error) => reject(new Error(locationErrorCode(error))),
                { enableHighAccuracy: true, timeout: LOCATION_TIMEOUT_MS, maximumAge: maximumAge || 0 }
            );
        });
        nativeLocation = request;
        nativeLocationStartedAt = Date.now();
        const clear = () => {
            if (nativeLocation === request) {
                nativeLocation = null;
            }
        };
        request.then(clear, clear);
        return request;
    }

    function getPosition(allowRestart, maximumAge) {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) {
                reject(new Error("missing_gps"));
                return;
            }
            if (!window.isSecureContext) {
                reject(new Error("geolocation_insecure"));
                return;
            }
            const timer = window.setTimeout(() => reject(new Error("geolocation_timeout")), LOCATION_TIMEOUT_MS);
            requestNativePosition(allowRestart, maximumAge)
                .then(resolve, reject)
                .finally(() => window.clearTimeout(timer));
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
        return { text: "Đang nằm ngoài phạm vi đơn vị", kind: "warn" };
    }

    function wifiConfirmedHint(result) {
        const name = result && result.location_name;
        if (name) {
            return { text: MESSAGES.wifi_location_confirmed + ": " + name, kind: "ok" };
        }
        return { text: MESSAGES.wifi_location_confirmed, kind: "ok" };
    }

    function punchAccepted(result) {
        return Boolean(result && (result.result === "success" || result.result === "needs_review"));
    }

    function punchRefusedForMissingGps(result) {
        if (!result || punchAccepted(result)) {
            return false;
        }
        return result.error === "missing_gps" || result.error === "unknown_location";
    }

    function applyPunchLocationHint(result, gpsError) {
        if (gpsError && punchAccepted(result) && result.location_name) {
            const hint = wifiConfirmedHint(result);
            setLocationHint(hint.text, hint.kind);
            setWifiFallbackHint(true);
            return;
        }
        if (gpsError && punchAccepted(result)) {
            setLocationHint("");
            setWifiFallbackHint(true);
            return;
        }
        if (gpsError && punchRefusedForMissingGps(result)) {
            showLocationError(gpsError);
            return;
        }
        if (result && (result.location_name || result.error)) {
            const hint = workplaceHintFromResult(result);
            setLocationHint(hint.text, hint.kind);
        }
        if (gpsError) {
            setWifiFallbackHint(true);
        }
    }

    async function applyWorkplaceHint(position, options) {
        const quiet = options && options.quiet;
        const hasCoords = Boolean(position && position.coords);
        setWifiFallbackHint(!hasCoords);
        if (!quiet) {
            setLocationHint("Đang xác định vị trí…");
        }
        const payload = {};
        if (hasCoords) {
            payload.latitude = position.coords.latitude;
            payload.longitude = position.coords.longitude;
            payload.gps_accuracy = position.coords.accuracy;
        }
        const result = await rpc("/attendance/api/location", payload);
        const hint = workplaceHintFromResult(result);
        setLocationHint(hint.text, hint.kind);
        return result;
    }

    async function geolocationPermissionState() {
        if (!navigator.permissions || !navigator.permissions.query) {
            return "";
        }
        try {
            const status = await navigator.permissions.query({ name: "geolocation" });
            return (status && status.state) || "";
        } catch (_error) {
            return "";
        }
    }

    async function requestClientLocation(options) {
        const quiet = options && options.quiet;
        const permission = await geolocationPermissionState();
        if (permission === "denied") {
            setWifiFallbackHint(true);
            throw new Error("geolocation_denied");
        }
        if (!quiet) {
            setLocationHint("Đang xin quyền vị trí…");
        }
        return getPosition(!quiet, quiet ? POLL_LOCATION_MAX_AGE_MS : 0);
    }

    const LOCATION_POLL_MS = 30000;
    let locationPollTimer = null;
    let locationPollInFlight = false;

    function isStatusPanelVisible() {
        return Boolean(statusPanel && !statusPanel.classList.contains("kv-hidden"));
    }

    async function pollWorkplaceLocation() {
        if (locationPollInFlight || document.hidden || !isStatusPanelVisible() || checkBtn.disabled) {
            return;
        }
        locationPollInFlight = true;
        try {
            const position = await requestClientLocation({ quiet: true });
            await applyWorkplaceHint(position, { quiet: true });
        } catch (_error) {
            await applyWorkplaceHint(null, { quiet: true }).catch(() => null);
        } finally {
            locationPollInFlight = false;
        }
    }

    function stopLocationPolling() {
        if (locationPollTimer) {
            window.clearInterval(locationPollTimer);
            locationPollTimer = null;
        }
    }

    function startLocationPolling() {
        stopLocationPolling();
        if (!isStatusPanelVisible() || document.hidden) {
            return;
        }
        locationPollTimer = window.setInterval(() => {
            pollWorkplaceLocation();
        }, LOCATION_POLL_MS);
    }

    function previewHasFrame() {
        return Boolean(videoEl && videoEl.videoWidth && videoEl.videoHeight && !videoEl.paused);
    }

    function syncCameraTap() {
        const show = !cameraFailed && !previewHasFrame();
        if (cameraTapEl) {
            cameraTapEl.hidden = !show;
        }
        if (cameraWrapEl) {
            cameraWrapEl.classList.toggle("is-closed", show);
        }
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
            if (cameraWrapEl) {
                const ratio = Math.min(1.34, Math.max(0.56, videoEl.videoWidth / videoEl.videoHeight));
                cameraWrapEl.style.setProperty("--kv-cam-ratio", ratio.toFixed(3));
            }
        }
        const context = previewEl.getContext("2d");
        if (!context) {
            return;
        }
        context.drawImage(videoEl, 0, 0, previewEl.width, previewEl.height);
        if (!videoEl.paused) {
            syncCameraTap();
        }
    }

    function startPreviewLoop() {
        stopPreviewLoop();
        drawPreviewFrame();
    }

    function keepVideoPlaying() {
        if (!videoEl || !cameraStream || !cameraStream.active) {
            syncCameraTap();
            return;
        }
        if (typeof videoEl.webkitExitFullscreen === "function" && videoEl.webkitDisplayingFullscreen) {
            videoEl.webkitExitFullscreen();
        }
        if (videoEl.paused) {
            videoEl.play().then(() => syncCameraTap()).catch(() => syncCameraTap());
            return;
        }
        syncCameraTap();
    }

    function stopCamera() {
        cameraRequestId += 1;
        cameraAcquirePending = false;
        stopPreviewLoop();
        if (cameraStream) {
            cameraStream.getTracks().forEach((track) => track.stop());
            cameraStream = null;
        }
        if (videoEl) {
            videoEl.srcObject = null;
        }
        syncCameraTap();
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
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.isSecureContext) {
            cameraFailed = true;
            syncCameraTap();
            throw new Error(window.isSecureContext ? "missing_photo" : "camera_insecure");
        }
        if (cameraStream && cameraStream.active) {
            return cameraStream;
        }
        const requestId = ++cameraRequestId;
        cameraAcquirePending = true;
        cameraFailed = false;
        syncCameraTap();
        setCameraHint("Đang xin quyền camera…");
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
                cameraFailed = true;
                syncCameraTap();
                const code = cameraErrorCode(error);
                setCameraHint(MESSAGES[code] || code, "error");
                throw new Error(code);
            }
            throw error;
        } finally {
            if (requestId === cameraRequestId) {
                cameraAcquirePending = false;
            }
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
            /* iOS in-app browsers (Zalo) block autoplay until the preview is tapped. */
        }
        syncCameraTap();
        startPreviewLoop();
        await waitForVideoFrame();
        syncCameraTap();
        if (previewHasFrame()) {
            setCameraHint("Hãy nhìn vào camera và nhấn chấm công.", "ok");
        } else {
            setCameraHint("Nhấn vào khung hình để mở camera.", "warn");
        }
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
        requestClientLocation()
            .then((position) => applyWorkplaceHint(position))
            .catch((error) => {
                reportLocationIssue(error && error.message);
                return applyWorkplaceHint(null).catch(() => null);
            })
            .finally(() => startCamera().catch(() => {}));
        return result;
    }

    loginForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        loginBtn.disabled = true;
        showMessage(false);
        ensureCameraUi();
        const locationPromise = requestClientLocation().catch((error) => error);
        const cameraPromise = locationPromise.then(() => acquireCameraStream().catch((error) => error));
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
                reportLocationIssue(location.message);
                await applyWorkplaceHint(null).catch(() => null);
            } else if (location && location.coords) {
                await applyWorkplaceHint(location).catch(() => {
                    setLocationHint(MESSAGES.network, "error");
                });
            }
            startLocationPolling();
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

    const confirmEl = document.getElementById("kv-confirm");
    const confirmTextEl = document.getElementById("kv-confirm-text");
    const confirmOkBtn = document.getElementById("kv-confirm-ok");
    const confirmCancelBtn = document.getElementById("kv-confirm-cancel");

    function askConfirm(message) {
        if (!confirmEl || !confirmTextEl || !confirmOkBtn || !confirmCancelBtn) {
            return Promise.resolve(window.confirm(message));
        }
        return new Promise((resolve) => {
            confirmTextEl.textContent = message;
            confirmEl.hidden = false;
            const finish = (value) => {
                confirmEl.hidden = true;
                confirmOkBtn.removeEventListener("click", onOk);
                confirmCancelBtn.removeEventListener("click", onCancel);
                confirmEl.removeEventListener("click", onBackdrop);
                resolve(value);
            };
            const onOk = () => finish(true);
            const onCancel = () => finish(false);
            const onBackdrop = (event) => {
                if (event.target === confirmEl) {
                    finish(false);
                }
            };
            confirmOkBtn.addEventListener("click", onOk);
            confirmCancelBtn.addEventListener("click", onCancel);
            confirmEl.addEventListener("click", onBackdrop);
        });
    }

    checkBtn.addEventListener("click", async () => {
        if (checkBtn.disabled) {
            return;
        }
        const eventType = checkBtn.dataset.eventType || "check_in";
        let confirmMessage = "Xác nhận chấm công vào?";
        if (eventType === "check_out") {
            const worked = statusSnapshot && statusSnapshot.check_in
                ? formatWorkedDuration(statusSnapshot.check_in)
                : "";
            confirmMessage = worked
                ? "Xác nhận chấm công ra?\n" + worked + "."
                : "Xác nhận chấm công ra?";
        }
        const confirmed = await askConfirm(confirmMessage);
        if (!confirmed) {
            return;
        }
        checkBtn.disabled = true;
        showMessage(false);
        try {
            const locationAttempt = requestClientLocation().then(
                (position) => {
                    setWifiFallbackHint(false);
                    return { position: position, gpsError: null };
                },
                (error) => {
                    const gpsError = error && error.message;
                    reportLocationIssue(gpsError);
                    setWifiFallbackHint(true);
                    return { position: null, gpsError: gpsError };
                }
            );
            const faceImage = await requestClientPhoto();
            const located = await locationAttempt;
            const coords = located.position && located.position.coords;
            const gpsError = located.gpsError;
            const result = await punchWithRetry({
                event_type: eventType,
                latitude: coords ? coords.latitude : false,
                longitude: coords ? coords.longitude : false,
                gps_accuracy: coords ? coords.accuracy : false,
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
            applyPunchLocationHint(result, gpsError);
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

    let sheetYear = 0;
    let sheetMonth = 0;

    function currentSheetMonth() {
        const parts = new Intl.DateTimeFormat("en-US", {
            timeZone: DISPLAY_TZ,
            year: "numeric",
            month: "numeric",
        }).formatToParts(new Date());
        const values = {};
        parts.forEach((part) => {
            values[part.type] = part.value;
        });
        return { year: Number(values.year), month: Number(values.month) };
    }

    function previousSheetMonth() {
        if (sheetMonth <= 1) {
            return { year: sheetYear - 1, month: 12 };
        }
        return { year: sheetYear, month: sheetMonth - 1 };
    }

    function nextSheetMonth() {
        if (sheetMonth >= 12) {
            return { year: sheetYear + 1, month: 1 };
        }
        return { year: sheetYear, month: sheetMonth + 1 };
    }

    const sheetNextBtn = document.getElementById("kv-sheet-next");

    function renderSheet(result) {
        const title = document.getElementById("kv-sheet-title");
        const rowsEl = document.getElementById("kv-sheet-rows");
        const totalEl = document.getElementById("kv-sheet-total");
        if (!title || !rowsEl || !totalEl) {
            return;
        }
        sheetYear = result.year;
        sheetMonth = result.month;
        if (sheetNextBtn) {
            const current = currentSheetMonth();
            sheetNextBtn.disabled = sheetYear * 12 + sheetMonth >= current.year * 12 + current.month;
        }
        title.textContent = result.month_label || "Bảng công";
        rowsEl.textContent = "";
        const rows = result.rows || [];
        if (!rows.length) {
            const empty = document.createElement("p");
            empty.className = "kv-sheet-empty";
            empty.textContent = "Không có ca trong tháng này.";
            rowsEl.appendChild(empty);
        } else {
            rows.forEach((row) => {
                const item = document.createElement("article");
                item.className = "kv-sheet-row";
                const date = document.createElement("p");
                date.className = "kv-sheet-date";
                date.textContent = row.date || "";
                const times = document.createElement("p");
                times.textContent = "Vào " + (row.check_in || "—") + " · Ra " + (row.check_out || "—");
                const hours = document.createElement("p");
                hours.textContent = "Giờ công " + (row.hours || "0:00");
                const overtime = document.createElement("p");
                overtime.textContent = "Giờ làm thêm " + (row.overtime_hours || "0:00");
                item.appendChild(date);
                item.appendChild(times);
                item.appendChild(hours);
                item.appendChild(overtime);
                if (row.note) {
                    const note = document.createElement("p");
                    note.className = "kv-sheet-note";
                    note.textContent = row.note;
                    item.appendChild(note);
                }
                rowsEl.appendChild(item);
            });
        }
        totalEl.textContent = (result.shift_count || 0) + " ca · " + (result.total_hours || "0:00") + " giờ công · " + (result.total_overtime_hours || "0:00") + " giờ làm thêm";
    }

    async function loadSheet(year, month) {
        showMessage(false);
        const result = await rpc("/attendance/api/sheet", { year: year, month: month });
        if (!result.ok) {
            if (result.error === "invalid_session") {
                renderLogin();
            }
            showMessage(result.error || "network", "error");
            return;
        }
        stopLocationPolling();
        renderSheet(result);
        loginPanel.classList.add("kv-hidden");
        statusPanel.classList.add("kv-hidden");
        sheetPanel.classList.remove("kv-hidden");
        stopCamera();
    }

    const sheetOpenBtn = document.getElementById("kv-sheet-open");
    if (sheetOpenBtn && sheetPanel) {
        sheetOpenBtn.addEventListener("click", async () => {
            const current = currentSheetMonth();
            try {
                await loadSheet(current.year, current.month);
            } catch (_error) {
                showMessage("network", "error");
            }
        });
        document.getElementById("kv-sheet-prev").addEventListener("click", async () => {
            const target = previousSheetMonth();
            try {
                await loadSheet(target.year, target.month);
            } catch (_error) {
                showMessage("network", "error");
            }
        });
        if (sheetNextBtn) {
            sheetNextBtn.addEventListener("click", async () => {
                if (sheetNextBtn.disabled) {
                    return;
                }
                const target = nextSheetMonth();
                try {
                    await loadSheet(target.year, target.month);
                } catch (_error) {
                    showMessage("network", "error");
                }
            });
        }
        document.getElementById("kv-sheet-back").addEventListener("click", () => {
            sheetPanel.classList.add("kv-hidden");
            statusPanel.classList.remove("kv-hidden");
            showMessage(false);
            startCamera().catch(() => {});
            startLocationPolling();
            pollWorkplaceLocation();
        });
    }

    logoutBtn.addEventListener("click", async () => {
        stopLocationPolling();
        stopCamera();
        await rpc("/attendance/api/logout", {});
        renderLogin();
        showMessage(false);
    });

    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            stopLocationPolling();
            return;
        }
        if (!isStatusPanelVisible()) {
            return;
        }
        startLocationPolling();
        pollWorkplaceLocation();
    });

    setInterval(() => {
        clockEl.textContent = formatTime();
        renderWorkedTime();
    }, 1000);
    clockEl.textContent = formatTime();

    refreshStatus().catch(() => renderLogin());
})();

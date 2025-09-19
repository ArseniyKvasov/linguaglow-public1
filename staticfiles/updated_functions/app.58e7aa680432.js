let currentJaasApi = null;
let connectionTimer = null;
const panel = document.getElementById('panel');
const joinDesktopBtn = document.querySelector('.join-desktop-btn');
const joinMobileBtn = document.querySelector('.join-mobile-btn');
let isCallActive = false;
const gapElement = document.getElementById('gap-element');


// Фиксированный контейнер для видео
const videoContainer = document.createElement('div');
videoContainer.id = 'fixed-video-container';
document.body.appendChild(videoContainer);

// Контейнер для панели управления (создаем сразу)
const controlsPanel = document.createElement('div');
controlsPanel.id = 'video-controls-panel';
document.body.appendChild(controlsPanel);

// Создаем iframe один раз
const videoElement = document.createElement('div');
videoElement.className = 'video w-100 h-100';
videoContainer.appendChild(videoElement);

// Обработчики для всех кнопок присоединения
joinDesktopBtn.addEventListener('click', async () => {
    startVideoCall();
});
joinMobileBtn.addEventListener('click', async () => {
    startVideoCall();
});

async function startVideoCall() {
    // Скрываем все кнопки присоединения
    joinDesktopBtn.classList.remove("d-none", "d-xl-block");
    joinDesktopBtn.classList.add("d-none");
    joinMobileBtn.classList.remove("d-block", "d-xl-none");
    joinMobileBtn.classList.add("d-none");

    // Показываем фиксированный контейнер
    videoContainer.style.display = 'block';

    panel.style.bottom = '180px';

    // Таймер для отслеживания подключения
    connectionTimer = setTimeout(() => {
        showNotification("Произошла ошибка. Используйте другой браузер - Яндекс или Google Chrome.", "danger");
        cleanup();
    }, 45000);

    try {
        const roomName = `LinguaGlow-${classroomId}`;

        // Запрос токена с сервера
        const response = await fetch('/api/jitsi/token/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            },
            body: JSON.stringify({
                room: roomName,
                role: mainContainer.dataset.userRole || 'student'
            })
        });

        if (!response.ok) {
            throw new Error(`Ошибка при получении токена: ${response.statusText}`);
            showNotification("Произошла ошибка при подключении.", "danger");
        }

        const data = await response.json();
        const jitsiToken = data.token;

        currentJaasApi = new JitsiMeetExternalAPI('jitsi-linguaglow.ru', {
            roomName,
            parentNode: videoElement,
            configOverwrite: {
                startWithAudioMuted: false,
                startWithVideoMuted: false,
                prejoinPageEnabled: false,
                disableSimulcast: true,
                enableNoisyMicDetection: false,
                enableClosePage: false,
                disableSettings: true,
                disableProfile: true,
                videoQuality: {
                    maxHeight: 480,
                    maxWidth: 640,
                },
                constraints: {
                    video: {
                        height: { ideal: 480, max: 480, min: 180 },
                        width: { ideal: 640, max: 640, min: 320 }
                    }
                },
                disableDeepLinking: true,
            },
            interfaceConfigOverwrite: {
                APP_NAME: 'LinguaGlow',
                SHOW_JITSI_WATERMARK: false,
                SHOW_WATERMARK_FOR_GUESTS: false,
                SHOW_POWERED_BY: false,
                TOOLBAR_BUTTONS: [],
                CONNECTION_INDICATOR_DISABLED: true,
                DEFAULT_BACKGROUND: '#fff',
                FILM_STRIP_MAX_HEIGHT: 0,
                VERTICAL_FILMSTRIP: false,
                mobileAppPromo: false,
            },
            userInfo: {
                displayName: mainContainer.dataset.username,
                email: ''
            },
            jwt: jitsiToken,
        });

        currentJaasApi.addListener('videoConferenceJoined', () => {
            clearTimeout(connectionTimer);
            connectionTimer = null;
            isCallActive = true;

            initControls();
        });

        currentJaasApi.addListener('readyToClose', () => {
            cleanup();
        });

    } catch (error) {
        console.error('Ошибка подключения:', error);
        cleanup();
    }
}

function initControls() {
    // Показываем панель управления
    if (controlsPanel) {
        controlsPanel.style.display = 'flex';
        controlsPanel.style.justifyContent = 'space-between';
        controlsPanel.style.alignItems = 'center';
        controlsPanel.innerHTML = '';
    }

    if (videoContainer) {
        videoContainer.style.bottom = '65px';
        videoContainer.style.borderRadius = '8px 8px 0 0';
    }
    if (panel) {
        panel.style.bottom = '230px';
    }
    if (gapElement) {
        gapElement.style.marginBottom = '310px';
    }

    // Кнопки управления
    const btnMic = createControlButton('Микрофон', 'bi-mic text-success');
    const btnCam = createControlButton('Камера', 'bi-camera-video text-success');
    const btnScreen = createControlButton('Экран', 'bi-display');
    const btnEnd = createControlButton('Выход', 'bi-telephone-x text-danger');

    controlsPanel.append(btnMic, btnCam, btnScreen, btnEnd);

    // Обработчики событий Jitsi
    currentJaasApi.on('audioMuteStatusChanged', ({ muted }) => {
        if (btnMic) {
            btnMic.innerHTML = `<i class="bi ${muted ? 'bi-mic-mute text-danger' : 'bi-mic text-success'}"></i>`;
        }
    });

    currentJaasApi.on('videoMuteStatusChanged', ({ muted }) => {
        if (btnCam) {
            btnCam.innerHTML = `<i class="bi ${muted ? 'bi-camera-video-off text-danger' : 'bi-camera-video text-success'}"></i>`;
        }
    });

    // Обработчики кликов
    if (btnMic) {
        btnMic.addEventListener('click', () => currentJaasApi.executeCommand('toggleAudio'));
    }
    if (btnCam) {
        btnCam.addEventListener('click', () => currentJaasApi.executeCommand('toggleVideo'));
    }
    if (btnScreen) {
        btnScreen.addEventListener('click', () => currentJaasApi.executeCommand('toggleShareScreen'));
    }
    if (btnEnd) {
        btnEnd.addEventListener('click', () => currentJaasApi.executeCommand('hangup'));
    }

    // Кнопка полноэкранного режима (переносим в videoContainer)
    const btnFullscreen = document.createElement('button');
    btnFullscreen.className = 'btn btn-sm bg-white text-dark d-flex align-items-center btn-fullscreen position-absolute rounded shadow-sm';
    btnFullscreen.title = 'На весь экран';
    btnFullscreen.innerHTML = '<i class="bi bi-arrows-fullscreen"></i>';
    btnFullscreen.style.cssText = `
        top: 10px;
        right: 10px;
        width: 32px;
        height: 32px;
        z-index: 5;
    `;
    videoContainer.appendChild(btnFullscreen);

    // Создаем overlay для затемнения фона
    const overlay = document.createElement('div');
    overlay.id = 'video-overlay';
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-color: rgba(0, 0, 0, 0.5);
        z-index: 1045;
        opacity: 0;
        pointer-events: none;
        transition: opacity 0.1s ease;
    `;
    document.body.appendChild(overlay);

    let isExpanded = false;
    let originalWidth = '300px';
    let originalHeight = '200px';
    let originalBottom = '15px';
    let originalRight = '15px';
    let originalBorderRadius = '8px';

    btnFullscreen.addEventListener('click', () => {
        const iframe = videoElement.querySelector('iframe');
        if (!iframe) return;

        isExpanded = !isExpanded;

        if (isExpanded) {
            // Сохраняем оригинальные параметры
            originalWidth = videoContainer.style.width;
            originalHeight = videoContainer.style.height;
            originalBottom = videoContainer.style.bottom;
            originalRight = videoContainer.style.right;
            originalBorderRadius = videoContainer.style.borderRadius;

            // Показываем overlay с плавным появлением
            overlay.style.pointerEvents = 'auto';
            overlay.style.opacity = '1';

            // Анимация расширения
            videoContainer.style.transition = 'all 0.1s cubic-bezier(0.25, 0.8, 0.25, 1)';
            setTimeout(() => {
                videoContainer.style.width = 'min(80vw, 1000px)';
                videoContainer.style.height = 'min(80vh, 700px)';
                videoContainer.style.bottom = '50%';
                videoContainer.style.right = '50%';
                videoContainer.style.borderRadius = '12px';
                videoContainer.style.transform = 'translate(50%, 50%)';

                // Обновляем иконку
                btnFullscreen.innerHTML = '<i class="bi bi-fullscreen-exit"></i>';
                btnFullscreen.title = 'Уменьшить экран';

                // Поднимаем z-index
                videoContainer.style.zIndex = '1050';

                panel.style.bottom = '0';
                controlsPanel.style.display = 'none';
            }, 10);
        } else {
            // Скрываем overlay
            overlay.style.opacity = '0';
            overlay.style.pointerEvents = 'none';

            // Анимация возврата
            videoContainer.style.transition = 'all 0.1s cubic-bezier(0.25, 0.8, 0.25, 1)';
            setTimeout(() => {
                videoContainer.style.width = originalWidth;
                videoContainer.style.height = originalHeight;
                videoContainer.style.bottom = originalBottom;
                videoContainer.style.right = originalRight;
                videoContainer.style.borderRadius = originalBorderRadius;
                videoContainer.style.transform = 'translate(0, 0)';

                // Обновляем иконку
                btnFullscreen.innerHTML = '<i class="bi bi-arrows-fullscreen"></i>';
                btnFullscreen.title = 'На весь экран';

                // Возвращаем z-index
                videoContainer.style.zIndex = '1040';

                panel.style.bottom = '230px';
                controlsPanel.style.display = 'flex';
            }, 100);
        }
    });

    // Закрытие по клику на overlay
    overlay.addEventListener('click', () => {
        if (isExpanded) {
            btnFullscreen.click();
        }
    });
}

function createControlButton(title, iconClass) {
    const btn = document.createElement('button');
    btn.className = 'call-btn';
    btn.title = title;
    btn.innerHTML = `<i class="bi ${iconClass}"></i>`;
    if (iconClass === "bi-display") {
        btn.classList.add("d-none", "d-md-block");
    }
    return btn;
}

function cleanup() {
    isCallActive = false;

    if (connectionTimer) {
        clearTimeout(connectionTimer);
        connectionTimer = null;
    }

    // Показываем все кнопки присоединения
    if (joinDesktopBtn) {
        joinDesktopBtn.classList.remove("d-none");
        joinDesktopBtn.classList.add("d-none", "d-xl-block");
    }
    if (joinMobileBtn) {
        joinMobileBtn.classList.remove("d-none");
        joinMobileBtn.classList.add("d-block", "d-xl-none");
    }

    panel.style.bottom = '0';
    gapElement.style.marginBottom = '0';

    // Очищаем контейнер (но сохраняем iframe)
    const controls = videoContainer.querySelector('.call-controls');
    if (controls) controls.remove();

    const btnFullscreen = videoContainer.querySelector('.btn-fullscreen');
    if (btnFullscreen) btnFullscreen.remove();

    let originalWidth = '260px';
    let originalHeight = '170px';
    let originalBottom = '15px';
    let originalRight = '15px';
    let originalBorderRadius = '8px';
    setTimeout(() => {
        if (videoContainer) {
            videoContainer.style.width = originalWidth;
            videoContainer.style.height = originalHeight;
            videoContainer.style.bottom = originalBottom;
            videoContainer.style.right = originalRight;
            videoContainer.style.borderRadius = originalBorderRadius;
            videoContainer.style.transform = 'translate(0, 0)';
            videoContainer.style.zIndex = '1040';
        }

        // Обновляем иконку
        btnFullscreen.innerHTML = '<i class="bi bi-arrows-fullscreen"></i>';
        btnFullscreen.title = 'На весь экран';
    }, 10);

    // Скрываем контейнер
    videoContainer.style.display = 'none';

    // Скрываем панель управления
    controlsPanel.style.display = 'none';
    controlsPanel.innerHTML = '';

    // Очищаем Jitsi API
    if (currentJaasApi) {
        try {
            currentJaasApi.dispose();
        } catch (e) {
            console.error('Ошибка при очистке Jitsi:', e);
        }
        currentJaasApi = null;
    }

    // Удаляем overlay при очистке
    const overlay = document.getElementById('video-overlay');
    if (overlay) overlay.remove();
}


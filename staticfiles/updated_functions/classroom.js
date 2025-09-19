        // Установка просматриваемого пользователя

document.addEventListener('DOMContentLoaded', () => {
    const studentOptions = document.querySelectorAll('.student-option');
    const dropdownButton = document.getElementById('studentDropdown');

    // Функция для активации элемента
    function activateOption(option) {
        // Удаляем класс 'active' у всех элементов
        studentOptions.forEach(opt => opt.classList.remove('active'));

        // Добавляем класс 'active' к выбранному элементу
        option.classList.add('active');

        // Обновляем текст кнопки на имя выбранного ученика
        dropdownButton.textContent = option.textContent;
    }

    // Добавляем обработчики кликов для каждого элемента
    studentOptions.forEach(option => {
        option.addEventListener('click', (event) => {
            event.preventDefault();
            activateOption(option);
            studentId = option.dataset.studentId;
        });
    });

    // По умолчанию активируем первый элемент
    if (studentOptions.length > 0) {
        activateOption(studentOptions[0]);
    }
});




        // Панель управления

function disableCopying() {
    // Запрещаем выделение текста
    document.addEventListener('selectstart', preventSelection);
    document.addEventListener('contextmenu', preventContextMenu);
    document.addEventListener('copy', preventCopy);
}

function enableCopying() {
    // Возвращаем стандартное поведение
    document.removeEventListener('selectstart', preventSelection);
    document.removeEventListener('contextmenu', preventContextMenu);
    document.removeEventListener('copy', preventCopy);
}

function preventSelection(event) {
    event.preventDefault();
}

function preventContextMenu(event) {
    event.preventDefault();
}

function preventCopy(event) {
    event.preventDefault();
}

document.addEventListener('DOMContentLoaded', function () {
    const disableCopyingButton = document.getElementById('disableCopyingButton');
    const refreshPageButton = document.getElementById('refreshPageButton');
    const studentDropdown = document.getElementById('studentDropdown');
    const controlPanelDropdown = document.getElementById('controlPanelDropdown');
    const studentOptions = document.querySelectorAll('.student-option');
    const studentDropdownContainer = studentDropdown?.closest('.dropdown');
    const controlPanelContainer = controlPanelDropdown?.closest('.dropdown');
    const bottomPanel = document.querySelector('.position-fixed.bottom-0.start-0');

    // Функция для показа кнопки "Пригласить ученика"
    function showInviteButtonOnly() {
        if (!bottomPanel) return;
        bottomPanel.innerHTML = `
            <button
                class="btn btn-primary d-flex align-items-center rounded shadow"
                id="inviteStudentButton"
                data-bs-toggle="modal"
                data-bs-target="#invitationModal"
            >
                <i class="bi bi-person-plus me-2"></i> Пригласить ученика
            </button>
        `;
    }

    // Проверка количества учеников
    if (!studentOptions.length) {
        showInviteButtonOnly();
    }

    // Инициализация состояния копирования
    const isCopyingAllowed = mainContainer.dataset.copyingMode; // Начальное состояние
    if (isCopyingAllowed === "false" && userRole !== "teacher") {
        disableCopying();
    }

    if (disableCopyingButton) {
        disableCopyingButton.addEventListener('click', function () {
            const currentAction = disableCopyingButton.querySelector('.text').textContent.trim();
            const isCopyingAllowed = currentAction === 'Запретить копирование';

            fetch(`/classroom/${classroomId}/toggle-copying/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({ allow_copying: !isCopyingAllowed })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    if (data.new_state) {
                        sendMessage("copying-enable", "", "", "all");
                        showNotification("Копирование разрешено", "success");

                        disableCopyingButton.querySelector('.text').textContent = 'Запретить копирование';
                        disableCopyingButton.classList.remove('text-success');
                        disableCopyingButton.classList.add('text-danger');

                        const icon = disableCopyingButton.querySelector('i');
                        if (icon) {
                            icon.classList.add('bi-ban');
                            icon.classList.remove('bi-check-circle');
                        }
                    } else {
                        sendMessage("copying-disable", "", "", "all");
                        showNotification("Копирование запрещено", "success");

                        disableCopyingButton.querySelector('.text').textContent = 'Разрешить копирование';
                        disableCopyingButton.classList.remove('text-danger');
                        disableCopyingButton.classList.add('text-success');

                        const icon = disableCopyingButton.querySelector('i');
                        if (icon) {
                            icon.classList.add('bi-check-circle');
                            icon.classList.remove('bi-ban');
                        }
                    }
                } else {
                    alert('Ошибка при обновлении настроек.');
                }
            })
            .catch(error => console.error('Ошибка:', error));
        });
    }

    if (refreshPageButton) {
        refreshPageButton.addEventListener('click', function () {
            sendMessage("page-reload", "", "", "all");
            showNotification("Обновляем страницы учеников", "success");
            refreshPageButton.disabled = true;
            refreshPageButton.title = 'Обновление страницы учеников...';
            setTimeout(() => {
                refreshPageButton.disabled = false;
                refreshPageButton.title = '';
            }, 10000);
        });
    }
});





        //ВебСокет


    //Получаем токен из сессионных данных или хранилища (например, из cookies или localStorage)
const token = localStorage.getItem('auth_token') || document.cookie.replace(/(?:(?:^|.*;\s*)auth_token\s*\=\s*([^;]*).*$)|^.*$/, "$1");

        // Стабильность Websocket

// Константы для переподключения
const MAX_RECONNECT_ATTEMPTS = 10;
const INITIAL_RECONNECT_DELAY = 1000; // 1 секунда
const MAX_RECONNECT_DELAY = 30000; // 30 секунд

let reconnectAttempts = 0;
let reconnectDelay = INITIAL_RECONNECT_DELAY;
let reconnectTimeout = null;
let socket = null;

/**
 * Создает и возвращает новое соединение WebSocket с обработчиками
 * @param {string} classroomId
 * @param {string} token
 * @returns {WebSocket}
 */
function createWebSocket(classroomId, token) {
    const ws = new WebSocket(`wss://${window.location.host}/ws/classroom/${classroomId}/?token=${token}`);

    ws.onopen = () => {
        console.log("✅ WebSocket подключен");
        showNotification("Соединение восстановлено.", "success");
        reconnectAttempts = 0;
        reconnectDelay = INITIAL_RECONNECT_DELAY;
        socketOpened = true;
    };

    ws.onclose = (event) => {
        socketOpened = false;
        if (!event.wasClean) {
            console.log('🔌 Соединение закрыто, пробуем переподключиться...');
            scheduleReconnect(classroomId, token);
        }
    };

    ws.onerror = (err) => {
        console.error("WebSocket ошибка:", err);
        // При ошибке сразу закрываем сокет, чтобы сработал onclose и переподключение
        if (ws.readyState !== WebSocket.CLOSED && ws.readyState !== WebSocket.CLOSING) {
            ws.close();
        }
    };

    return ws;
}

/**
 * Планирует переподключение с экспоненциальной задержкой
 * @param {string} classroomId
 * @param {string} token
 */
function scheduleReconnect(classroomId, token) {
    if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
    }

    if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        showNotification("Вы оффлайн. Используйте другой браузер — Яндекс или Google Chrome.", "danger");
        return;
    }

    reconnectDelay = Math.min(INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectAttempts), MAX_RECONNECT_DELAY);
    reconnectAttempts++;

    console.log(`⌛ Попытка переподключения ${reconnectAttempts} через ${reconnectDelay}мс...`);

    reconnectTimeout = setTimeout(() => {
        socket = createWebSocket(classroomId, token);
    }, reconnectDelay);
}

/**
 * Запускает WebSocket с логикой переподключения
 * @param {string} classroomId
 * @param {string} token
 */
function startWebSocket(classroomId, token) {
    if (socket) {
        socket.close();
        socket = null;
    }
    reconnectAttempts = 0;
    reconnectDelay = INITIAL_RECONNECT_DELAY;
    socket = createWebSocket(classroomId, token);

    // Дополнительно отслеживаем восстановление сети браузера
    window.addEventListener('online', () => {
        if (!socket || socket.readyState === WebSocket.CLOSED) {
            console.log('🌐 Сеть восстановлена, переподключаемся...');
            reconnectAttempts = 0;
            reconnectDelay = INITIAL_RECONNECT_DELAY;
            if (reconnectTimeout) {
                clearTimeout(reconnectTimeout);
            }
            socket = createWebSocket(classroomId, token);
        }
    });
}

startWebSocket(classroomId, token);

socket.onopen = function () {
    socketOpened = true;

    if (mode === 'classroom') {
        sendMessage("user-enter", "", {"username": document.getElementById('main-container').dataset.username}, "teacher");
    }
};

socket.onmessage = function (event) {
    const { request_type, task_id, data, sender_id } = JSON.parse(event.data);

    // Показываем только ответы от выбранного ученика
    if (
        userRole === 'teacher' &&
        request_type === 'task-answer'
    ) {
        const selectedIds = Array.isArray(studentId) ? studentId : [parseInt(studentId)];
        if (!selectedIds.includes(sender_id)) return;
    }

    const handlers = {
        "task-attention": () => moveToPointedTask(task_id),
        "task-answer": () => {
            handleTaskAnswer(task_id, data);
            updateProgressBar(task_id, data.correct_count, data.incorrect_count, data.max_score);
        },
        "test-check": () => {
            checkTestAnswers(task_id);
            updateProgressBar(task_id, data.correct_count, data.incorrect_count, data.max_score);
        },
        "truefalse-check": () => {
            checkTrueFalseAnswers(task_id);
            updateProgressBar(task_id, data.correct_count, data.incorrect_count, data.data.max_score);
        },
        "task-reset": () => {
            const taskContainer = document.getElementById(task_id);
            const taskType = taskContainer.getAttribute('data-task-type');
            const functionName = `clear${taskType.charAt(0).toUpperCase() + taskType.slice(1)}Answer`;
            if (typeof window[functionName] === 'function') {
                window[functionName](task_id);
            }
            updateProgressBar(task_id, 0, 0, 100, false);
        },
        "user-enter": () => {
            showNotification(`${data.username} присоединился к классу.`, "success");
            if (userRole === 'teacher') {
                const studentExists = Array.from(document.querySelectorAll('.student-option')).some(
                    el => el.textContent.trim() === data.username
                );
                if (!studentExists) window.location.reload();
            }
        },
        "user-leave": () => showNotification(`${data.username} покинул класс.`, "warning"),
        "copying-enable": () => enableCopying(),
        "copying-disable": () => disableCopying(),
        "page-reload": () => location.reload(),
        "pdf-page": () => moveToSelectedPdfPage(task_id, data.page)
    };

    if (handlers[request_type]) handlers[request_type]();
};



// Дополнительная проверка, если ни onopen, ни onerror не сработали быстро
setTimeout(() => {
    if (socket.readyState !== WebSocket.OPEN && !socketOpened) {
        reconnectWebSocket(classroomId, token);
    }
}, 30000);

function sendMessage(request_type, task_id, data, receivers = 'all') {
    const message_id = "";
    const message = {
        request_type,
        task_id,
        data,
        receivers,
        message_id
    };

    // Если студент — всегда отправляем только учителю
    if (userRole === 'student') {
        message.receivers = 'teacher';
    }

    // Если учитель и receivers == 'student', то добавляем конкретного ученика
    if (userRole === 'teacher' && receivers === 'student') {
        if (Array.isArray(studentId)) {
            message.receivers = studentId;  // [id1, id2, ...]
        } else if (studentId) {
            message.receivers = [parseInt(studentId)];
        }
    }

    socket.send(JSON.stringify(message));
}





        // Общие функции


async function fetchUserAnswers(userId, taskId, classroomId) {
    try {
        const params = new URLSearchParams({
            user_id: userId,
            task_id: taskId,
            classroom_id: classroomId
        });

        const response = await fetch(`/api/get_answers/?${params}`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken') // Функция для получения CSRF токена
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (data.status === 'error') {
            console.error('Error fetching answers:', data.message);
            return null;
        }

        return data;

    } catch (error) {
        console.error('Error fetching user answers:', error);
        return null;
    }
}








    // Функции для обработки действий

function taskAttention(taskId) {
    sendMessage('task-attention', taskId, {}, 'all');
    moveToPointedTask(taskId, false);
    return;
}

function handleTaskAnswer(taskId, data) {
    const answer = data.answer;
    const isCorrect = data.isCorrect;
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer) {
        return;
    }

    const task_type = taskContainer.dataset.taskType;
    const functionName = `fill${task_type.charAt(0).toUpperCase()}${task_type.slice(1)}Answer`;
    if (typeof window[functionName] === 'function') {
        window[functionName](taskId, answer, isCorrect);
    } else {
        console.warn(`Функция ${functionName} не найдена`);
    }
}

async function moveToPointedTask(taskId, scroll = true) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer) {
        return;
    }

    // Прокручиваем к заданию
    if (scroll) {
        const sectionId = taskContainer.dataset.sectionId;
        // Загружаем раздел перед прокруткой
        await loadSection(sectionId);
        taskContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    // Подсветка с анимацией
    setTimeout(() => {
        taskContainer.classList.add('card-glowing');
        // Удаляем класс после окончания анимации
        setTimeout(() => {
            taskContainer.classList.remove('card-glowing');
        }, 1000); // должна совпадать с длительностью анимации
    }, 600);
}

async function moveToSelectedPdfPage(taskId, page) {
    await moveToPointedTask(taskId, true);

    const taskEl = document.getElementById(taskId);
    if (!taskEl) return;

    const pageInput = taskEl.querySelector('#page-input');
    const nextBtn = taskEl.querySelector('#next-page');
    const prevBtn = taskEl.querySelector('#prev-page');
    const pageCountEl = taskEl.querySelector('#page-count');

    if (!pageInput || !nextBtn || !prevBtn || !pageCountEl) return;

    const max = parseInt(pageInput.getAttribute('max')) || 1;
    const targetPage = Math.min(Math.max(page, 1), max);

    // Устанавливаем нужную страницу
    pageInput.value = targetPage;

    // Вызываем событие изменения (если от него зависит рендер)
    pageInput.dispatchEvent(new Event('change', { bubbles: true }));

    // Также можно вызвать обработчик вручную, если он не слушает change
    if (typeof renderPage === 'function') {
        renderPage(targetPage, taskId);  // зависит от вашей реализации
    }
}

async function deleteAnswers(task_id, classroom_id, user_id) {
    try {
        // Отправляем POST-запрос
        const response = await fetch('/api/delete_answers/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                task_id: task_id,
                classroom_id: classroomId,
                user_id: user_id
            })
        });

        // Обрабатываем ответ
        const data = await response.json();
        const messageDiv = document.getElementById('response-message');
        if (response.ok) {
            const taskContainer = document.getElementById(task_id);
            const taskType = taskContainer.getAttribute('data-task-type');
            const capitalizedTaskType = taskType.charAt(0).toUpperCase() + taskType.slice(1);
            const functionName = `clear${capitalizedTaskType}Answer`;
            if (typeof window[functionName] === 'function') {
                window[functionName](task_id);
            }
            updateProgressBar(task_id, 0, 0, 100, false);
        } else {
            showNotification(data.message, 'danger');
        }
    } catch (error) {
        console.error('Error:', error);
    }
}






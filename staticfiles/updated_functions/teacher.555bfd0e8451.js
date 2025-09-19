const addTextContextButtons = document.querySelectorAll(".addTextContentButton");

const elementRussianNames = {
    "wordlist": "Список слов",
    "matchupthewords": "Соотнесите слова",
    "essay": "Эссе",
    "note": "Заметка",
    "image": "Изображение",
    "sortintocolumns": "Распределить по колонкам",
    "makeasentence": "Составить предложение",
    "unscramble": "Составить слово из букв",
    "fillintheblanks": "Заполнить пропуски",
    "dialogue": "Диалог",
    "article": "Статья",
    "audio": "Аудио",
    "test": "Тест",
    "trueorfalse": "Правда или ложь",
    "labelimages": "Подпишите изображения",
    "embeddedtask": "Интерактивное задание"
};





        // Разделы урока

function addSectionButtonInitialization() {
    const button = document.querySelector('.add-section-link');
    if (!button || userRole !== "teacher") return;

    const lessonId = button.dataset.lessonId;
    const isNew = button.dataset.isNew === "True";

    button.addEventListener('click', function(e) {
        e.preventDefault();

        // Если это первый клик и isNew=true
        if (isNew && !this.dataset.initialClickHandled) {
            new bootstrap.Modal(document.getElementById('generationModal')).show();
            this.dataset.initialClickHandled = 'true'; // Помечаем как обработанный
            return;
        }

        // Стандартное поведение для последующих кликов
        new bootstrap.Modal(document.getElementById('sectionChoiceModal')).show();
    });

    // Остальная логика обработчиков остается без изменений
    document.getElementById('createEmptySectionBtn').addEventListener('click', () => {
        const modal = bootstrap.Modal.getInstance(document.getElementById('sectionChoiceModal'));
        modal.hide();
        setTimeout(() => openCreateSectionModal(), 300);
    });

    document.getElementById('generateSectionBtn').addEventListener('click', () => {
        const modal = bootstrap.Modal.getInstance(document.getElementById('sectionChoiceModal'));
        modal.hide();
        setTimeout(() => {
            new bootstrap.Modal(document.getElementById('generationModal')).show();
        }, 300);
    });
}

// --- Drag & Drop core ---
function initDragAndDrop() {
    const list = document.getElementById('section-list');
    if (!list) return;

    // все li делаем перетаскиваемыми
    list.querySelectorAll('li').forEach(li => li.setAttribute('draggable', 'true'));

    let draggingEl = null;

    list.addEventListener('dragstart', function(e) {
        const li = e.target.closest('li');
        if (!li) return;

        // если начали тянуть с кнопки — отменяем
        if (e.target.closest('button')) {
            e.preventDefault();
            return;
        }

        draggingEl = li;
        li.classList.add('dragging');
        try {
            e.dataTransfer.setData('text/plain', li.dataset.sectionId || '');
        } catch (err) {}
        e.dataTransfer.effectAllowed = 'move';
    });

    list.addEventListener('dragover', function(e) {
        e.preventDefault();
        if (!draggingEl) return;

        const target = e.target.closest('li');
        if (!target || target === draggingEl) return;

        const rect = target.getBoundingClientRect();
        const after = (e.clientY - rect.top) > (rect.height / 2);
        const reference = after ? target.nextSibling : target;
        list.insertBefore(draggingEl, reference);
    });

    list.addEventListener('drop', function(e) {
        e.preventDefault();
        if (!draggingEl) return;
        draggingEl.classList.remove('dragging');
        draggingEl = null;
        sendOrderToServer();
    });

    list.addEventListener('dragend', function(e) {
        const li = e.target.closest('li');
        if (li) li.classList.remove('dragging');
        draggingEl = null;
    });
}

// --- Отправка порядка на сервер ---
function sendOrderToServer() {
    const list = document.getElementById('section-list');
    if (!list) return;

    const order = Array.from(list.querySelectorAll('li')).map(li => li.dataset.sectionId);

    const lessonId = "{{ lesson.id }}"; // Django template var
    fetch(`/lessons/${lessonId}/reorder_sections/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify({ order: order })
    })
    .then(res => {
        if (!res.ok) return res.json().then(j => Promise.reject(j));
        return res.json();
    })
    .then(data => {
        if (data.status && data.status === 'ok') {
            // optionally show success
        } else {
            console.error('Ошибка сохранения порядка:', data);
        }
    })
    .catch(err => {
        console.error('Ошибка при сохранении порядка:', err);
    });
}

// Вспомогательные функции
function scrollToBottom(container) {
    const overflowContainer = container.closest('.overflow-y-auto');
    if (overflowContainer) {
        overflowContainer.scrollTo({
            top: overflowContainer.scrollHeight,
            behavior: 'smooth'
        });
    }
}

function getSelectedSectionType() {
    const radio = document.querySelector('input[name="sectionType"]:checked');
    return radio.value;
}

function resetModalFields() {
    document.getElementById('manualSectionName').value = '';
    document.getElementById('typeLearning').checked = true;
}

// Открыть модалки
function openCreateSectionModal() {
    resetModalFields();

    document.getElementById('manualSectionModalLabel').textContent = 'Новый раздел';
    document.getElementById('saveManualSectionIcon').className = 'bi bi-plus-circle';
    document.getElementById('saveManualSectionText').textContent = 'Создать';
    const btn = document.getElementById('saveManualSection');
    btn.dataset.action = 'create';
    btn.dataset.sectionId = '';

    new bootstrap.Modal(document.getElementById('manualSectionModal')).show();
}

function openEditSectionModal(sectionId, currentName, currentType) {
    document.getElementById('manualSectionName').value = currentName;

    const radio = document.querySelector(`input[name="sectionType"][value="${currentType}"]`);
    if (radio) radio.checked = true;

    document.getElementById('manualSectionModalLabel').textContent = 'Редактировать раздел';
    document.getElementById('saveManualSectionIcon').className = 'bi bi-check-circle';
    document.getElementById('saveManualSectionText').textContent = 'Сохранить';
    const btn = document.getElementById('saveManualSection');
    btn.dataset.action = 'edit';
    btn.dataset.sectionId = sectionId;

    new bootstrap.Modal(document.getElementById('manualSectionModal')).show();
}

document.getElementById('saveManualSection').addEventListener('click', () => {
    const btn = document.getElementById('saveManualSection');
    const name = document.getElementById('manualSectionName').value.trim();
    const type = getSelectedSectionType();
    const action = btn.dataset.action;
    const sectionId = btn.dataset.sectionId;

    // Получаем инстанс модалки и скроем её после операции
    const modalEl = document.getElementById('manualSectionModal');
    const modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);

    if (action === 'create') {
        handleAddSection(lessonId, name, type);
    } else if (action === 'edit') {
        handleSectionEdit(sectionId, name, type);
    }
});

// Работа с API
async function handleAddSection(lessonId, sectionName, sectionType) {
    try {
        const resp = await fetch(`/hub/lesson/${lessonId}/add_section/`, {
            method: 'POST',
            headers: {'Content-Type':'application/json','X-CSRFToken':getCookie('csrftoken')},
            body: JSON.stringify({name: sectionName, type: sectionType})
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error||'Ошибка');
        sections.push({id: data.section_id, name: data.name, type: sectionType});
        renderSectionList();
        loadSection(data.section_id);
        bootstrap.Modal.getInstance(document.getElementById('manualSectionModal')).hide();
        return data;
    } catch (err) {
        showNotification(err.message,'danger');
        throw err;
    }
}

function handleSectionEdit(sectionId, name, type) {
    fetch(`/hub/section/${sectionId}/update`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({ name, type })
    })
    .then(res => res.ok ? res.json() : Promise.reject())
    .then(data => {
        showNotification('Раздел обновлён.', 'success');
        sections = sections.map(s =>
            s.id === sectionId ? { ...s, name, type } : s
        );
        renderSectionList();
        loadSection(sectionId);
        bootstrap.Modal.getInstance(document.getElementById('manualSectionModal')).hide();
    })
    .catch(() => showNotification('Ошибка при обновлении.', 'danger'));
}

async function handleDeleteSection(sectionId) {
    const confirmDelete = await bootstrapConfirm("Вы уверены, что хотите удалить этот раздел?");
    if (!confirmDelete) return;

    fetch(`/section/${sectionId}/delete/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const sectionItem = document.querySelector(`li[data-section-id="${sectionId}"]`);
            if (sectionItem) {
                sectionItem.remove();
                showNotification("Раздел успешно удалён", "success");
                initSectionsFromDOM();
                renderSectionList();
                initializeFirstSection();
            }

            const sectionList = document.querySelector('#section-list');
            initializeFirstSection();

            getContext(lessonId);
        } else {
            showNotification(data.error || "Не удалось удалить раздел", "danger");
        }
    })
    .catch(error => {
        console.error("Ошибка при удалении раздела:", error);
        showNotification("Произошла ошибка при удалении", "danger");
    });
}


window.reinitSectionList = initDragAndDrop;

document.addEventListener('DOMContentLoaded', function () {
    const description = document.getElementById('sectionTypeDescription');
    const radios = document.querySelectorAll('input[name="sectionType"]');
    const select = document.getElementById('sectionTypeSelect');
    const saveBtn = document.getElementById('saveManualSection');
    const sectionNameInput = document.getElementById('manualSectionName');

    let selectedType = 'learning';

    initDragAndDrop();

    function updateDescription(type) {
        switch (type) {
            case 'revision':
                description.textContent = 'Будет автоматически добавлен в будущие уроки';
                break;
            case 'hometask':
                description.textContent = '';
                break;
            default:
                description.textContent = 'Является частью текущего урока';
        }
    }

    // Слушатели radio-кнопок (>= md)
    radios.forEach(radio => {
        radio.addEventListener('change', () => {
            if (!radio.checked) return;
            selectedType = radio.value;
            if (select) select.value = selectedType;
            updateDescription(selectedType);
        });
    });

    // Слушатель select (< md)
    if (select) {
        select.addEventListener('change', () => {
            selectedType = select.value;
            const matching = document.querySelector(`input[name="sectionType"][value="${selectedType}"]`);
            if (matching) matching.checked = true;
            updateDescription(selectedType);
        });
    }

    sectionNameInput.addEventListener('input', () => {
        if (sectionNameInput.classList.contains('is-invalid') && sectionNameInput.value.trim() !== '') {
            sectionNameInput.classList.remove('is-invalid');
        }
    });

    sectionNameInput.addEventListener('keydown', event => {
        if (event.key === 'Enter') {
            event.preventDefault();
            saveBtn.click();
        }
    });
});






        // Обработчики заданий

function organizeActionButtons(taskhtml, elems, color = 'dark') {
    const wrapper = document.createElement('div');
    wrapper.className = "d-flex justify-content-end align-items-center";

    const actionsContainer = document.createElement('div');
    actionsContainer.className = "actions-container ms-2 d-flex align-items-center rounded-3 border border-white bg-opacity-25 bg-white";

    // Кнопка "Призвать учеников" — на мобильных слева от дропдауна
    if (elems.summon && mode === "classroom") {
        const summonBtn = createIconButton("Призвать учеников", "bi-broadcast", `text-${color}`, "ms-2 d-md-none");
        actionsContainer.appendChild(summonBtn);
    }

    // Dropdown (на мобилках)
    const dropdown = document.createElement('div');
    dropdown.className = "dropdown d-md-none d-inline z-5";

    const dropdownToggle = document.createElement('button');
    dropdownToggle.className = `btn btn-sm text-${color} border-0`;
    dropdownToggle.setAttribute('type', 'button');
    dropdownToggle.setAttribute('data-bs-toggle', 'dropdown');
    dropdownToggle.setAttribute('aria-expanded', 'false');
    dropdownToggle.innerHTML = `<i class="bi bi-three-dots-vertical"></i>`;

    const dropdownMenu = document.createElement('div');
    dropdownMenu.className = 'dropdown-menu dropdown-menu-end';

    if (elems.edit) dropdownMenu.appendChild(createDropdownItem("Редактировать", "bi-pencil"));
    if (elems.mark) dropdownMenu.appendChild(createDropdownItem("Добавить в контекст", "bi-bookmark"));
    if (elems.mark) dropdownMenu.appendChild(createDropdownItem("Скрыть из контекста", "bi-bookmark-check"));
    if (elems.restart) dropdownMenu.appendChild(createDropdownItem("Сбросить", "bi-arrow-clockwise"));
    if (elems.deleteListener) dropdownMenu.appendChild(createDropdownItem("Удалить", "bi-trash"));

    dropdown.appendChild(dropdownToggle);
    dropdown.appendChild(dropdownMenu);
    actionsContainer.appendChild(dropdown);

    // Кнопки для desktop
    const desktopButtons = document.createElement('div');
    desktopButtons.className = "d-none d-md-flex";

    if (elems.edit) desktopButtons.appendChild(createIconButton("Редактировать", "bi-pencil", `text-${color}`, "ms-2"));
    if (elems.mark) desktopButtons.appendChild(createIconButton("Добавить в контекст", "bi-bookmark", `text-${color}`, "ms-2"));
    if (elems.mark) desktopButtons.appendChild(createIconButton("Скрыть из контекста", "bi-bookmark-check", `text-${color}`, "ms-2"));

    // summon — после edit, только на десктопе
    if (elems.summon && mode === "classroom") {
        const summonBtnDesktop = createIconButton("Призвать учеников", "bi-broadcast", `text-${color}`, "ms-2");
        desktopButtons.appendChild(summonBtnDesktop);
    }

    if (elems.restart) desktopButtons.appendChild(createIconButton("Сбросить", "bi-arrow-clockwise", `text-${color}`, "ms-2"));
    if (elems.deleteListener) desktopButtons.appendChild(createIconButton("Удалить", "bi-trash", `text-${color}`, "ms-2 me-2"));

    actionsContainer.appendChild(desktopButtons);
    wrapper.appendChild(actionsContainer);

    const taskHeader = taskhtml.querySelector('.card-header');
    if (taskHeader) {
        taskHeader.appendChild(wrapper);
    }

    // Инициализация событий
    if (elems.mark) initAttachTaskListeners(taskhtml);
    if (elems.edit) initEditTaskListeners(taskhtml);
    if (elems.summon) initSummonTaskListeners(taskhtml);
    if (elems.restart) initResetTaskListeners(taskhtml);
    if (elems.deleteListener) initDeleteTaskListener(taskhtml);
}

// Вспомогательная функция для создания пунктов меню
function createDropdownItem(title, icon) {
    const item = document.createElement('button');
    item.className = 'dropdown-item align-items-center gap-2';
    item.style.display = 'flex';
    if (title === "Удалить") {
        item.className += " text-danger";
    }
    item.type = 'button';
    item.innerHTML = `<i class="bi ${icon}"></i> <span class="action-text">${title}</span>`;
    return item;
}



// Добавление обработчиков
function initAttachTaskListeners(taskContainer) {
    const bookmarks = taskContainer.querySelectorAll(".bi-bookmark");
    const taskId = taskContainer.id;
    if (!bookmarks || !taskId) return;

    bookmarks.forEach(icon => {
        const button = icon.parentElement;
        button.addEventListener("click", function () {
            formatAndAddTaskToContext(taskId);
        });
        button.style.display = "flex";
    });

    const checkedBookmarks = taskContainer.querySelectorAll(".bi-bookmark-check");
    checkedBookmarks.forEach(icon => {
        const button = icon.parentElement;
        button.addEventListener("click", function () {
            removeTaskFromContext(taskId);
        });
        button.style.display = "none";
    });
}

function initSummonTaskListeners(taskContainer) {
    const icons = taskContainer.querySelectorAll(".bi-broadcast");

    if (!icons.length) return;

    icons.forEach(icon => {
        const button = icon.closest("button");
        if (!button) return;

        button.addEventListener("click", async function () {
            const taskContainer = this.closest(".task-item");
            if (!taskContainer) return;

            const taskId = taskContainer.id;
            if (!taskId) {
                showNotification("Ошибка: отсутствуют данные задания.", "danger");
                return;
            }

            taskAttention(taskId);
        });
    });
}

function initEditTaskListeners(taskContainer) {
    const icons = taskContainer.querySelectorAll(".bi-pencil");

    if (!icons.length) return;

    icons.forEach(icon => {
        const button = icon.closest("button");
        if (!button) return;

        button.addEventListener("click", async function () {
            const header = this.closest(".card-header");
            if (!header) return;

            const taskContainer = header.parentElement;
            if (!taskContainer) return;

            const taskId = taskContainer.id;
            if (!taskId) {
                showNotification("Ошибка: отсутствует ID задания.", "danger");
                return;
            }

            editTask(taskId);
        });
    });
}

function initResetTaskListeners(taskContainer) {
    const icons = taskContainer.querySelectorAll(".bi-arrow-clockwise");

    icons.forEach(icon => {
        const button = icon.closest("button");
        if (!button) return;

        if (mode === "classroom") {
            button.addEventListener("click", async function () {
                try {
                    const taskContainer = this.closest(".task-item");
                    if (!taskContainer) {
                        showNotification("Ошибка: отсутствует контейнер задачи.", "danger");
                        return;
                    }

                    const taskId = taskContainer.id;
                    if (!taskId) {
                        showNotification("Ошибка: отсутствуют данные задания.", "danger");
                        return;
                    }

                    await deleteAnswers(taskId, classroomId, studentId || userId);
                    sendMessage('task-reset', taskId, {}, 'student');
                    showNotification("Ответы успешно удалены.", "success");
                } catch (error) {
                    console.error("Ошибка при удалении ответов:", error);
                    showNotification("Произошла ошибка при удалении ответов.", "danger");
                }
            });
        } else {
            button.remove();
        }
    });
}

function initDeleteTaskListener(taskContainer) {
    const taskId = taskContainer.id;
    const icons = taskContainer.querySelectorAll(".bi-trash");

    icons.forEach(icon => {
        const button = icon.closest("button");
        if (!button || !taskId) return;

        button.addEventListener("click", async function () {
            const confirmDelete = await bootstrapConfirm("Вы уверены, что хотите удалить это задание?");
            if (!confirmDelete) return;

            try {
                const response = await fetch(`/hub/tasks/${taskId}/delete/`, {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken'),
                    },
                });

                if (response.ok) {
                    checkAndRemoveTaskFromContext(taskId);
                    taskContainer.parentElement.remove();

                    const addTaskButton = document.querySelector('#add-task-button-wrapper');
                    const tasksLeftInSection = document.querySelectorAll(`[data-section-id='${mainContainer.dataset.sectionId}']`).length;

                    if (addTaskButton && tasksLeftInSection === 0) {
                        addTaskButton.classList.remove('mt-3', 'mt-lg-4');
                    }

                    removeAccordionElementFromContextWindow(taskId);
                } else {
                    showNotification("Ошибка при удалении задания", "danger");
                }
            } catch (error) {
                console.log(error);
                showNotification("Произошла ошибка. Обновите страницу.", "danger");
            }
        });
    });
}






        // Контекст

function addTaskToContext(lesson_id, task_id, header, content) {
    fetch(`/hub/add-context-element/${lesson_id}/`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCookie("csrftoken")
        },
        body: JSON.stringify({
            task_id: task_id,
            header: header,
            content: content
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showNotification(data.error, "danger");
        } else {
            showTaskInContextWindow(data.task_id, data.header, data.content);
            const context_window = document.querySelector(".context-window");
            if (context_window.querySelectorAll(".accordion").length === 1) {
                const generation_container = document.getElementById("generation-container");
                if (generation_container) {
                    generation_container.innerHTML = "";
                    const generate_btn = document.getElementById("task-generate");
                    if (generate_btn) {
                        generate_btn.style.display = "flex";
                    }
                }
            }
        }
    })
    .catch(error => {
        showNotification("Произошла ошибка. Попробуйте выбрать другое задание или обратитесь в поддержку.", "danger");
    });
}

function removeTaskFromContext(taskId) {
    const lessonId = document.getElementById("main-container").dataset.lessonId;

    fetch(`/hub/remove-context-element/${lessonId}/${taskId}/`, {
        method: "DELETE",
        headers: {
            "X-CSRFToken": getCookie("csrftoken"),
            "Content-Type": "application/json"
        }
    }).then(response => response.json())
        .then(data => {
            if (data.error && data.error !== "Такого задания в контексте нет.") {
                showNotification(data.error, "danger");
            } else {
                removeAccordionElementFromContextWindow(data.task_id)
            }
        }).catch(error => showNotification("Произошла ошибка. Измените параметры или обратитесь в поддержку.", "danger"));
}

function addTextContext() {
    const containers = document.querySelectorAll(".noteContainer");

    addTextContextButtons.forEach(el => el.style.display = "none");

    containers.forEach(container => {
        // Очищаем контейнер от старых input и кнопок, если есть
        container.innerHTML = "";

        // Создаём input
        const input = document.createElement("input");
        input.type = "text";
        input.classList.add("form-control");
        input.placeholder = "Введите текст...";
        input.style.flexGrow = "1";

        // Кнопка сохранить — зелёная галочка
        const saveButton = document.createElement("button");
        saveButton.type = "button";
        saveButton.classList.add("btn", "btn-success");
        saveButton.title = "Сохранить";
        saveButton.style.padding = "0.25rem 0.5rem"; // чтобы кнопка была компактной
        saveButton.innerHTML = "<i class='bi bi-check-lg'></i>";

        // Кнопка отмены — крестик
        const cancelButton = document.createElement("button");
        cancelButton.type = "button";
        cancelButton.classList.add("btn-close");
        cancelButton.setAttribute("aria-label", "Отмена");
        cancelButton.style.width = "1rem";
        cancelButton.style.height = "1rem";

        // Добавляем элементы в контейнер (input + кнопки в одну строку)
        container.appendChild(input);
        container.appendChild(saveButton);
        container.appendChild(cancelButton);

        input.focus();

        cancelButton.addEventListener("click", () => {
            container.innerHTML = "";
            addTextContextButtons.forEach(el => el.style.display = "block");
        });

        saveButton.addEventListener("click", () => {
            const content = input.value.trim();
            if (content) {
                addTaskToContext(lessonId, null, null, content);
                container.innerHTML = "";
                addTextContextButtons.forEach(el => el.style.display = "block");
            } else {
                showNotification("Заметка не может быть пустой", "warning");
                input.focus();
            }
        });
    });
}

async function checkAndRemoveTaskFromContext(taskId) {
    const context = await getContext(lessonId, "view");

    const taskExists = Object.entries(context).some(
        ([existingTaskId]) => existingTaskId === taskId
    );

    if (taskExists) {
        removeTaskFromContext(taskId);
    }
}

function formatTaskContent(taskType, raw_content) {
    let content;
    if (taskType === "wordlist") {
        content = raw_content
            .map(({word, translation}) => `<b>${word}</b> - ${translation}`)
            .join('<br>');
    } else if (taskType === "matchupthewords") {
        content = Object.entries(raw_content)
            .map(([word, translation]) => `${word} - ${translation}`)
            .join('\n');
    } else if (taskType === "labelimages") {
        content = raw_content.join(', ');
    } else if (taskType === "unscramble") {
        content = raw_content.map(({ word, shuffled_word, hint }) => {
            let formatted = `${word.replaceAll("␣", " ")}`;
            if (hint) {
                formatted += ` (${hint})`;
            }
            return formatted;
        }).join(', ');
    } else if (taskType === "fillintheblanks") {
        content = raw_content.replaceAll(/\[(.*?)\]/g, "_");
    } else if (taskType === "test") {
        content = raw_content.map((q, qIndex) => {
            let answers = q.answers.map((a, aIndex) =>
                `   ${aIndex + 1}. ${a.text} ${a.is_correct ? "(✔)" : ""}`
            ).join("\n");
            return `${qIndex + 1}. ${q.text}\n${answers}<br>`;
        }).join("\n\n");
    } else if (taskType === "makeasentence") {
        content = raw_content.map(sentence => sentence.correct).join("<br>");
    } else if (taskType === "sortintocolumns") {
        content = raw_content
            .map(col => `${col.name} - ${col.words.join(", ")}`)
            .join("<br>");
    } else if (taskType === "trueorfalse") {
        content = raw_content.map(statement => `${statement.text}: ${statement.is_true ? "Правда" : "Ложь"}`)
            .join("<br>");
    } else if (taskType === "audio") {
        content = "Audio script: " + raw_content;
    } else {
        content = raw_content;
    }
    return content;
}


async function formatAndAddTaskToContext(taskId) {
    // Получаем данные с сервера
    const taskData = await fetchTaskData(taskId);
    if (!taskData) return;

    // Убираем id и title, оставляем только контент
    const { id, title, image_urls, audio_url, display_format, taskType, ...contentData } = taskData;
    const raw_content = Object.values(contentData)[0] || "Нет данных";

    let header = elementRussianNames[taskType];
    const content = formatTaskContent(taskType, raw_content);

    // Добавляем задание в контекст
    addTaskToContext(lessonId, taskId, header, content);
}

async function updateTaskInContext(taskId) {
    const context = await getContext(lessonId, "view");

    if (!context) {
        console.error("Context not found");
        return;
    }

    // Преобразуем context в массив для удобства
    const contextEntries = Object.entries(context);

    contextEntries.forEach(([existingTaskId, taskData]) => {
        if (existingTaskId === taskId) {
            // Удаляем старое
            removeTaskFromContext(taskId);
            // Добавляем новое
            formatAndAddTaskToContext(taskId);
        }
    });
}





        // Выбор и добавление учеников

const activeTaskTypes = ['wordlist', 'matchupthewords', 'labelimages', 'unscramble', 'fillintheblanks', 'test', 'makeasentence', 'sortintocolumns', 'trueorfalse', 'essay'];

document.addEventListener('DOMContentLoaded', () => {
    const studentOptions = document.querySelectorAll('.student-option');

    studentOptions.forEach(option => {
        option.addEventListener('click', (event) => {
            event.preventDefault(); // Предотвращаем переход по ссылке

            // Получаем ID выбранного ученика
            studentId = option.dataset.studentId;

            const taskContainers = document.querySelectorAll('.task-item');
            taskContainers.forEach(container => {
                const taskId = container.id;
                const taskType = container.getAttribute('data-task-type');
                const capitalizedTaskType = taskType.charAt(0).toUpperCase() + taskType.slice(1);

                if (taskType && activeTaskTypes.includes(taskType)) {
                    const functionName = `clear${capitalizedTaskType}Answer`;
                    if (typeof window[functionName] === 'function') {
                        window[functionName](taskId);
                    }
                    displayUserStats(taskId);
                }
            });

            // Обновляем текст кнопки на имя выбранного ученика
            const dropdownButton = document.getElementById('studentDropdown');
            dropdownButton.textContent = option.textContent;

            // Здесь можно добавить AJAX-запрос или другую логику
        });
    });
});



        // Сохранение задания

async function saveTask(params, payloads) {
    const url = `/hub/section/${params.section_id}/task/save`;

    const requestData = {
        obj_id: params.obj_id || null,
        task_type: params.task_type,
        payloads: payloads
    };

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify(requestData)
        });

        const data = await response.json();

        if (data.success) {
            return data.task_id;
        } else {
            showNotification(data.error, "danger");
            return null;
        }
    } catch (error) {
        showNotification('Ошибка сети при сохранении задания.', "danger");
        return null;
    }
}



        // Модальное окно удалений


function bootstrapConfirm(message = 'Вы уверены?') {
    return new Promise((resolve) => {
        // Создаем минималистичную модалку
        const modalEl = document.createElement('div');
        modalEl.className = 'modal fade';
        modalEl.innerHTML = `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content border-0 shadow-none">
                    <div class="modal-body p-4 text-center">
                        <p class="mb-3 fs-6">${message}</p>
                        <div class="d-flex justify-content-end gap-2">
                            <button id="confirmCancel" class="btn btn-sm border-0 text-secondary fw-bold fs-6 p-2">Нет</button>
                            <button id="confirmOk" class="btn btn-sm border-0 text-primary fw-bold fs-6 p-2">Да</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modalEl);

        const modal = new bootstrap.Modal(modalEl);
        const okBtn = modalEl.querySelector('#confirmOk');
        const cancelBtn = modalEl.querySelector('#confirmCancel');

        const cleanup = () => {
            okBtn.removeEventListener('click', onOk);
            cancelBtn.removeEventListener('click', onCancel);
            modal.hide();
            modalEl.addEventListener('hidden.bs.modal', () => modalEl.remove());
        };

        const onOk = () => { cleanup(); resolve(true); };
        const onCancel = () => { cleanup(); resolve(false); };

        okBtn.addEventListener('click', onOk);
        cancelBtn.addEventListener('click', onCancel);
        modal.show();
    });
}

// Пример использования
// Заменяем window.confirm на bootstrapConfirm
async function deleteAction() {
    const result = await bootstrapConfirm();
    if (result) {
        alert('Действие подтверждено');
        // Тут код удаления или другого действия
    } else {
        alert('Действие отменено');
    }
}


if (mode === 'classroom') {
    document.addEventListener('DOMContentLoaded', function () {
        const invitationModal = document.getElementById('invitationModal');
        const invitationLinkInput = document.getElementById('invitationLink');
        const copyLinkButton = document.getElementById('copyLinkButton');

        // Обработчик открытия модального окна
        invitationModal.addEventListener('show.bs.modal', function () {
            fetch(`/invite/${classroomId}/`)
                .then(response => response.json())
                .then(data => {
                    invitationLinkInput.value = data.invitation_url; // Вставляем ссылку в поле
                })
                .catch(error => console.error('Ошибка при получении ссылки:', error));
        });

        // Обработчик копирования ссылки
        copyLinkButton.addEventListener('click', function () {
            invitationLinkInput.select();
            document.execCommand('copy');
            showNotification('Ссылка скопирована!', "success");
        });
    });
}

// Проверка ответов
if (mode === 'generation') {
    function checkFrontendTrueFalseAnswers(taskId) {
    const taskBlock = document.querySelector(`.task-item[data-task-type='trueorfalse'][id='${taskId}']`);
    if (!taskBlock) return;

    fetchComplexTaskData(taskId)
        .then(data => {
            const questions = taskBlock.querySelectorAll(".question-item");

            data.answers.forEach((answerObj, index) => {
                const { is_true } = answerObj;
                const question = questions[index];
                if (!question) return;

                const trueInput = question.querySelector(`input[type="radio"][value="true"]`);
                const falseInput = question.querySelector(`input[type="radio"][value="false"]`);

                const trueLabel = question.querySelector(`label[for='${trueInput.id}']`);
                const falseLabel = question.querySelector(`label[for='${falseInput.id}']`);

                const selectedInput = trueInput.checked ? trueInput : (falseInput.checked ? falseInput : null);

                // Сбросить стили и заблокировать выбор
                [trueInput, falseInput].forEach(input => input.disabled = true);
                [trueLabel, falseLabel].forEach(label => {
                    label.classList.remove("correct_label", "incorrect_label");
                });

                if (selectedInput) {
                    const isSelectedCorrect = selectedInput.value === String(is_true);
                    const selectedLabel = selectedInput === trueInput ? trueLabel : falseLabel;

                    if (isSelectedCorrect) {
                        // Верный ответ → подсветим
                        selectedLabel.classList.add("correct_label");
                    } else {
                        // Неверный ответ → только красным
                        selectedLabel.classList.add("incorrect_label");
                    }
                }
            });
        })
        .catch(err => {
            console.error("Error checking true or false answers:", err);
        });
}

    function checkFrontendTestAnswers(taskId) {
        const form = document.querySelector(`.test-form[data-task-id='${taskId}']`);
        if (!form) return;

        fetchComplexTaskData(taskId).then(data => {
            const correct = extractCorrectAnswers(data.answers);

            correct.forEach(({ "question-index": qIndex, answers: correctAnswers }) => {
                const questionBlock = form.querySelector(
                    `.question-item[data-question-id='${qIndex}']`
                );

                if (!questionBlock) return;

                const radios = questionBlock.querySelectorAll(`input[name='question-${qIndex}']`);

                radios.forEach((radio, index) => {
                    const label = questionBlock.querySelector(`label[for='${radio.id}']`);
                    if (!label) return;

                    radio.disabled = true;
                    label.classList.remove("correct_label", "incorrect_label");

                    const isChecked = radio.checked;
                    const isCorrect = correctAnswers.includes(index);

                    if (isChecked && isCorrect) {
                        label.classList.add("correct_label");
                    } else if (isChecked && !isCorrect) {
                        label.classList.add("incorrect_label");
                        // также отметить правильный
                        correctAnswers.forEach(correctIndex => {
                            const correctRadio = radios[correctIndex];
                            const correctLabel = questionBlock.querySelector(`label[for='${correctRadio.id}']`);
                            if (correctLabel) correctLabel.classList.add("correct_label");
                        });
                    }
                });
            });
        }).catch(err => {
            console.error("Error checking answers:", err);
        });
    }

    async function fetchComplexTaskData(taskId) {
        const response = await fetch("/api/get-complex-answers/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ task_id: taskId }),
        });

        if (!response.ok) {
            throw new Error('Failed to fetch task data');
        }

        return await response.json();
    }

    // Получить правильные ответы теста
    function extractCorrectAnswers(questions) {
        return questions.map((q, i) => ({
            "question-index": i,
            answers: q.answers
                .map((a, j) => a.is_correct ? j : -1)
                .filter(j => j !== -1)
        }));
    }
}
const pdfContainer = document.getElementById("pdf-container");
const lessonName = document.getElementById("task-list").dataset.lessonName;
let existingTaskIds
let pdfFormatting = false;
if (document.getElementById("task-list").dataset.existingTaskIds) {
    existingTaskIds = JSON.parse(document.getElementById("task-list").dataset.existingTaskIds.replace(/'/g, '"'));
} else {
    existingTaskIds = [];
    pdfFormatting = true;
}

function handleWordlist(task_id, payloads) {
    const { id, title, words } = payloads;
    const taskContainer = document.getElementById(`${id}`);

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header p-0 m-0 bg-white d-flex align-items-center justify-content-between rounded border-0">
            <div class="bg-primary rounded text-white p-2 w-100">
                <span class="task-title fw-bold">${title}</span>
            </div>
            <input 
                type="checkbox" 
                class="form-check-input select-task ms-3 p-2" 
                title="Выбрать задание" 
                data-task-id="${id}" 
                name="tasks" 
                ${existingTaskIds.includes(id) || pdfFormatting ? "checked" : ""}
            >
        </div>

        <!-- Список слов -->
        <div class="card-body">
            <div class="words-list">
                ${words.map(({ word, translation }) => `
                    <div class="word-item mb-1 d-flex align-items-center justify-content-between position-relative p-2 border rounded">
                        <div class="me-3">
                            <span class="fw-bold me-1">${word}</span> - <span class="ms-1">${translation}</span>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
    // Обработчик нажатия для отметки слов
    const markButtons = taskContainer.querySelectorAll('.btn-mark-word');
    markButtons.forEach(btn => {
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            const wordItem = btn.closest('.word-item');
            const icon = btn.querySelector('i');

            if (wordItem) {
                wordItem.classList.toggle('bg-light');
                icon.classList.toggle('bi-square');
                icon.classList.toggle('bi-square-fill');
                btn.classList.toggle('text-warning');
            }
        });
    });
}

function handleMatchupthewords(task_id, payloads) {
    const { id, title, pairs } = payloads;
    const taskContainer = document.getElementById(`${id}`);
    if (!taskContainer) return;

    // Исходные массивы
    const words = pairs.map(item => item.card1);
    const translations = pairs.map(item => item.card2);

    // Перемешиваем независимо
    const shuffledWords = shuffleArray([...words]);
    const shuffledTranslations = shuffleArray([...translations]);

    // Генерируем HTML
    const rowsHTML = shuffledWords.map((word, index) => {
        const translation = shuffledTranslations[index];
        return `
            <div class="row pair mb-2 d-flex align-items-stretch g-2">
                <div class="col-6">
                    <button class="match-btn btn btn-outline-secondary fs-6 fw-bold w-100 h-100" data-word="${escapeHtml(word)}">
                        ${word.replace(/&quot;/g, '"')}
                    </button>
                </div>
                <div class="col-6">
                    <button class="match-btn btn btn-outline-secondary fs-6 fw-bold w-100 h-100" data-translation="${escapeHtml(translation)}">
                        ${translation.replace(/&quot;/g, '"')}
                    </button>
                </div>
            </div>
        `;
    }).join('');

    // Сборка HTML-карточки
    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header p-0 m-0 bg-white d-flex align-items-center justify-content-between border-0">
            <div class="border-bottom text-dark p-2 w-100">
                <span class="task-title fw-bold">${title}</span>
            </div>
            <input 
                type="checkbox" 
                class="form-check-input select-task ms-3 p-2" 
                title="Выбрать задание" 
                data-task-id="${id}" 
                name="tasks" 
                ${existingTaskIds.includes(id) || pdfFormatting ? "checked" : ""}
            >
        </div>

        <!-- Тело карточки -->
        <div class="card-body">
            <div class="container">
                ${rowsHTML}
            </div>
        </div>
    `;
}

function handleFillintheblanks(task_id, payloads) {
    const { id, title, text, display_format, labels } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    // Разбиваем текст по пропускам в квадратных скобках.
    // Элементы массива – либо обычный текст, либо "[ответ]"
    const parts = text.split(/(\[.*?\])/g);

    let blanksHTML = '';
    let blankIndex = 0;

    // Формируем HTML для текста с пропусками
    parts.forEach(part => {
        if (part.startsWith('[') && part.endsWith(']')) {
            // Извлекаем ответ, удаляя квадратные скобки
            const answer = part.slice(1, -1);
            blanksHTML += `
                <span class="blank-container position-relative d-inline-block">
                    <input type="text"
                           class="blank-input form-control mb-1 rounded text-center d-inline-block"
                           data-task-id="${id}"
                           data-blank-id="${blankIndex}"
                           data-correct-answer="${escapeHtml(answer)}"
                           style="min-width: 100px; max-width: 100%; font-size: 14px; line-height: 14px;;"
                           inputmode="text"
                           enterkeyhint="done">
                </span>
            `;
            blankIndex++;
        } else {
            blanksHTML += `<span class="text-part">${part}</span>`;
        }
    });

    // Если формат "list" - выводим список ответов
    let wordListHTML = '';
    if (display_format === 'withList') {
        wordListHTML = `
            <div class="word-list mb-3">
                <ul class="list-unstyled d-flex flex-wrap gap-2">
                    ${labels.map((word) => `
                        <li class="badge bg-primary text-white fs-6 word-item"
                            data-word="${escapeHtml(word)}">
                            ${word}
                        </li>
                    `).join('')}
                </ul>
            </div>
        `;
    }

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header p-0 m-0 bg-white d-flex align-items-center justify-content-between border-0">
            <div class="border-bottom text-dark p-2 w-100">
                <span class="task-title fw-bold">${title}</span>
            </div>
            <input 
                type="checkbox" 
                class="form-check-input select-task ms-3 p-2" 
                title="Выбрать задание" 
                data-task-id="${id}" 
                name="tasks" 
                ${existingTaskIds.includes(id) || pdfFormatting ? "checked" : ""}
            >
        </div>

        <!-- Тело карточки -->
        <div class="card-body rounded-bottom">
            ${wordListHTML}
            <div class="blanks-text lh-base">
                ${blanksHTML}
            </div>
        </div>
    `;
}

function handleNote(task_id, payloads) {
    const { id, title, content } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header p-0 m-0 bg-white d-flex align-items-center justify-content-between rounded border-0">
            <div class="bg-success rounded text-white p-2 w-100">
                <span class="task-title fw-bold">${title}</span>
            </div>
            <input
                type="checkbox" 
                class="form-check-input select-task ms-3 p-2" 
                title="Выбрать задание" 
                data-task-id="${id}" 
                name="tasks" 
                ${existingTaskIds.includes(id) || pdfFormatting ? "checked" : ""}
            >
        </div>

        <!-- Тело карточки -->
        <div class="card-body">
            <div class="article-content text-part">
                ${content}
            </div>
        </div>
    `;
}

function handleArticle(task_id, payloads) {
    const { id, title, content, isTeacher } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header p-0 m-0 bg-white d-flex align-items-center justify-content-between rounded border-0">
            <div class="bg-success rounded text-white p-2 w-100">
                <span class="task-title fw-bold">${title}</span>
            </div>
            <input 
                type="checkbox" 
                class="form-check-input select-task ms-3 p-2" 
                title="Выбрать задание" 
                data-task-id="${id}" 
                name="tasks" 
                ${existingTaskIds.includes(id) || pdfFormatting ? "checked" : ""}
            >
        </div>

        <!-- Тело карточки -->
        <div class="card-body rounded-bottom">
            <div class="article-content text-part">
                ${content}
            </div>
        </div>
    `;
}

function handleTest(task_id, payloads) {
    const { id, title, questions } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    // Формируем HTML для вопросов
    let questionsHTML = "";
    if (Array.isArray(questions)) {
        questions.forEach((question, qIndex) => {
            let answersHTML = "";
            if (Array.isArray(question.answers)) {
                question.answers.forEach((answer, aIndex) => {
                    answersHTML += `
                        <div class="form-check answer-item mb-2">
                            <input class="form-check-input ${answer.is_correct ? 'correct-radio' : ''}" type="radio"
                                   name="question-${qIndex}"
                                   id="answer-${id}-${qIndex}-${aIndex}"
                                   value="${aIndex}"
                                   data-question-id="${qIndex}"
                                   data-answer-id="${aIndex}">
                            <label class="form-check-label fs-6"
                                   for="answer-${id}-${qIndex}-${aIndex}">
                                ${answer.text}
                            </label>
                        </div>
                    `;
                });
            }
            questionsHTML += `
                <div class="question-item mb-4 p-3 rounded border border-light" data-question-id="${qIndex}">
                    <p class="fw-bold mb-3">${question.text}</p>
                    <div class="answers-list">
                        ${answersHTML}
                    </div>
                </div>
            `;
        });
    }

    // Итоговая разметка
    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header p-0 m-0 bg-white d-flex align-items-center justify-content-between border-0">
            <div class="border-bottom text-dark p-2 w-100">
                <span class="task-title fw-bold">${title}</span>
            </div>
            <input 
                type="checkbox" 
                class="form-check-input select-task ms-3 p-2" 
                title="Выбрать задание" 
                data-task-id="${id}" 
                name="tasks" 
                ${existingTaskIds.includes(id) || pdfFormatting ? "checked" : ""}
            >
        </div>

        <div class="card-body">
            ${questions && questions.length ? `
            <form class="test-form" data-task-id="${id}">
                ${questionsHTML}
                <button type="button" class="btn btn-primary task-check w-100 mt-4 disabled" disabled>
                    Проверить
                </button>
            </form>
            ` : ""}
        </div>
    `;
}

function handleTrueorfalse(task_id, payloads) {
    const { id, title, statements } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    let statementsHTML = "";
    if (Array.isArray(statements)) {
        statements.forEach((statement, index) => {
            const counter = index + 1;
            statementsHTML += `
                <div class="question-item card mb-3" data-index="${index}">
                    <div class="card-body">
                        <div class="d-flex align-items-center mb-3">
                            <i class="bi bi-chat-quote text-primary fs-4 me-3"></i>
                            <span class="fw-bold">${statement.text}</span>
                        </div>
                        <div class="form-check mb-2">
                            <input class="form-check-input ${statement.is_true ? 'correct-radio' : ''}"
                                   type="radio" name="statement-${counter}"
                                   id="true_${counter}" value="true"
                                   data-statement-index="${index}">
                            <label class="form-check-label" for="true_${counter}">
                                Правда
                            </label>
                        </div>
                        <div class="form-check mb-3">
                            <input class="form-check-input ${!statement.is_true ? 'correct-radio' : ''}"
                                   type="radio" name="statement-${counter}"
                                   id="false_${counter}" value="false"
                                   data-statement-index="${index}">
                            <label class="form-check-label" for="false_${counter}">
                                Ложь
                            </label>
                        </div>
                    </div>
                </div>
            `;
        });
    }

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header p-0 m-0 bg-white d-flex align-items-center justify-content-between border-0">
            <div class="border-bottom text-dark p-2 w-100">
                <span class="task-title fw-bold">${title}</span>
            </div>
            <input 
                type="checkbox" 
                class="form-check-input select-task ms-3 p-2" 
                title="Выбрать задание" 
                data-task-id="${id}" 
                name="tasks" 
                ${existingTaskIds.includes(id) || pdfFormatting ? "checked" : ""}
            >
        </div>
        <div class="card-body">
            <div class="statements-list">
                ${statementsHTML}
                <button type="button" class="btn btn-primary task-check w-100 mt-4" disabled>
                    Проверить
                </button>
            </div>
        </div>
    `;
}

function handleUnscramble(task_id, payloads) {
    const { id, title, words } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    let wordsHTML = "";
    if (Array.isArray(words)) {
        words.forEach((element) => {
            // Используем исходное слово напрямую для data-атрибута
            const wordData = element.word;

            // Формируем поля для букв: для каждой буквы исходного слова
            let wordFieldsHTML = "";
            for (let i = 0; i < element.word.length; i++) {
                wordFieldsHTML += `
                    <div class="position-relative d-inline-block">
                        <div class="border border-primary border-2 rounded text-center fw-bold fs-5 empty-slot position-relative"
                             style="width: 40px; height: 40px; line-height: 40px;"
                             data-letter-id="${i}" data-correct-letter="${escapeHtml(element.word[i])}">
                        </div>
                    </div>
                `;
            }

            // Формируем кнопки с буквами: перебираем каждую букву перемешанного слова
            let letterButtonsHTML = "";
            let shuffledLetters = [];
            if (typeof element.shuffled_word === "string") {
                shuffledLetters = element.shuffled_word.split('');
            } else if (Array.isArray(element.shuffled_word)) {
                shuffledLetters = element.shuffled_word;
            }
            shuffledLetters.forEach((letter, index) => {
                letterButtonsHTML += `
                    <button class="btn btn-outline-dark fw-bold letter-button"
                            style="width: 40px; height: 40px; font-family: 'Verdana';"
                            data-letter="${escapeHtml(letter)}"
                            data-letter-id="${index}">
                        ${letter}
                    </button>
                `;
            });


            // Если есть подсказка
            let hintHTML = "";
            if (element.hint) {
                hintHTML = `
                    <div class="hint-container mt-3 text-center text-muted">
                        <i class="bi bi-lightbulb"></i> Подсказка: ${element.hint}
                    </div>
                `;
            }

            // Иконки статуса (фиксированное количество, как в шаблоне)
            const statusIconsHTML = `
                <div class="d-flex align-items-center mb-2 justify-content-center">
                    <i class="bi bi-x-circle text-success fs-4 me-2"></i>
                    <i class="bi bi-x-circle text-success fs-4 me-2"></i>
                    <i class="bi bi-x-circle text-success fs-4"></i>
                </div>
            `;

            wordsHTML += `
                <div class="word-container mb-4" data-errors="0" data-word="${escapeHtml(wordData)}">
                    ${statusIconsHTML}
                    <div class="d-flex flex-wrap gap-2 mb-2 word-fields justify-content-center" data-word="${escapeHtml(wordData)}">
                        ${wordFieldsHTML}
                    </div>
                    <div class="flex-wrap gap-2 letter-buttons justify-content-center" style="display: flex;">
                        ${letterButtonsHTML}
                    </div>
                    ${hintHTML}
                </div>
            `;
        });
    }

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header p-0 m-0 bg-white d-flex align-items-center justify-content-between border-0">
            <div class="border-bottom text-dark p-2 w-100">
                <span class="task-title fw-bold">${title}</span>
            </div>
                        <input 
                type="checkbox" 
                class="form-check-input select-task ms-3 p-2" 
                title="Выбрать задание" 
                data-task-id="${id}" 
                name="tasks" 
                ${existingTaskIds.includes(id) || pdfFormatting ? "checked" : ""}
            >
        </div>

        <!-- Тело карточки -->
        <div class="card-body rounded-bottom">
            ${wordsHTML}
        </div>
    `;
}

function handleMakeasentence(task_id, payloads) {
    const { id, title, sentences } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    const renderSentence = (sentence) => {
        const correctWords = sentence.correct.split(" ");
        const shuffledWords = sentence.shuffled.split(" ");

        const fieldsHTML = correctWords.map((word, index) => `
            <div class="position-relative d-inline-block">
                <div class="border border-primary border-2 rounded text-center fw-bold fs-5 empty-slot position-relative"
                     style="min-width: 70px; height: 30px; line-height: 30px;"
                     data-word-position="${index}" data-correct-answer="${escapeHtml(word)}"></div>
            </div>
        `).join("");

        const wordButtonsHTML = shuffledWords.map((word) => `
            <button class="btn btn-outline-dark word-button"
                    style="min-width: 70px; height: 30px; font-size: 14px; line-height: 14px;"
                    data-word="${escapeHtml(word)}">${word}</button>
        `).join("");

        const statusIconsHTML = `
            <div class="d-flex align-items-center mb-2 justify-content-center">
                ${Array(3).fill(`<i class="bi bi-x-circle text-success fs-4 me-2"></i>`).join("").replace(/me-2<\/i>$/, '</i>')}
            </div>
        `;

        return `
            <div class="sentence-container mb-5">
                ${statusIconsHTML}
                <div class="d-flex flex-wrap gap-2 mb-2 sentence-fields justify-content-start">${fieldsHTML}</div>
                <div class="flex-wrap gap-2 word-buttons justify-content-start d-flex">${wordButtonsHTML}</div>
            </div>
        `;
    };

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header p-0 m-0 bg-white d-flex align-items-center justify-content-between border-0">
            <div class="border-bottom text-dark p-2 w-100">
                <span class="task-title fw-bold">${title}</span>
            </div>
            <input 
                type="checkbox" 
                class="form-check-input select-task ms-3 p-2" 
                title="Выбрать задание" 
                data-task-id="${id}" 
                name="tasks" 
                ${existingTaskIds.includes(id) || pdfFormatting ? "checked" : ""}
            >
        </div>
        <div class="card-body">
            ${(sentences || []).map(renderSentence).join("")}
        </div>
    `;
}

function handleEssay(task_id, payloads) {
    const { id, title, conditions } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    // Формируем HTML для условий
    let conditionsHTML = '';
    let gradingFieldsHTML = '';
    if (conditions && Array.isArray(conditions)) {
        conditions.forEach((criteria, index) => {
            if (criteria.text) {
                const max = Number(criteria.points);
                conditionsHTML += `
                    <div class="condition-item mb-3 p-3 rounded-3 border border-light-subtle">
                        <div class="d-flex align-items-center justify-content-between">
                            <label class="mb-0">
                                <span class="d-block fw-semibold">${criteria.text}</span>
                                <small class="text-muted">Критерий оценки</small>
                            </label>
                            <div class="d-flex align-items-center ms-3">
                                <span class="badge bg-primary-subtle text-primary border border-primary rounded-pill px-3 py-2">
                                    ${criteria.points} ${getBallWord(criteria.points)}
                                </span>
                            </div>
                        </div>
                    </div>
                `;
                gradingFieldsHTML += `
                    <div class="mb-3">
                        <label class="form-label fw-semibold">${criteria.text}</label>
                        <input type="number" min="0" max="${max}" data-index="${index}" class="form-control grade-input" placeholder="Оценка (0–${max})">
                    </div>
                `;
            }
        });
    }

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header p-0 m-0 bg-white d-flex align-items-center justify-content-between border-0">
            <div class="border-bottom text-dark p-2 w-100">
                <span class="task-title fw-bold">${title}</span>
            </div>
            <input 
                type="checkbox" 
                class="form-check-input select-task ms-3 p-2" 
                title="Выбрать задание" 
                data-task-id="${id}" 
                name="tasks" 
                ${existingTaskIds.includes(id) || pdfFormatting ? "checked" : ""}
            >
        </div>

        <!-- Содержимое -->
        <div class="card-body p-4">
            <div class="conditions-list mb-4">${conditionsHTML}</div>

            <!-- Поле для эссе -->
            <div id="essay-editor-${id}"
                 class="essay-editor border rounded-3 p-3 mb-3"
                 contenteditable="true"
                 style="min-height: 200px; overflow-y: auto;">
            </div>

            <div class="d-flex justify-content-between align-items-center text-muted mb-3">
                <button class="btn btn-primary essay-submit-btn">Отправить</button>
                <span id="word-count-${id}">0 слов</span>
            </div>

            <div class="essay-note mt-3"></div>
        </div>
    `;
}

function handleImage(task_id, payloads) {
    const { id, title, image_url } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header p-0 m-0 bg-white d-flex align-items-center justify-content-between rounded border-0">
            <div class="bg-primary rounded text-white p-2 w-100">
                <span class="task-title fw-bold">${title}</span>
            </div>
            <input 
                type="checkbox" 
                class="form-check-input select-task ms-3 p-2" 
                title="Выбрать задание" 
                data-task-id="${id}" 
                name="tasks" 
                ${existingTaskIds.includes(id) || pdfFormatting ? "checked" : ""}
            >
        </div>

        <!-- Тело карточки -->
        <div class="card-body border-0">
            <img src="${image_url}" alt="" class="img-fluid rounded">
        </div>
    `;
}

function handleLabelimages(task_id, payloads) {
    const { id, title, images, labels } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    // Генерация списка меток
    const badgeListHTML = `
        <div class="word-list mb-4">
            <ul class="list-unstyled d-flex flex-wrap gap-2">
                ${labels.map((label, index) => `
                    <li class="badge bg-primary text-white fs-6 word-item"
                        data-word="${escapeHtml(label)}"
                        data-label-id="label-${id}-${index}">
                        ${label}
                    </li>
                `).join('')}
            </ul>
        </div>
    `;

    // Генерация изображений
    const imagesHTML = images.map((image, index) => {
        const correctLabel = image.label || "";
        const url = image.url;

        return `
            <div class="col-xxl-2 col-lg-3 col-md-4 col-sm-6">
                <div class="card h-100 border-0">
                    <div class="square-image-container position-relative">
                        <div class="square-image">
                            <img src="${url}" class="img-fluid rounded" style="object-fit: cover;">
                        </div>
                    </div>
                    <div class="card-body p-0 mt-3">
                        <span class="label-container position-relative d-inline-block w-100">
                            <input type="text"
                                   class="form-control label-image w-100"
                                   data-task-id="${id}"
                                   data-image-index="${index}"
                                   data-image-url="${url}"
                                   data-correct-label="${escapeHtml(correctLabel)}"
                                   inputmode="text"
                                   enterkeyhint="done">
                        </span>
                    </div>
                </div>
            </div>
        `;
    }).join('');

    // Отображение задания
    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header p-0 m-0 bg-white d-flex align-items-center justify-content-between border-0">
            <div class="border-bottom text-dark p-2 w-100">
                <span class="task-title fw-bold">${title}</span>
            </div>
            <input 
                type="checkbox" 
                class="form-check-input select-task ms-3 p-2" 
                title="Выбрать задание" 
                data-task-id="${id}" 
                name="tasks" 
                ${existingTaskIds.includes(id) || pdfFormatting ? "checked" : ""}
            >
        </div>
        <div class="card-body rounded-bottom">
            ${badgeListHTML}
            <div class="row g-4">
                ${imagesHTML}
            </div>
        </div>
    `;
}

function handleSortintocolumns(task_id, payloads) {
    const { id, title, columns, labels } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    let wordBankHTML = labels.map(word => `
        <span class="badge bg-primary draggable-word fs-6" draggable="true" data-word="${escapeHtml(word)}">
            ${word}
        </span>
    `).join('');

    let columnsHTML = "";
    columns.forEach(col => {
        const correctText = col.words.join(", ");
        columnsHTML += `
            <div class="col-12 col-md-6 col-lg-4 col-xl-3">
                <div class="card h-100 column-dropzone" data-column="${escapeHtml(col.name)}">
                    <div class="card-header bg-white text-center fw-bold">
                        ${col.name}
                        <input type="checkbox" class="form-check-input select-task ms-3" title="Выбрать задание" data-task-id="${task_id}" name="tasks" {% if task.id in existing_task_ids %}checked{% endif %}>
                    </div>
                    <div class="card-body drop-area p-3 position-relative">
                        <div class="d-flex flex-column gap-2 min-vh-25 overflow-y-auto text-center"></div>
                    </div>
                </div>
            </div>
        `;
    });

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header p-0 m-0 bg-white d-flex align-items-center justify-content-between border-0">
            <div class="border-bottom text-dark p-2 w-100">
                <span class="task-title fw-bold">${title}</span>
            </div>
            <input
                type="checkbox"
                class="form-check-input select-task ms-3 p-2"
                title="Выбрать задание"
                data-task-id="${id}"
                name="tasks"
                {% if task.id in existing_task_ids %}checked{% endif %}
            >
        </div>
        <div class="card-body position-relative">
            <div class="sticky-word-bank">
                <div class="d-flex flex-wrap gap-2 mb-3 word-bank">${wordBankHTML}</div>
            </div>
            <div class="row g-3 mt-3 sortable-columns d-flex justify-content-center">${columnsHTML}</div>
        </div>
    `;
}

function handleAudio(task_id, payloads) {
    const { id, title, audio_url, transcript } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header p-0 m-0 bg-white d-flex align-items-center justify-content-between rounded border-0">
            <div class="bg-primary rounded text-white p-2 w-100">
                <span class="task-title fw-bold">${title}</span>
            </div>
            <input 
                type="checkbox" 
                class="form-check-input select-task ms-3 p-2" 
                title="Выбрать задание" 
                data-task-id="${id}" 
                name="tasks" 
                ${existingTaskIds.includes(id) || pdfFormatting ? "checked" : ""}
            >
        </div>
        <div class="card-body p-4 border-0 rounded-bottom">
            <div class="audio-player-modern">
                <audio preload="metadata" class="audio-element">
                    <source src="${audio_url}" type="audio/mpeg">
                    Ваш браузер не поддерживает аудио элемент.
                </audio>
            </div>
            <button class="btn border-0 text-primary fw-bold mx-auto mt-3" style="display: block;" id="show-transcript-btn">
                Показать скрипт
            </button>
            <div id="transcript-container" class="alert alert-warning p-3 border rounded-3 position-relative mt-3" style="display: none;">
                ${transcript}
            </div>
        </div>
    `;

    const showTranscriptBtn = taskContainer.querySelector('#show-transcript-btn');
    const transcriptContainer = taskContainer.querySelector('#transcript-container');

    if (showTranscriptBtn && transcriptContainer) {
        showTranscriptBtn.addEventListener('click', () => {
            const isVisible = transcriptContainer.style.display === 'block';
            transcriptContainer.style.display = isVisible ? 'none' : 'block';
            showTranscriptBtn.textContent = isVisible ? 'Показать скрипт' : 'Скрыть скрипт';
        });
    }

    const audioElement = taskContainer.querySelector('.audio-element');
    return setupModernAudioPlayer(audioElement);
}

function handleEmbeddedtask(task_id, payloads) {
    const { id, title, embed_code } = payloads;
    if (!embed_code) return;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    const safeEmbed = embed_code; // безопасный iframe или null (проверка на сервере)

    // Экранируем embed_code, если всё-таки передаём его в onclick
    const escapedEmbedCode = embed_code.replaceAll('"', '&quot;');

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header p-0 m-0 bg-white d-flex align-items-center justify-content-between border-0">
            <div class="border-bottom text-dark p-2 w-100">
                <span class="task-title fw-bold">${title}</span>
            </div>
            <input 
                type="checkbox" 
                class="form-check-input select-task ms-3 p-2" 
                title="Выбрать задание" 
                data-task-id="${id}" 
                name="tasks" 
                ${existingTaskIds.includes(id) || pdfFormatting ? "checked" : ""}
            >
        </div>

        <!-- Тело карточки -->
        <div class="card-body p-4">
            <div class="embed-wrapper">
                <!-- Кнопка запуска, embed_code передается через onclick -->
                <button class="btn btn-primary btn-lg w-100 mb-3 d-flex justify-content-between align-items-center"
                        onclick="toggleEmbed(this, '${escapedEmbedCode}')">
                    <span>Перейти</span>
                    <i class="bi bi-arrow-right-circle-fill fs-4"></i>
                </button>

                ${safeEmbed ? `
                    <div class="embed-container embed-responsive embed-responsive-16by9 d-none">
                        <iframe class="embed-responsive-item" allowfullscreen style="border: none; height: 400px;"></iframe>
                    </div>
                ` : `
                    <div class="text-danger">Невозможно отобразить embed-код: источник не разрешён</div>
                `}
            </div>
        </div>
    `;
}

async function fetchTaskData(taskId) {
    try {
        const response = await fetch(`/hub/api/tasks/${taskId}/`);
        if (!response.ok) {
            throw new Error(`Ошибка HTTP: ${response.status}`);
        }
        const data = await response.json();
        return data;
    } catch (error) {
        showNotification("Ошибка при получении данных. Обратитесь в поддержку.", "danger");
        return null; // Возвращаем null в случае ошибки
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    const tasks = document.querySelectorAll(".task-item");

    for (const el of tasks) {
        const taskId = el.id;
        const taskType = el.dataset.taskType;

        if (!taskId || !taskType) continue;

        const taskData = await fetchTaskData(taskId);
        if (!taskData) continue;

        const functionName = `handle${taskType.charAt(0).toUpperCase()}${taskType.slice(1).toLowerCase()}`;

        if (typeof window[functionName] === 'function') {
            try {
                window[functionName](taskId, taskData);
            } catch (error) {
                console.error(error);
            }
        }

        const container = el.closest('.full-task-container');
        if (container) {
            container.style.display = 'flex';
            el.classList.add('mb-4');
            el.style.display = 'block';
        } else {
            console.warn('Container for task-item not found:', el);
        }
    }

    attachCheckboxListeners();
    updateActionButtonsState();
});



function enhanceTextarea(textarea) {
  if (!textarea || !textarea.parentNode) return; // Проверка на существование элемента

  // Устанавливаем contenteditable
  textarea.contentEditable = "true";
  textarea.style.minHeight = "200px;";

  // Создаем контейнер для панели инструментов
  const toolbar = document.createElement("div");
  toolbar.classList.add("d-flex", "mb-2");
  toolbar.style.width = "100%";
  toolbar.style.gap = "4px";

  // Список кнопок с параметрами [иконка, команда, подсказка]
  const buttons = [
    ["bi bi-type-bold", "bold", "Полужирный"],
    ["bi bi-type-italic", "italic", "Курсив"],
    ["bi bi-type-underline", "underline", "Подчёркивание"],
    ["bi bi-list-ul", "insertUnorderedList", "Маркированный список"],
    ["bi bi-list-ol", "insertOrderedList", "Нумерованный список"]
  ];

  // Создание кнопок
  buttons.forEach(([iconClass, command, tooltip]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.classList.add("btn", "btn-outline-primary", "btn-sm", "flex-fill");
    button.innerHTML = `<i class="${iconClass}"></i>`;
    button.setAttribute("title", tooltip);
    button.setAttribute("data-bs-toggle", "tooltip");

    button.addEventListener("click", () => {
      document.execCommand(command, false, null);
      textarea.focus();
    });

    toolbar.appendChild(button);
  });

  // Вставляем панель инструментов перед редактируемым элементом
  textarea.parentNode.insertBefore(toolbar, textarea);

  // Инициализация тултипов Bootstrap 5 (если библиотека загружена)
  if (window.bootstrap?.Tooltip) {
    const tooltips = toolbar.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltips.forEach(el => new bootstrap.Tooltip(el));
  }
}

function getBallWord(number) {
    if (number % 10 === 1 && number % 100 !== 11) {
        return "балл";
    } else if ([2, 3, 4].includes(number % 10) && ![12, 13, 14].includes(number % 100)) {
        return "балла";
    } else {
        return "баллов";
    }
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function escapeHtml(unsafe) {
    const safe = unsafe.toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    return safe;
};

function setupModernAudioPlayer(player) {
    if (!(player instanceof HTMLAudioElement)) {
        console.error('Переданный элемент не является аудиоплеером');
        return;
    }

    const container = document.createElement('div');
    container.className = 'd-flex align-items-center gap-3';

    // Кнопка Play/Pause
    const playBtn = document.createElement('button');
    playBtn.className = 'btn btn-outline-primary rounded d-flex align-items-center justify-content-center';
    playBtn.style.width = '40px';
    playBtn.style.height = '40px';
    playBtn.style.borderRadius = '8px';
    playBtn.innerHTML = '<i class="bi bi-play-fill"></i>';
    playBtn.disabled = true; // Отключаем кнопку до загрузки аудио

    // Прогрессбар
    const progressWrap = document.createElement('div');
    progressWrap.className = 'progress flex-grow-1';
    progressWrap.style.height = '8px';
    progressWrap.style.cursor = 'pointer';

    const progressBar = document.createElement('div');
    progressBar.className = 'progress-bar bg-primary';
    progressBar.style.width = '0%';
    progressWrap.appendChild(progressBar);

    // Время
    const time = document.createElement('div');
    time.className = 'text-muted small';
    time.style.minWidth = '40px';
    time.textContent = '0:00';

    // Сборка
    container.appendChild(playBtn);
    container.appendChild(progressWrap);
    container.appendChild(time);
    player.parentNode.insertBefore(container, player);
    player.classList.add('d-none');

    // Обработчики событий аудио
    const audioEvents = {
        play: () => {
            playBtn.innerHTML = '<i class="bi bi-pause-fill"></i>';
            playBtn.disabled = false;
        },
        pause: () => {
            playBtn.innerHTML = '<i class="bi bi-play-fill"></i>';
            playBtn.disabled = false;
        },
        ended: () => {
            playBtn.innerHTML = '<i class="bi bi-play-fill"></i>';
            progressBar.style.width = '0%';
            time.textContent = '0:00';
        },
        timeupdate: () => {
            if (isFinite(player.duration)) {
                const percent = (player.currentTime / player.duration) * 100;
                progressBar.style.width = `${percent}%`;
                time.textContent = formatTime(player.currentTime);
            }
        },
        canplay: () => {
            playBtn.disabled = false;
            time.textContent = formatTime(player.duration);
        },
        error: () => {
            console.error('Ошибка аудио:', player.error);
            playBtn.innerHTML = '<i class="bi bi-exclamation-triangle"></i>';
            playBtn.classList.add('text-danger');
            time.textContent = 'Ошибка';
        }
    };

    // Добавляем обработчики событий
    Object.entries(audioEvents).forEach(([event, handler]) => {
        player.addEventListener(event, handler);
    });

    // Обработчик клика на кнопку
    playBtn.addEventListener('click', async () => {
        try {
            if (player.paused) {
                await player.play();
            } else {
                player.pause();
            }
        } catch (error) {
            console.error('Ошибка воспроизведения:', error);
            playBtn.innerHTML = '<i class="bi bi-exclamation-triangle"></i>';
        }
    });

    // Обработчик клика на прогрессбар
    progressWrap.addEventListener('click', (e) => {
        if (!isFinite(player.duration)) return;

        const rect = progressWrap.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const percent = Math.min(Math.max(clickX / rect.width, 0), 1);
        player.currentTime = player.duration * percent;
    });

    function formatTime(seconds) {
        if (!isFinite(seconds)) return '0:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60).toString().padStart(2, '0');
        return `${mins}:${secs}`;
    }

    // Возвращаем методы для управления извне
    return {
        play: () => player.play(),
        pause: () => player.pause(),
        destroy: () => {
            Object.entries(audioEvents).forEach(([event, handler]) => {
                player.removeEventListener(event, handler);
            });
            container.remove();
        }
    };
}

function shuffleArray(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [array[i], array[j]] = [array[j], array[i]];
    }
    return array;
}




        // Работа с PDF

function getSelectedTasks() {
    const selectedTasks = [];

    document.querySelectorAll('.task-item').forEach(task => {
        const checkbox = task.querySelector('.select-task');
        if (checkbox && checkbox.checked) {
            selectedTasks.push(task);
        }
    });

    return selectedTasks;
}

// Фразы для оверлея
const loadingPhrases = [
    "Работаем над вашим файлом...",
    "Добавляем стили...",
    "Оптимизируем изображения...",
    "Генерируем PDF-структуру...",
    "Настраиваем шрифты...",
    "Проверяем форматирование...",
    "Уплотняем макет...",
    "Добавляем метаданные...",
    "Сжимаем файл...",
    "Почти готово...",
    "Финальная сборка...",
    "Проверяем совместимость...",
    "Готовим к загрузке..."
];

let phraseIndex = 0;
let phraseInterval;

// Показываем оверлей + запускаем циклическую смену фраз
function showLoadingOverlay() {
    const overlay = document.getElementById('pdfLoadingOverlay');
    const phraseEl = document.getElementById('overlayPhrase');
    const progressEl = document.getElementById('overlayProgress');

    if (!overlay) return;

    overlay.classList.remove('d-none');
    phraseIndex = 0;
    if (phraseEl) phraseEl.textContent = loadingPhrases[phraseIndex];
    if (progressEl) progressEl.textContent = '0%';

    // обновляем фразу каждые 5 секунд
    phraseInterval = setInterval(() => {
        phraseIndex = (phraseIndex + 1) % loadingPhrases.length;
        if (phraseEl) phraseEl.textContent = loadingPhrases[phraseIndex];
    }, 5000);
}

function hideLoadingOverlay() {
    const overlay = document.getElementById('pdfLoadingOverlay');
    if (!overlay) return;
    overlay.classList.add('d-none');
    clearInterval(phraseInterval);
}

// ========== Прогресс-утилиты ==========
let totalTasks = 0;
let completedTasks = 0;

function initProgress(total) {
    totalTasks = total || 0;
    completedTasks = 0;

    const container = document.getElementById('pdfProgressContainer');
    const bar = document.getElementById('pdfProgressBar');
    const txt = document.getElementById('pdfProgressText');
    const pct = document.getElementById('pdfProgressPercent');
    const overlayPct = document.getElementById('overlayProgress');

    if (!container || !bar || !txt) return;

    txt.textContent = `Заданий: 0 / ${totalTasks}`;
    container.classList.remove('d-none');
    if (overlayPct) overlayPct.textContent = '0%';
}

function updateProgress(increment = 1) {
    completedTasks += increment;
    if (completedTasks > totalTasks) completedTasks = totalTasks;

    const bar = document.getElementById('pdfProgressBar');
    const txt = document.getElementById('pdfProgressText');
    const pct = document.getElementById('pdfProgressPercent');
    const overlayPct = document.getElementById('overlayProgress');

    const percent = totalTasks === 0 ? 100 : Math.round((completedTasks / totalTasks) * 100);

    if (bar) {
        bar.style.width = `${percent}%`;
        bar.setAttribute('aria-valuenow', String(percent));
    }
    if (txt) txt.textContent = `Заданий: ${completedTasks} / ${totalTasks}`;
    if (pct) pct.textContent = `${percent}%`;
    if (overlayPct) overlayPct.textContent = `${percent}%`;
}

function finalizeProgress() {
    completedTasks = totalTasks;
    updateProgress(0);
    // прогресс остаётся видимым до закрытия модалки
}

document.getElementById('downloadPdfBtn').addEventListener('click', generatePDF);

async function generatePDF() {
    showLoadingOverlay();

    try {
        // 1. Читаем настройки
        const removeEmojisOpt = document.getElementById('removeEmojis').checked;
        const grayscaleOpt    = document.getElementById('grayscale').checked;
        const fontSizeOpt     = Number(document.getElementById('fontSize').value) || 14;
        if (fontSizeOpt < 10 || fontSizeOpt > 24) {
            alert('Размер шрифта должен быть от 10 до 24px.');
            hideLoadingOverlay();
            return;
        }

        // 2. Подготавливаем контейнер
        pdfContainer.innerHTML = "";
        const titleColor = grayscaleOpt ? '#000000' : '#007bff';

        // Вставляем заголовок как pdf-title
        pdfContainer.innerHTML = `
            <div class="d-flex justify-content-start align-items-center mb-3 pdf-title">
                <label class="mb-0">
                    Name:&nbsp;
                    <input
                        type="text"
                        id="studentName"
                        style="border: none; border-bottom: 1px solid #000; width: 250px; font-size: inherit;"
                    />
                </label>
            </div>
        `;

        // 3. Добавляем задачи внутрь pdfContainer
        const tasks = getSelectedTasks();
        initProgress(tasks.length);

        for (const el of tasks) {
            const taskId   = el.id;
            const taskType = el.dataset.taskType;
            if (!taskId || !taskType) {
                // Помечаем как обработанное, даже если данные некорректны
                updateProgress(1);
                continue;
            }

            const taskData = await fetchTaskData(taskId);
            if (!taskData) {
                updateProgress(1);
                continue;
            }

            const fnName = `handle${taskType[0].toUpperCase()}${taskType.slice(1).toLowerCase()}PDF`;
            if (typeof window[fnName] === 'function') {
                try {
                    window[fnName](taskData, !grayscaleOpt);
                } catch (e) {
                    console.error(e);
                }
            } else {
                // fallback на текстовый рендер
                handleTextPDF(taskData, !grayscaleOpt);
            }

            // Обновляем прогресс после каждого задания
            updateProgress(1);

            // Небольшая пауза, чтобы UI успевал обновляться (по желанию)
            await new Promise(r => setTimeout(r, 20));
        }

        // 4. Фильтруем «пустышки» и применяем стили
        pdfContainer.style.display = 'block';
        Array.from(pdfContainer.querySelectorAll('.pdf-element')).forEach(el => {
            if (el.getBoundingClientRect().height < 5) el.remove();
        });
        if (removeEmojisOpt) removeEmojisFromElement(pdfContainer);
        if (grayscaleOpt) pdfContainer.style.filter = 'grayscale(1)';

        const fontFamily = "'Montserrat','Segoe UI','Helvetica','Arial',sans-serif";
        pdfContainer.style.width      = '794px';
        pdfContainer.style.fontSize   = `${fontSizeOpt}px`;
        pdfContainer.style.fontFamily = fontFamily;
        pdfContainer.querySelectorAll('.pdf-element').forEach(el => {
            el.style.fontSize   = `${fontSizeOpt}px`;
            el.style.fontFamily = fontFamily;
        });
        pdfContainer.querySelectorAll('.pdf-title').forEach(el => {
            el.style.fontSize   = `${fontSizeOpt}px`;
            el.style.fontFamily = fontFamily;
        });

        // 5. Создаём PDF и группируем элементы
        const { jsPDF } = window.jspdf || window.jspPDF || window.jspdf;
        const pdf        = new jsPDF('p','mm','a4');
        const pw         = pdf.internal.pageSize.getWidth(),
              ph         = pdf.internal.pageSize.getHeight();
        const marginX    = 10, marginY = 2, gapMm = 2;
        const contentW   = pw - marginX * 2;

        // 1) Собираем все элементы в одном массиве
        const allEls = Array.from(pdfContainer.children).filter(el =>
            el.classList.contains('pdf-title') ||
            el.classList.contains('pdf-element')
        );

        // 2) Формируем группы: [title+element] или [element]
        const groups = [];
        for (let i = 0; i < allEls.length; ) {
            const el = allEls[i];

            if (el.classList.contains('pdf-title')) {
                const next = allEls[i + 1];
                if (next && next.classList.contains('pdf-element')) {
                    // группа из двух: заголовок + следующий элемент
                    groups.push([el, next]);
                    i += 2;
                } else {
                    // одиночный заголовок (если нет pdf-element после)
                    groups.push([el]);
                    i += 1;
                }
            } else {
                // pdf-element без заголовка
                groups.push([el]);
                i += 1;
            }
        }

        let yOffset = marginY;

        // Функция для рендеринга «LinguaGlow for teachers» вверху страницы
        const addHeader = () => {
            pdf.setFontSize(fontSizeOpt);
            pdf.setFont('helvetica','bold');
            pdf.setTextColor(grayscaleOpt ? '#6c757d' : '#007bff');
            const text = 'LinguaGlow for teachers';
            const txW  = pdf.getTextWidth(text);
            pdf.text(text, pw - marginX - txW, marginY*2+5);
            yOffset = marginY*2 + 10;
        };

        // Рендерим каждую группу целиком
        for (const grp of groups) {
            // Временный wrapper для оценки размера
            const wrapper = document.createElement('div');
            wrapper.style.position = 'absolute';
            wrapper.style.left     = '-9999px';
            wrapper.style.width    = '794px';
            wrapper.style.fontSize = `${fontSizeOpt}px`;
            wrapper.style.fontFamily = fontFamily;
            grp.forEach(el => wrapper.appendChild(el.cloneNode(true)));
            document.body.appendChild(wrapper);

            const canvas = await html2canvas(wrapper, {
                scale: 1.5, useCORS: true, width: 794, windowWidth: 794,
                backgroundColor: grayscaleOpt ? '#fff' : undefined
            });
            const imgW = canvas.width, imgH = canvas.height;
            const imgWmm = contentW, imgHmm = imgH * imgWmm / imgW;

            document.body.removeChild(wrapper);

            // Если не влезает — перелистываем ДО вставки
            if (yOffset + imgHmm + gapMm > ph - marginY) {
                pdf.addPage();
                addHeader();
            } else if (pdf.getNumberOfPages() === 1 && yOffset === marginY) {
                // Для первой страницы тоже добавляем шапку
                addHeader();
            }

            // Вставляем изображение группы
            pdf.addImage(canvas.toDataURL('image/jpeg',1), 'JPEG',
                         marginX, yOffset, imgWmm, imgHmm);
            yOffset += imgHmm + gapMm;
        }

        // Отмечаем прогресс как завершённый
        finalizeProgress();

        // Сохраняем PDF (lessonName можно заменить на вашу переменную)
        const lessonName = typeof window.lessonName !== 'undefined' ? String(window.lessonName) : 'Lesson';
        pdf.save(`LinguaGlow - ${lessonName.slice(0,15)}.pdf`);
    } catch (error) {
        console.error("Ошибка при генерации PDF:", error);
        alert('Ошибка при генерации PDF. Проверьте консоль.');
    } finally {
        // скрываем временный контейнер и оверлей
        if (pdfContainer) pdfContainer.style.display = 'none';
        hideLoadingOverlay();
    }
}

// Убирает эмодзи из текстового содержимого элемента
function removeEmojisFromElement(element) {
    const walk = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    while (walk.nextNode()) {
        walk.currentNode.textContent = walk.currentNode.textContent.replace(
            /([\u2700-\u27BF]|[\uE000-\uF8FF]|[\uD83C-\uDBFF\uDC00-\uDFFF])+|\p{Emoji_Presentation}|\p{Extended_Pictographic}/gu,
            ''
        );
    }
}




        // PDF-шаблоны

function handleWordlistPDF(payloads, is_colorful = true) {
    const { id, title, words } = payloads;

    const headerHtml = `
        <div class="pdf-title ${is_colorful ? 'bg-primary text-white rounded shadow' : 'text-black'}
                    fw-bold p-2 my-4 fst-italic"
             style="${is_colorful ? '' : 'font-size: 1.2rem;'};">
            ${title}
        </div>
    `;

    const rowsHtml = [];
    for (let i = 0; i < words.length; i += 2) {
        const first  = words[i];
        const second = words[i + 1];

        rowsHtml.push(`
            <div class="pdf-element row ms-2" style="line-height: 1.1; margin-bottom: 0;">
                <div class="col-6 d-flex align-items-start px-1" style="padding-top: 0px; padding-bottom: 0px;">
                    <span class="fw-bold me-1">${first.word}</span>
                    <span>-</span>
                    <span class="ms-1">${first.translation}</span>
                </div>
                <div class="col-6 d-flex align-items-start px-1" style="padding-top: 0px; padding-bottom: 0px;">
                    ${second
                      ? `<span class="fw-bold me-1">${second.word}</span>
                         <span>-</span>
                         <span class="ms-1">${second.translation}</span>`
                      : ''
                    }
                </div>
            </div>
        `);
    }

    pdfContainer.innerHTML += headerHtml + rowsHtml.join('');
}

function handleMatchupthewordsPDF(payloads, is_colorful = true) {
    const { id, title, pairs } = payloads;
    const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    const limitedPairs = pairs.slice(0, 15);

    let html = '';

    html += `
        <div class="pdf-title text-black fw-bold p-2 my-4 fst-italic"
            style="font-size: 1.2rem;">
            ${title}
        </div>
    `;

    const words = limitedPairs.map(item => item.card1);
    const translations = limitedPairs.map(item => item.card2);
    const shuffledWords = shuffleArray([...words]);
    const shuffledTranslations = shuffleArray([...translations]);

    html += limitedPairs.map((item, i) => `
        <div class="pdf-element row align-items-start ms-2" style="line-height: 1.1; margin-bottom: 0;">
            <div class="col-6 fw-bold px-1" style="padding-top: 0px; padding-bottom: 0px;">
                ${i + 1}. ${shuffledWords[i]}
            </div>
            <div class="col-6 px-1" style="padding-top: 0px; padding-bottom: 0px;">
                ${letters[i]}. ${shuffledTranslations[i]}
            </div>
        </div>
    `).join('');

    html += `
        <div class="pdf-element mt-2">
            <table class="table table-bordered rounded" style="
                border-width: 2px;
                border-color: #000;
                border-collapse: separate;
                border-spacing: 0;
                border-style: solid;
                border-top: 2px solid #000;
                border-radius: 0.5rem;
                overflow: hidden;">
                <thead>
                    <tr>
                        ${limitedPairs.map((_, i) => `
                            <th scope="col" class="text-center p-1" style="border-bottom: 1px solid #000; border-right: 1px solid #000;">
                                ${i + 1}
                            </th>
                        `).join('')}
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        ${limitedPairs.map((_, i) => `
                            <td style="min-height: 30px; border-bottom: 1px solid #000; border-right: 1px solid #000; padding: 6px;">
                                &nbsp;
                            </td>
                        `).join('')}
                    </tr>
                </tbody>
            </table>
        </div>
    `;

    pdfContainer.innerHTML += html;
}

function handleFillintheblanksPDF(payloads, is_colorful = true) {
    const { title, text, display_format, labels } = payloads;

    // 1) Заголовок
    let html = `
        <div class="pdf-title fw-bold fst-italic p-2 my-4"
            style="font-size: 1.25rem;">
            ${title}
        </div>
    `;

    // 2) Разбиваем текст на текст и ответы [answer]
    const parts = text.split(/(\[.*?\])/g);

    // 3) Собираем все ответы, чтобы вычислить среднюю длину
    const answers = parts
        .filter(p => p.startsWith('[') && p.endsWith(']'))
        .map(p => p.slice(1, -1));
    const avgLen = answers.length
        ? Math.round(answers.reduce((sum, a) => sum + a.length, 0) / (answers.length / 2))
        : 0;
    // Длина линии: не больше 50 символов
    const lineLen = Math.min(50, avgLen || 50);

    // 4) Формируем HTML для текста с линиями
    html += `<div class="pdf-element mb-4" style="line-height: 2;">`;
    parts.forEach(part => {
        if (part.startsWith('[') && part.endsWith(']')) {
            // это пропуск
            html += `
                <span class="d-inline-block mx-1"
                      style="
                        width: ${lineLen}ch;
                        border-bottom: 1px solid #000;
                        vertical-align: bottom;
                      ">
                </span>
            `;
        } else {
            // обычный текст
            html += `<span>${part}</span>`;
        }
    });
    html += `</div>`;

    // 5) Если нужно — список вариантов
    if (display_format === 'withList' && Array.isArray(labels)) {
        html += `
            <div class="pdf-element m-2">
                <ul class="list-unstyled d-flex flex-wrap gap-2">
                    ${labels.map(w => `
                        <li class="badge bg-secondary text-white">
                            ${w}
                        </li>
                    `).join('')}
                </ul>
            </div>
        `;
    }

    // Вставляем в контейнер
    pdfContainer.innerHTML += html;
}

// Определяем формат контента
function detectFormat(content) {
    // HTML
    if (/<[a-z][\s\S]*>/i.test(content)) {
        return "html";
    }
    // Markdown
    if (
        /^#{1,6}\s/m.test(content) ||          // заголовки (# ...)
        /\*\*(.*?)\*\*/.test(content) ||       // жирный (**bold**)
        /\*(.*?)\*/.test(content) ||           // курсив (*italic*)
        /^(\*|-|\+)\s+/m.test(content) ||      // списки (* item, - item, + item)
        /```[\s\S]*```/.test(content)          // блоки кода
    ) {
        return "markdown";
    }
    // По умолчанию — обычный текст
    return "text";
}

// Рендерим по формату
function renderContent(content) {
    const format = detectFormat(content);

    switch (format) {
        case "markdown":
            return marked.parse(content);

        case "text":
            return (
                "<p>" +
                content
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;")
                    .split(/\n{2,}/)           // двойной перенос → новый абзац
                    .map(p => p.replace(/\n/g, "<br>"))
                    .join("</p><p>") +
                "</p>"
            );

        case "html":
        default:
            return content;
    }
}

function handleNotePDF(payloads, is_colorful = true) {
    const { title, content } = payloads;

    // Заголовок
    let html = `
        <div class="pdf-title ${is_colorful ? 'bg-success text-white rounded shadow' : 'text-black'} fw-bold p-2 my-4 fst-italic"
             style="${is_colorful ? '' : 'font-size: 1.25rem;'}">
            ${title}
        </div>
    `;

    // Разбиваем контент на абзацы (по двойному переводу строки или тегам <p>)
    const paragraphs = renderContent(content)
        .split(/\n\s*\n|<\/p>\s*<p>|<\/p>|<p>/i)
        .map(p => p.trim())
        .filter(p => p.length > 0);

    // Каждый абзац оборачиваем в отдельный pdf-element
    paragraphs.forEach(p => {
        html += `
            <div class="pdf-element mb-1">
                ${p}
            </div>
        `;
    });

    pdfContainer.innerHTML += html;
}

function handleArticlePDF(payloads, is_colorful = true) {
    const { title, content } = payloads;

    // Заголовок
    let html = `
        <div class="pdf-title ${is_colorful ? 'bg-success text-white rounded shadow' : 'text-black'} fw-bold p-2 my-4 fst-italic"
             style="${is_colorful ? '' : 'font-size: 1.25rem;'}">
            ${title}
        </div>
    `;

    // Разбиваем контент на абзацы
    const paragraphs = renderContent(content)
        .split(/\n\s*\n|<\/p>\s*<p>|<\/p>|<p>/i)
        .map(p => p.trim())
        .filter(p => p.length > 0);

    // Каждый абзац — отдельный pdf-element
    paragraphs.forEach(p => {
        html += `
            <div class="pdf-element mb-1">
                ${p}
            </div>
        `;
    });

    pdfContainer.innerHTML += html;
}

function handleTestPDF(payloads, is_colorful = true) {
    const { id, title, questions } = payloads;
    if (!Array.isArray(questions)) return;

    const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    let html = '';

    // Заголовок
    html += `
        <div class="pdf-title text-black fw-bold p-2 my-4 fst-italic"
             style="font-size: 1.25rem;">
            ${title}
        </div>
    `;

    // Вопросы и ответы
    questions.forEach((question, qIndex) => {
        let answersHTML = '';
        if (Array.isArray(question.answers)) {
            question.answers.forEach((answer, aIndex) => {
                answersHTML += `
                    <div class="ms-3 mb-1">
                        <span class="fw-normal">${letters[aIndex]}. ${answer.text}</span>
                    </div>
                `;
            });
        }

        html += `
            <div class="pdf-element mb-2 px-2">
                <p class="fw-bold mb-1">${question.text}</p>
                ${answersHTML}
            </div>
        `;
    });

    pdfContainer.innerHTML += html;
}

function handleTrueorfalsePDF(payloads, is_colorful = true) {
    const { id, title, statements } = payloads;
    if (!Array.isArray(statements)) return;

    let html = `
        <div class="pdf-title text-dark fw-bold p-2 my-4 fst-italic"
             style="font-size: 1.25rem;">
            ${title}
        </div>
    `;

    statements.forEach((statement, index) => {
        html += `
            <div class="pdf-element mb-2 px-2">
                <p class="fw-bold mb-1">${index + 1}. ${statement.text}</p>
                <div class="ms-3">
                    ○ Правда &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ○ Ложь
                </div>
            </div>
        `;
    });

    pdfContainer.innerHTML += html;
}

function handleUnscramblePDF(payloads, is_colorful = true) {
    const { title, words } = payloads;
    let html = '';

    // 1) Заголовок
    html += `
        <div class="pdf-title fw-bold fst-italic p-2 my-4 text-dark" style="font-size: 1.25rem;">
            ${title}
        </div>
    `;

    // 2) Идём группами по 2 слова
    for (let i = 0; i < words.length; i += 2) {
        const pair = words.slice(i, i + 2);

        html += `<div class="row mb-3 pdf-element">`;

        pair.forEach(element => {
            const word = element.word;
            const shuffled = Array.isArray(element.shuffled_word)
                ? element.shuffled_word
                : String(element.shuffled_word).split('');
            const hint = element.hint;

            // a) слоты
            let slots = '';
            for (let k = 0; k < word.length; k++) {
                slots += `
                    <span class="d-inline-block mx-1"
                          style="width: 2ch; border-bottom: 1px solid #000; text-align: center; line-height: 2;">
                        &nbsp;
                    </span>
                `;
            }

            // b) буквы
            const lettersHTML = shuffled.map(l => `
                <span class="d-inline-block mx-1 fw-bold">
                    ${l === ' ' ? '␣' : l}
                </span>
            `).join('');

            // c) подсказка
            const hintHTML = hint
                ? `<div class="text-muted fst-italic mt-2">Подсказка: ${hint}</div>`
                : '';

            html += `
                <div class="col-6">
                    <div class="mb-2">${slots}</div>
                    <div class="mb-2">${lettersHTML}</div>
                    ${hintHTML}
                </div>
            `;
        });

        // Если одно слово — добавляем пустую колонку
        if (pair.length === 1) {
            html += `<div class="col-6 pdf-element" style="min-height: 30px;"></div>`;
        }

        html += `</div>`;
    }

    // 3) Вставляем в контейнер
    pdfContainer.innerHTML += html;
}

function handleMakeasentencePDF(payloads, is_colorful = true) {
    const { title, sentences } = payloads;

    let html = `
        <!-- Заголовок -->
        <div class="pdf-title fw-bold fst-italic p-2 my-4 text-dark"
            style="font-size: 1.25rem;">
            ${title}
        </div>
    `;

    // Проходимся по каждому предложению
    (sentences || []).forEach((sentence, index) => {
        const correctWords = sentence.correct.split(" ");
        const shuffledWords = sentence.shuffled.split(" ");

        const lineFieldsHTML = correctWords.map(() => `
            <span class="d-inline-block mx-1"
                  style="
                      display: inline-block;
                      min-width: 140px;
                      border-bottom: 1px solid #000;
                      height: 1.2em;
                      vertical-align: bottom;
                      line-height: 3;">
            </span>
        `).join("");

        const wordListHTML = shuffledWords.map(word => {
            return `
                <li class="badge ${is_colorful ? 'bg-secondary text-white' : 'bg-light text-dark'}">
                    ${word}
                </li>
            `;
        }).join("");

        html += `
            <div class="pdf-element mb-3">
                <div class="mb-2">${lineFieldsHTML}</div>
                <ul class="list-unstyled d-flex flex-wrap gap-2">
                    ${wordListHTML}
                </ul>
            </div>
        `;
    });

    pdfContainer.innerHTML += html;
}

function handleEssayPDF(payloads, is_colorful = true) {
    const { title, conditions } = payloads;

    let html = `
        <!-- Заголовок -->
        <div class="pdf-title fw-bold fst-italic my-4 p-2 text-dark"
            style="font-size: 1.25rem;">
            ${title}
        </div>
    `;

    // Условия оценивания (если есть)
    if (conditions && Array.isArray(conditions) && conditions.length) {
        html += `<ul class="list-unstyled mb-2 pdf-element">`;

        conditions.forEach(condition => {
            const max = Number(condition.points);
            if (condition.text) {
                html += `
                    <li class="mb-2 d-flex justify-content-between">
                        <span>${condition.text}</span>
                        <span class="badge bg-primary-subtle text-dark">${max} ${getBallWord(max)}</span>
                    </li>
                `;
            }
        });

        html += `</ul>`;
    }

    // Поле для написания эссе
    html += `
        <div class="border rounded p-3 mb-3 pdf-element" style="min-height: 300px;"></div>
    `;

    pdfContainer.innerHTML += html;
}

function handleImagePDF(payloads, is_colorful = true) {
    const { title, image_url } = payloads;

    const html = `
        <!-- Заголовок -->
        <div class="pdf-title ${is_colorful ? 'bg-primary text-white rounded shadow' : 'text-black'} fw-bold p-2 my-4 fst-italic"
            style="${is_colorful ? '' : 'font-size: 1.25rem;'}">
            ${title}
        </div>

        <!-- Изображение -->
        <div class="text-center mb-2 pdf-element">
            <img src="${image_url}" alt="image task" class="img-fluid rounded" style="max-width: 100%; height: auto;">
        </div>
    `;

    pdfContainer.innerHTML += html;
}

function handleLabelimagesPDF(payloads, is_colorful = true) {
    const { title, images, labels } = payloads;

    const badgeListHTML = `
        <div class="fw-semibold fst-italic p-2 text-dark" style="font-size: 1.25rem;">${title}</div>
        <div class="d-flex flex-wrap gap-2 mb-4">
            ${labels.map(label => `
                <span class="badge bg-primary-subtle text-primary border border-primary px-3 py-2 rounded-pill fs-6">
                    ${label}
                </span>
            `).join('')}
        </div>
    `;

    pdfContainer.innerHTML += `
        <div class="pdf-title my-4">
            ${badgeListHTML}
        </div>
    `;

    for (let i = 0; i < images.length; i += 3) {
        const rowImages = images.slice(i, i + 3).map(img => `
            <div class="col-4 text-center">
                <img src="${img.url}"
                     class="img-fluid rounded mb-2"
                     style="height: 180px; width: 180px; object-fit: cover;">
                <div style="
                    width: 180px;
                    border-bottom: 1px solid #000;
                    margin: 0 auto;
                    height: 1.5rem;
                    ">
                </div>
            </div>
        `).join('');

        pdfContainer.innerHTML += `
            <div class="pdf-element">
                <div class="row mb-2 d-flex justify-content-between">
                    ${rowImages}
                </div>
            </div>
        `;
    }
}

function handleSortintocolumnsPDF(payloads, is_colorful = true) {
    const { title, columns, labels } = payloads;

    // Генерация word-bank
    const wordBankHTML = `
        <div class="fw-bold fst-italic p-2 my-4 text-dark" style="font-size: 1.25rem;">${title}</div>
        <div class="d-flex flex-wrap gap-2 mb-4">
            ${labels.map(word => `
                <span class="badge bg-primary-subtle text-primary border border-primary px-3 py-2 rounded-pill fs-6">
                    ${word}
                </span>
            `).join('')}
        </div>
    `;

    // Генерация колонок по 2 в строку
    const columnRows = [];
    for (let i = 0; i < columns.length; i += 2) {
        const pair = columns.slice(i, i + 2);
        const colsHTML = pair.map(col => `
            <div class="col-md-6">
                <div class="border rounded-3 p-3" style="min-height: 200px;">
                    <div class="fw-bold mb-2">${col.name}</div>
                </div>
            </div>
        `).join('');
        columnRows.push(`<div class="row g-4 mb-2">${colsHTML}</div>`);
    }

    pdfContainer.innerHTML += `
        <div class="pdf-element mt-2">
            ${wordBankHTML}
        </div>
        ${columnRows.map(row => `
            <div class="pdf-element">
                ${row}
            </div>
        `).join('')}
    `;
}

function handleAudioPDF(payloads, is_colorful = true) {
    const { id, title, audio_url, transcript } = payloads;

    // Преобразуем title в безопасный ID
    const safeId = `qr-code-${title.replace(/\s+/g, '-').replace(/[^a-zA-Z0-9\-_]/g, '')}`;

    pdfContainer.innerHTML += `
        <div class="pdf-element">
            <div class="fw-bold fst-italic p-2 my-4 text-dark" style="font-size: 1.25rem;">${title} - Audio</div>
            <div id="${safeId}"></div>
        </div>
    `;

    // Извлекаем имя файла из пути
    const filename = audio_url.split('/').pop();

    // Формируем ссылку на QR
    const normalizedUrl = `https://linguaglow.ru/qr/audio/${filename}`;

    new QRCode(document.getElementById(safeId), {
        text: normalizedUrl,
        width: 256,
        height: 256
    });
}

function handleEmbeddedtaskPDF(payloads, is_colorful = true) {
    const { id, title, embed_code } = payloads;
    if (!embed_code) return;

    const safeId = `qr-code-${title.replace(/\s+/g, '-').replace(/[^a-zA-Z0-9\-_]/g, '')}`;

    // 1. Извлекаем только src из iframe
    const srcMatch = embed_code.match(/<iframe[^>]*src=["']([^"']+)["']/);
    if (!srcMatch) return;
    const src = srcMatch[1];

    // 2. Сжимаем src в компактный URI-safe формат
    const compressed = LZString.compressToEncodedURIComponent(src);

    // 3. Проверяем, что результат влезет в QR
    console.log('compressed.length =', compressed.length);
    if (compressed.length > 1000) {
        alert("К сожалению, виртуальная доска слишком большая для QR-кода и не может быть добавлена.");
        return;
    }

    // 4. Формируем URL
    const normalizedUrl = `https://linguaglow.ru/qr/iframe/lz/${compressed}`;

    // 5. Вставляем в DOM и генерируем QR
    pdfContainer.innerHTML += `
        <div class="pdf-element">
            <div class="fw-bold fst-italic p-2 my-4 text-dark" style="font-size: 1.25rem;">
                ${title} - IFrame
            </div>
            <div id="${safeId}"></div>
        </div>
    `;
    try {
        new QRCode(document.getElementById(safeId), {
            text: normalizedUrl,
            width: 256,
            height: 256
        });
    } catch (e) {
        console.error(e);
        alert("К сожалению, виртуальная доска слишком большая для QR-кода и не может быть добавлена.");
        const elements = pdfContainer.querySelectorAll(".pdf-element");
        if (elements.length > 0) {
            const last = elements[elements.length - 1];
            last.remove();
        }
    }
}






        // Контроль кнопок

function arraysEqual(existingTaskIds, selectedTaskElements) {
    const selectedIds = [...selectedTaskElements].map(el => el.id).sort();
    const existingIdsSorted = [...existingTaskIds].map(String).sort();

    if (selectedIds.length !== existingIdsSorted.length) return false;

    return existingIdsSorted.every((id, i) => id === selectedIds[i]);
}

function updateActionButtonsState() {
    const selectedTasks = getSelectedTasks(); // массив выбранных id, например ['id1', 'id2']

    // Если выбранные задачи совпадают с existingTaskIds — кнопки отключены (disabled)
    // Если отличаются — включаем кнопки (disabled = false)
    const shouldDisable = arraysEqual(existingTaskIds, selectedTasks);

    document.querySelectorAll('.panel button').forEach(btn => {
        btn.disabled = shouldDisable;
    });
}

function attachCheckboxListeners() {
    document.querySelectorAll('.select-task').forEach(checkbox => {
        checkbox.addEventListener('change', updateActionButtonsState);
    });
}


        // Отправка домашки

function sendHomework() {
    const container = document.getElementById('task-list');
    const classroomId = container.dataset.classroomId;
    const lessonId = container.dataset.lessonId;
    const sendHomeworkUrl = container.dataset.sendHomeworkUrl;

    // Собираем id отмеченных задач
    const checkedTasks = Array.from(container.querySelectorAll('input[name="tasks"]:checked'))
        .map(input => input.dataset.taskId);
    console.log(checkedTasks);

    fetch(sendHomeworkUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken,
        },
        body: JSON.stringify({
            classroom_id: classroomId,
            lesson_id: lessonId,
            task_ids: checkedTasks,
        }),
    })
    .then(resp => {
        if (!resp.ok) throw new Error('Network response was not ok');
        return resp.json();
    })
    .then(data => {
        existingTaskIds = data.created_ids;
        updateActionButtonsState();
        if (data.created_count) {
            setTimeout(() => {
                showNotification("Домашнее задание обновлено.", "success");
            }, 1000);
        } else {
            setTimeout(() => {
                showNotification("Домашнее задание удалено.", "warning");
            }, 1000);
        }
    })
    .catch(err => {
        console.error(err);
        showNotification("Не удалось изменить домашнее задание.", "danger");
    });
}

function showNotification(text, color) {
    // Проверяем, активно ли модальное окно редактора
    const editorModal = document.getElementById('taskEditorModal');
    const isEditorModalActive = editorModal && editorModal.classList.contains('show');
    let time = 3000;

    let alertContainer;

    if (isEditorModalActive && color === "warning") {
        // Если активно окно редактора, создаем контейнер внутри modal-body
        alertContainer = editorModal.querySelector('#notification-inner-container');
        if (!alertContainer) {
            alertContainer = document.createElement('div');
            alertContainer.id = 'notification-inner-container';
            alertContainer.style.position = 'absolute';
            alertContainer.style.bottom = '20px';
            alertContainer.style.left = '0';
            alertContainer.style.right = '0';
            alertContainer.style.display = 'block';
            alertContainer.style.width = '70%';
            alertContainer.classList.add('mx-auto');
            editorModal.querySelector('.modal-body').appendChild(alertContainer);
        }
        time = 1500
    } else {
        // Иначе используем стандартный контейнер в body
        alertContainer = document.getElementById('alert-container');
        if (!alertContainer) {
            alertContainer = document.createElement('div');
            alertContainer.id = 'alert-container';
            alertContainer.style.position = 'fixed';
            alertContainer.style.bottom = '20px';
            alertContainer.style.right = '20px';
            alertContainer.style.zIndex = "1050";
            document.body.appendChild(alertContainer);
        }
    }

    // Создаем элемент уведомления
    const alert = document.createElement('div');
    alert.className = `alert alert-${color} fade show`;
    alert.setAttribute('role', 'alert');
    alert.style.minWidth = '200px';
    alert.style.boxShadow = '0 4px 6px rgba(0,0,0,0.1)';
    alert.innerHTML = text;

    // Добавляем уведомление в контейнер
    alertContainer.appendChild(alert);

    // Автоматическое закрытие через 1,5-3 секунды
    setTimeout(() => {
        alert.classList.remove('show');
        alert.classList.add('fade');
        setTimeout(() => alert.remove(), 500);
    }, time);
}
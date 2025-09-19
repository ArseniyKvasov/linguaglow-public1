const mainContainer = document.getElementById('main-container');
const contextWindows = document.querySelectorAll(".context-window");
const lessonId = mainContainer.dataset.lessonId;
const courseId = mainContainer.dataset.courseId;
const userRole = mainContainer.dataset.userRole;
const mode = mainContainer.dataset.mode;
const selectedMatchup = {};
const taskList = document.getElementById('task-list');
const studentOptions = document.querySelectorAll('.student-option');
const lessonName = mainContainer.dataset.lessonName;
const userId = mainContainer.dataset.userId;
const classroomId = mainContainer.dataset.classroomId;

let studentId = '';
if (userRole === 'teacher' && mode === 'classroom' && studentOptions[0]) {
    studentId = studentOptions[0].dataset.studentId;
}






        // Отображение заданий

function createIconButton(title, iconClass, textColor, marginClass = "") {
    const button = document.createElement('button');
    button.className = `btn btn-link p-0 ${marginClass}`;
    button.title = title;

    const icon = document.createElement('i');
    icon.className = `bi ${iconClass} ${textColor}`;

    button.appendChild(icon);
    return button;
}

function handleWordlist(task_id, payloads) {
    const { id, title, words } = payloads;
    const taskContainer = document.getElementById(`${id}`);

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header d-flex align-items-center justify-content-between bg-primary rounded text-white">
            <span class="task-title fw-bold">${title}</span>
        </div>

        <!-- Список слов -->
        <div class="card-body">
            <div class="words-list">
                ${words.map(({ word, translation }) => `
                    <div class="word-item mb-2 d-flex align-items-center justify-content-between position-relative p-2 border rounded">
                        <div class="me-3">
                            <span class="fw-bold me-1">${clearText(word)}</span> - <span class="ms-1">${clearText(translation)}</span>
                        </div>
                        <button class="btn-mark-word btn btn-link text-primary" title="Отметить незнакомое слово">
                            <i class="bi bi-square"></i>
                        </button>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
    if (userRole === 'teacher') {
        organizeActionButtons(taskContainer, { edit: true, mark: true, restart: false, deleteListener: true, summon: true }, 'light');
    }

    const markButtons = taskContainer.querySelectorAll('.btn-mark-word');
    markButtons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();

            const wordItem = btn.closest('.word-item');
            if (!wordItem) return;

            const allWordItems = Array.from(taskContainer.querySelectorAll('.word-item'));
            const word_index = allWordItems.indexOf(wordItem);
            if (word_index === -1) return;

            // Проверяем текущее состояние выделения (уже выделено или нет)
            const isSelected = wordItem.classList.contains('bg-light');

            // Новый статус — переключаем
            const select = !isSelected;

            if (mode === "classroom") {
                sendMessage('task-answer', task_id, { answer: { word_index, select } }, 'student');
            }

            // Отправляем ответ с указанием выделять или снимать выделение
            submitAnswer(task_id, { word_index, select }, "plain");

            // Обновляем визуально
            fillWordlistAnswer(task_id, { word_index, select });
        });
    });

    displayUserStats(task_id);
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
                        ${clearText(word)}
                    </button>
                </div>
                <div class="col-6">
                    <button class="match-btn btn btn-outline-secondary fs-6 fw-bold w-100 h-100" data-translation="${escapeHtml(translation)}">
                        ${clearText(translation)}
                    </button>
                </div>
            </div>
        `;
    }).join('');

    // Сборка HTML-карточки
    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header bg-white d-flex align-items-center justify-content-between">
            <span class="task-title text-dark me-2 fw-bold">${title}</span>
        </div>

        <!-- Тело карточки -->
        <div class="card-body">
            <div class="container">
                ${rowsHTML}
            </div>
        </div>
    `;
    selectedMatchup[task_id] = {
        word: null,
        translation: null
    };

    if (userRole === 'teacher') {
        organizeActionButtons(taskContainer, { edit: true, mark: false, restart: true, deleteListener: true, summon: true });
    }

    const buttons = taskContainer.querySelectorAll('.match-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', async () => {
            const word = btn.dataset.word;
            const translation = btn.dataset.translation;

            // Определяем, к какой колонке относится кнопка
            const isWordButton = !!word;
            const isTranslationButton = !!translation;

            // Если кликнули по слову
            if (isWordButton) {
                // Сбрасываем выделение у всех кнопок в колонке "Слова"
                taskContainer.querySelectorAll('[data-word]').forEach(button => {
                    button.classList.remove('btn-primary');
                    button.classList.add('btn-outline-secondary');
                });

                // Выделяем текущую кнопку
                btn.classList.add('btn-primary');
                btn.classList.remove('btn-outline-secondary');

                // Сохраняем выбранное слово
                selectedMatchup[task_id].word = word;
            }

            // Если кликнули по переводу
            if (isTranslationButton) {
                // Сбрасываем выделение у всех кнопок в колонке "Переводы"
                taskContainer.querySelectorAll('[data-translation]').forEach(button => {
                    button.classList.remove('btn-primary');
                    button.classList.add('btn-outline-secondary');
                });

                // Выделяем текущую кнопку
                btn.classList.add('btn-primary');
                btn.classList.remove('btn-outline-secondary');

                // Сохраняем выбранный перевод
                selectedMatchup[task_id].translation = translation;
            }
            // Если выбрано и слово, и перевод — отправляем
            if (selectedMatchup[task_id].word && selectedMatchup[task_id].translation) {
                const answer = {
                    'card 1': selectedMatchup[task_id].word,
                    'card 2': selectedMatchup[task_id].translation
                };

                const isCorrect = await submitAnswer(task_id, answer);

                fillMatchupthewordsAnswer(task_id, answer, isCorrect);

                // Сбрасываем выбор после отправки ответа
                selectedMatchup[task_id] = { word: null, translation: null };
                taskContainer.querySelectorAll('.match-btn').forEach(button => {
                    button.classList.remove('btn-primary');
                    button.classList.add('btn-outline-secondary');
                });
            }
        });
    });

    displayUserStats(task_id);
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
                    ${correctTooltipContainer(answer)}
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
            blanksHTML += `<span class="text-part">${clearText(part)}</span>`;
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
                            ${clearText(word)}
                        </li>
                    `).join('')}
                </ul>
            </div>
        `;
    }

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header bg-white d-flex align-items-center justify-content-between">
            <span class="task-title text-dark me-2 fw-bold">${title}</span>
        </div>

        <!-- Тело карточки -->
        <div class="card-body rounded-bottom">
            ${wordListHTML}
            <div class="blanks-text lh-base">
                ${blanksHTML}
            </div>
        </div>
    `;
    if (userRole === 'teacher') {
        organizeActionButtons(taskContainer, { edit: true, mark: false, restart: true, deleteListener: true, summon: true });
    }
    // Добавляем обработчики событий для показа подсказки
    const blankInputs = taskContainer.querySelectorAll('.blank-input');

    blankInputs.forEach(input => {
        const tooltip = input.parentElement.querySelector('.correct-tooltip');
        // Показываем подсказку при наведении и фокусе
        input.addEventListener('mouseenter', () => {
            if (tooltip) tooltip.style.display = 'block';
        });
        input.addEventListener('focus', () => {
            if (tooltip) tooltip.style.display = 'block';
        });
        // Скрываем подсказку при уходе мыши и потере фокуса
        input.addEventListener('mouseleave', () => {
            if (tooltip) tooltip.style.display = 'none';
        });
        input.addEventListener('blur', () => {
            if (tooltip) tooltip.style.display = 'none';
        });
    });

    // Обработчик отправки ответа
    blankInputs.forEach(input => {
        input.addEventListener('change', async () => {
            if (!input.value.trim()) return;
            const taskId = input.dataset.taskId;
            const blankIndex = parseInt(input.dataset.blankId, 10);
            const userAnswer = input.value.trim();

            if (!userAnswer) return;

            const answerPayload = {
                index: blankIndex,
                answer: userAnswer
            };

            const isCorrect = await submitAnswer(taskId, answerPayload);

            fillFillintheblanksAnswer(taskId, answerPayload, isCorrect);
        });
    });

    displayUserStats(task_id);
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

function handleNote(task_id, payloads) {
    const { id, title, content } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    const rendered = renderContent(content);
    console.log(rendered);

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header d-flex align-items-center justify-content-between bg-success rounded">
            <span class="task-title text-white me-2 fw-bold">${title}</span>
        </div>

        <!-- Тело карточки -->
        <div class="card-body">
            <div class="article-content text-part">
                ${rendered}
            </div>
        </div>
    `;

    if (userRole === "teacher") {
        organizeActionButtons(
            taskContainer,
            { edit: true, mark: true, restart: false, deleteListener: true, summon: true },
            "light"
        );
    }
}

function handleArticle(task_id, payloads) {
    const { id, title, content } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    const rendered = renderContent(content);

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header d-flex align-items-center justify-content-between bg-success rounded">
            <span class="task-title text-white me-2 fw-bold">${title}</span>
        </div>

        <!-- Тело карточки -->
        <div class="card-body rounded-bottom">
            <div class="article-content text-part">
                ${rendered}
            </div>
        </div>
    `;

    if (userRole === "teacher") {
        organizeActionButtons(
            taskContainer,
            { edit: true, mark: true, restart: false, deleteListener: true, summon: true },
            "light"
        );
    }
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
                                ${clearText(answer.text)}
                            </label>
                        </div>
                    `;
                });
            }
            questionsHTML += `
                <div class="question-item mb-4 p-3 rounded border border-light" data-question-id="${qIndex}">
                    <p class="fw-bold mb-3">${clearText(question.text)}</p>
                    <div class="answers-list">
                        ${answersHTML}
                    </div>
                </div>
            `;
        });
    }

    // Итоговая разметка
    taskContainer.innerHTML = `
        <div class="card-header bg-white d-flex align-items-center justify-content-between">
            <span class="task-title text-dark me-2 fw-bold">${title}</span>
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

    if (userRole === 'teacher') {
        organizeActionButtons(taskContainer, { edit: true, mark: false, restart: true, deleteListener: true, summon: true });
    }

    const form = taskContainer.querySelector('.test-form');
    const checkBtn = taskContainer.querySelector('.task-check');

    if (form && checkBtn) {
        // При изменении любого радио
        form.addEventListener('change', (e) => {
            const input = e.target;
            if (input.type === 'radio') {
                const qIndex = parseInt(input.dataset.questionId);
                const aIndex = parseInt(input.dataset.answerId);

                if (mode === "classroom") {
                    sendMessage('task-answer', task_id, {'answer': { qIndex, aIndex }}, 'student');
                }

                // Отправляем один ответ
                fillTestAnswer(task_id, { qIndex, aIndex });
                submitAnswer(task_id, { qIndex, aIndex, flag: "radio" }, "plain");
            }
        });

        // Проверка всех ответов
        checkBtn.addEventListener('click', () => {
            if (mode === "classroom") {
                sendMessage("test-check", task_id, '', 'student');
                checkTestAnswers(task_id);
            } else if (mode === "public" || mode === "generation") {
                checkFrontendTestAnswers(task_id);
            } else {
                checkTestAnswers(task_id);
            }
            checkBtn.disabled = true;
        });
    }

    displayUserStats(task_id);
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
                            <span class="fw-bold">${clearText(statement.text)}</span>
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
        <div class="card-header d-flex align-items-center justify-content-between bg-white">
            <span class="task-title text-dark me-2 fw-bold">${title}</span>
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

    if (userRole === 'teacher') {
        organizeActionButtons(taskContainer, { edit: true, mark: false, restart: true, deleteListener: true, summon: true });
    }

    const checkBtn = taskContainer.querySelector('.task-check');

    taskContainer.addEventListener('change', (e) => {
        if (e.target.type === 'radio') {
            const index = e.target.dataset.statementIndex;
            const value = e.target.value;

            if (mode === "classroom") {
                sendMessage('task-answer', task_id, {'answer': { index, value }}, 'student');
            }
            fillTrueorfalseAnswer(task_id, { index, value });
            submitAnswer(task_id, { index, value }, "plain")

            checkAllAnswers(taskContainer);
        }
    });

    checkBtn.addEventListener('click', () => {
        // Вызов проверки
        if (mode === "classroom") {
            sendMessage("truefalse-check", task_id, '', 'student');
            checkTrueFalseAnswers(task_id);
        } else if (mode === "public" || mode === "generation") {
            checkFrontendTrueFalseAnswers(task_id);
        } else {
            checkTrueFalseAnswers(task_id);
        }
        checkBtn.disabled = true;
    });

    displayUserStats(task_id);
}

function handleUnscramble(task_id, payloads) {
    const { id, title, words } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    let wordsHTML = "";
    if (Array.isArray(words)) {
        words.forEach((element) => {
            // Используем исходное слово напрямую для data-атрибута
            const wordData = clearText(element.word);

            // Формируем поля для букв: для каждой буквы исходного слова
            let wordFieldsHTML = "";
            for (let i = 0; i < wordData.length; i++) {
                wordFieldsHTML += `
                    <div class="position-relative d-inline-block">
                        <div class="border border-primary border-2 rounded text-center fw-bold fs-5 empty-slot position-relative"
                             style="width: 40px; height: 40px; line-height: 40px;"
                             data-letter-id="${i}" data-correct-letter="${escapeHtml(wordData[i])}">
                        </div>
                        ${correctTooltipContainer(wordData[i])}
                    </div>
                `;
            }

            // Формируем кнопки с буквами: перебираем каждую букву перемешанного слова
            let letterButtonsHTML = "";
            let shuffledLetters = [];
            if (typeof clearText(element.shuffled_word) === "string") {
                shuffledLetters = clearText(element.shuffled_word).split('');
            } else if (Array.isArray(element.shuffled_word)) {
                shuffledLetters = clearText(element.shuffled_word);
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
                        <i class="bi bi-lightbulb"></i> Подсказка: ${clearText(element.hint)}
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
        <div class="card-header bg-white d-flex align-items-center justify-content-between">
            <span class="task-title text-dark me-2 fw-bold">${title}</span>
        </div>

        <!-- Тело карточки -->
        <div class="card-body rounded-bottom">
            ${wordsHTML}
        </div>
    `;

    if (userRole === 'teacher') {
        organizeActionButtons(taskContainer, { edit: true, mark: false, restart: true, deleteListener: true, summon: true });
    }
    // Добавляем обработчики событий для пустых слотов
    const emptySlots = taskContainer.querySelectorAll('.empty-slot');
    emptySlots.forEach(slot => {
        const tooltip = slot.parentElement.querySelector('.correct-tooltip');
        slot.addEventListener('mouseenter', () => {
            if (tooltip) tooltip.style.display = 'block';
        });
        slot.addEventListener('mouseleave', () => {
            if (tooltip) tooltip.style.display = 'none';
        });
        // Делаем слот фокусируемым, если нужно
        slot.setAttribute('tabindex', 0);
        slot.addEventListener('focus', () => {
            if (tooltip) tooltip.style.display = 'block';
        });
        slot.addEventListener('blur', () => {
            if (tooltip) tooltip.style.display = 'none';
        });
    });

    // Обработчик ввода буквы
    const letterButtons = taskContainer.querySelectorAll('.letter-button');
    letterButtons.forEach((button, letterIndex) => {
        button.addEventListener('click', async () => {
            const wordContainer = button.closest('.word-container');
            const slots = wordContainer.querySelectorAll('.empty-slot:not(.filled)');
            if (!slots.length || button.disabled) return;

            const currentSlot = slots[0];
            const wordIndex = Array.from(taskContainer.querySelectorAll('.word-container')).indexOf(wordContainer);
            const gapIndex = parseInt(currentSlot.dataset.letterId);
            const letter = button.dataset.letter;
            const letterId = parseInt(button.dataset.letterId);

            // Временно заполняем слот и блокируем кнопку
            currentSlot.classList.add('filled'); // добавим только filled, без цвета
            button.classList.add('disabled');

            setTimeout(() => {
                button.classList.remove('disabled');
            }, 1000);

            const answer = {
                word_index: wordIndex,
                gap_index: gapIndex,
                letter_index: letterId,
            };

            const isCorrect = await submitAnswer(task_id, answer);

            fillUnscrambleAnswer(task_id, answer, isCorrect, true);
        });
    });


    displayUserStats(task_id);
}

function handleMakeasentence(taskId, payloads) {
    console.log("calles");
    const { id, title, sentences } = payloads;
    console.log(title, sentences);
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    const renderSentence = (sentence) => {
        const correctWords = clearText(sentence.correct).split(" ");
        const shuffledWords = clearText(sentence.shuffled).split(" ");

        const fieldsHTML = correctWords.map((word, index) => `
            <div class="position-relative d-inline-block">
                <div class="border border-primary border-2 rounded text-center fw-bold fs-5 empty-slot position-relative"
                     style="min-width: 70px; height: 30px; line-height: 30px;"
                     data-word-position="${index}" data-correct-answer="${escapeHtml(word)}"></div>
                ${correctTooltipContainer(word)}
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
        <div class="card-header bg-white d-flex align-items-center justify-content-between">
            <span class="task-title text-dark me-2 fw-bold">${title}</span>
        </div>
        <div class="card-body">
            ${(sentences || []).map(renderSentence).join("")}
        </div>
    `;

    if (userRole === 'teacher') {
        organizeActionButtons(taskContainer, {
            edit: true, mark: false, restart: true, deleteListener: true, summon: true
        });
    }

    taskContainer.querySelectorAll('.empty-slot').forEach(slot => {
        const tooltip = slot.parentElement.querySelector('.correct-tooltip');
        slot.setAttribute('tabindex', 0);

        ['mouseenter', 'focus'].forEach(evt => slot.addEventListener(evt, () => {
            if (tooltip) tooltip.style.display = 'block';
        }));
        ['mouseleave', 'blur'].forEach(evt => slot.addEventListener(evt, () => {
            if (tooltip) tooltip.style.display = 'none';
        }));
    });

    taskContainer.querySelectorAll('.word-button').forEach((button) => {
        button.addEventListener('click', async () => {
            const sentenceContainer = button.closest('.sentence-container');
            const slots = sentenceContainer.querySelectorAll('.empty-slot:not(.filled)');
            if (!slots.length) return;

            const currentSlot = slots[0];
            const gap_index = +currentSlot.dataset.wordPosition;
            const sentenceIndex = Array.from(taskContainer.querySelectorAll('.sentence-container')).indexOf(sentenceContainer);
            const word_index = Array.from(sentenceContainer.querySelectorAll('.word-button')).indexOf(button);

            // Временно заполняем слот и блокируем кнопку
            currentSlot.classList.add('filled'); // добавим только filled, без цвета
            button.classList.add('disabled');

            setTimeout(() => {
                button.classList.remove('disabled');
            }, 1000);

            const answer = { sentenceIndex, gap_index, word_index };
            const isCorrect = await submitAnswer(taskId, answer);
            fillMakeasentenceAnswer(taskId, answer, isCorrect, true);
        });
    });

    displayUserStats(taskId);
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
                                <span class="d-block fw-semibold">${clearText(criteria.text)}</span>
                                <small class="text-muted">Критерий оценки</small>
                            </label>
                            <div class="d-flex align-items-center ms-3">
                                <span class="badge bg-primary-subtle text-primary border border-primary rounded-pill px-3 py-2">
                                    ${clearText(criteria.points)} ${getBallWord(criteria.points)}
                                </span>
                            </div>
                        </div>
                    </div>
                `;
                gradingFieldsHTML += `
                    <div class="mb-3">
                        <label class="form-label fw-semibold">${clearText(criteria.text)}</label>
                        <input type="number" min="0" max="${max}" data-index="${index}" class="form-control grade-input" placeholder="Оценка (0–${max})">
                    </div>
                `;
            }
        });
    }

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header d-flex align-items-center justify-content-between bg-white">
            <span class="task-title text-black me-2 fw-bold">${title}</span>
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

    // Дополнительная логика
    const editor = taskContainer.querySelector(`#essay-editor-${task_id}`);
    enhanceTextarea(editor);
    editor.innerHTML = '';
    editor.addEventListener('input', () => updateWordCount(task_id));

    const submitBtn = taskContainer.querySelector('.essay-submit-btn');
    submitBtn?.addEventListener('click', () => {
        const text = editor.innerHTML;
        submitAnswer(task_id, text);
    });

    if (userRole === 'teacher') {
        organizeActionButtons(taskContainer, { edit: true, mark: false, restart: true, deleteListener: true, summon: true });
    }

    displayUserStats(task_id);
}

function handleImage(task_id, payloads) {
    const { id, title, image_url } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header d-flex align-items-center justify-content-between bg-primary rounded">
            <span class="task-title text-light text-start fw-bold">${title}</span>
        </div>

        <!-- Тело карточки -->
        <div class="card-body d-flex justify-content-center">
            <img src="${image_url}" alt="" class="img-fluid rounded">
        </div>
    `;

    if (userRole === 'teacher') {
        organizeActionButtons(taskContainer, { edit: true, mark: false, restart: false, deleteListener: true, summon: true }, 'light');
    }
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
                        ${clearText(label)}
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
                            ${correctTooltipContainer(clearText(correctLabel))}
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
        <div class="card-header bg-white d-flex align-items-center justify-content-between">
            <span class="task-title text-dark me-2 fw-bold">${title}</span>
        </div>
        <div class="card-body rounded-bottom">
            ${badgeListHTML}
            <div class="row g-4">
                ${imagesHTML}
            </div>
        </div>
    `;

    if (userRole === 'teacher') {
        organizeActionButtons(taskContainer, { edit: true, mark: false, restart: true, deleteListener: true, summon: true });
    }

    // Подсказки и обработка ввода
    const labelInputs = taskContainer.querySelectorAll('.label-image');
    labelInputs.forEach(input => {
        const tooltip = input.parentElement.querySelector('.correct-tooltip');
        input.addEventListener('mouseenter', () => tooltip && (tooltip.style.display = 'block'));
        input.addEventListener('focus', () => tooltip && (tooltip.style.display = 'block'));
        input.addEventListener('mouseleave', () => tooltip && (tooltip.style.display = 'none'));
        input.addEventListener('blur', () => tooltip && (tooltip.style.display = 'none'));

        input.addEventListener('change', async () => {
            if (!input.value.trim()) return;
            const label = input.value.trim();
            const imageIndex = parseInt(input.dataset.imageIndex);
            const answer = {
                image_index: imageIndex,
                label: label
            };

            const isCorrect = await submitAnswer(task_id, answer);
            fillLabelimagesAnswer(task_id, answer, isCorrect);
        });
    });

    displayUserStats(task_id);
}

function handleSortintocolumns(task_id, payloads) {
    const { id, title, columns, labels } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    let wordBankHTML = labels.map(word => `
        <span class="badge bg-primary draggable-word fs-6" draggable="true" data-word="${escapeHtml(word)}">
            ${clearText(word)}
        </span>
    `).join('');

    let columnsHTML = "";
    columns.forEach(col => {
        const correctText = col.words.join(", ");
        columnsHTML += `
            <div class="col-12 col-md-6 col-lg-4 col-xl-3">
                <div class="card h-100 column-dropzone" data-column="${escapeHtml(col.name)}">
                    <div class="card-header bg-white text-center fw-bold">
                        ${clearText(col.name)}
                    </div>
                    <div class="card-body drop-area p-3 position-relative">
                        ${correctTooltipContainer(clearText(correctText))}
                        <div class="d-flex flex-column gap-2 min-vh-25 overflow-y-auto text-center"></div>
                    </div>
                </div>
            </div>
        `;
    });

    taskContainer.innerHTML = `
        <div class="card-header bg-white d-flex align-items-center justify-content-between">
            <span class="task-title text-dark me-2 fw-bold">${title}</span>
        </div>
        <div class="card-body position-relative">
            <div class="sticky-word-bank">
                <div class="d-flex flex-wrap gap-2 mb-3 word-bank">${wordBankHTML}</div>
            </div>
            <div class="row g-3 mt-3 sortable-columns d-flex justify-content-center">${columnsHTML}</div>
        </div>
    `;

    if (userRole === 'teacher') {
        organizeActionButtons(taskContainer, { edit: true, mark: false, restart: true, deleteListener: true, summon: true });
    }

    let draggedElement = null;

    const dropAreas = taskContainer.querySelectorAll('.drop-area');
    dropAreas.forEach(dropArea => {
        const tooltip = dropArea.querySelector('.correct-tooltip');
        const innerZone = dropArea.querySelector('.d-flex');
        const columnName = dropArea.closest('.column-dropzone')?.dataset.column;

        dropArea.addEventListener('mouseenter', () => tooltip && (tooltip.style.display = 'block'));
        dropArea.addEventListener('mouseleave', () => tooltip && (tooltip.style.display = 'none'));
        dropArea.addEventListener('focus', () => tooltip && (tooltip.style.display = 'block'));
        dropArea.addEventListener('blur', () => tooltip && (tooltip.style.display = 'none'));
        dropArea.setAttribute('tabindex', 0);

        dropArea.addEventListener('dragover', e => e.preventDefault());

        dropArea.addEventListener('drop', async e => {
            e.preventDefault();
            const word = e.dataTransfer.getData('text/plain');
            if (!draggedElement) {
                showNotification("Произошла ошибка. Ваши ответы не будут сохранены.", "danger");
                return;
            }

            const clone = draggedElement.cloneNode(true);
            clone.draggable = false;
            innerZone.appendChild(clone);
            draggedElement.style.display = 'none';

            const answer = { column_name: columnName, word };
            const isCorrect = await submitAnswer(task_id, answer);

            fillSortintocolumnsAnswer(task_id, answer, isCorrect);
        });
    });

    const wordElements = taskContainer.querySelectorAll('.draggable-word');
    wordElements.forEach(wordEl => {
        wordEl.addEventListener('dragstart', e => {
            e.dataTransfer.setData('text/plain', wordEl.dataset.word);
            draggedElement = wordEl;
        });
    });

    displayUserStats(task_id);
}

function handleAudio(task_id, payloads) {
    const { id, title, audio_url, transcript } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    taskContainer.innerHTML = `
        <div class="card-header bg-primary rounded d-flex align-items-center justify-content-between">
            <span class="task-title text-light me-2 fw-bold">${title}</span>
        </div>
        <div class="card-body p-4 border-0 rounded-bottom">
            <div class="audio-player-modern">
                <audio preload="metadata" class="audio-element">
                    <source src="${audio_url}" type="audio/mpeg">
                    Ваш браузер не поддерживает аудио элемент.
                </audio>
            </div>
            ${transcript && userRole === 'teacher' ? `
                <button class="btn border-0 text-primary fw-bold mx-auto mt-3" style="display: block;" id="show-transcript-btn">
                    Показать скрипт
                </button>
                <div id="transcript-container" class="alert alert-warning p-3 border rounded-3 position-relative mt-3" style="display: none;">
                    ${transcript}
                </div>
            ` : ''}
        </div>
    `;

    if (userRole === 'teacher') {
        organizeActionButtons(taskContainer, {
            edit: true,
            mark: true,
            restart: false,
            deleteListener: true,
            summon: true
        }, 'light');

        const showTranscriptBtn = taskContainer.querySelector('#show-transcript-btn');
        const transcriptContainer = taskContainer.querySelector('#transcript-container');

        if (showTranscriptBtn && transcriptContainer) {
            showTranscriptBtn.addEventListener('click', () => {
                const isVisible = transcriptContainer.style.display === 'block';
                transcriptContainer.style.display = isVisible ? 'none' : 'block';
                showTranscriptBtn.textContent = isVisible ? 'Показать скрипт' : 'Скрыть скрипт';
            });
        }
    }

    const audioElement = taskContainer.querySelector('.audio-element');
    return setupModernAudioPlayer(audioElement);
}

function handleEmbeddedtask(task_id, payloads) {
    const { id, title, embed_code } = payloads;
    const taskContainer = document.getElementById(id);
    if (!taskContainer) return;

    const safeEmbed = checkEmbed(embed_code); // безопасный iframe или null
    console.log(safeEmbed);

    // Экранируем embed_code, если всё-таки передаём его в onclick
    const escapedEmbedCode = embed_code.replaceAll('"', '&quot;');

    taskContainer.innerHTML = `
        <!-- Заголовок -->
        <div class="card-header bg-white d-flex align-items-center justify-content-between">
            <span class="task-title text-dark me-2 fw-bold">${title}</span>
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

    if (userRole === 'teacher') {
        organizeActionButtons(taskContainer, { edit: true, mark: false, restart: false, deleteListener: true, summon: true });
    }
}

const taskSelectedPages = {};

async function handlePdf(taskId, payloads) {
    const { id, title, pdf_url } = payloads;
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer || !pdf_url) return;

    // Инициализация контейнера
    taskContainer.innerHTML = `
        <div class="card-header bg-primary rounded d-flex justify-content-between align-items-center">
            <span class="task-title text-light fw-bold">${title}</span>
        </div>
        <div class="card-body p-0 position-relative" style="height: 80vh; min-height: 300px; width: 100%;">
        </div>
    `;
    const cardBody = taskContainer.querySelector('.card-body');

    // Стили адаптива
    const style = document.createElement('style');
    style.textContent = `
        .pdf-panel { flex-wrap: wrap; overflow-x: auto; }
        .mode-btn, .action-btn { border: none; background: none; font-size: 1.2rem; margin: 0 8px; cursor: pointer; color: #666; }
        .mode-btn.active, .action-btn.active { color: #007bff; }
        .selected-pages-container { display: flex; gap: 5px; margin-right: 10px; }
        .page-badge {
            display: flex;
            align-items: center;
            background-color: #e9ecef;
            padding: 3px 8px;
            border-radius: 10px;
            font-size: 0.85rem;
            cursor: pointer;
            transition: background-color 0.2s;
        }
        .page-badge:hover { background-color: #d1e7ff; }
        .badge-remove {
            margin-left: 5px;
            cursor: pointer;
            font-size: 1.1rem;
            line-height: 1;
        }
        #previewPdfContainer {
            height: 100%;
            border: 1px solid #dee2e6;
            border-radius: 5px;
        }
    `;
    document.head.appendChild(style);

    // Панель управления
    const panel = document.createElement('div');
    panel.className = 'pdf-panel bg-light d-flex align-items-center p-2 rounded my-2';
    panel.innerHTML = `
        <button id="prev-page" class="btn btn-sm btn-outline-secondary mx-1" title="Назад">←</button>
        <button id="next-page" class="btn btn-sm btn-outline-secondary mx-1" title="Вперед">→</button>
        <span class="mx-2">Стр.:</span>
        <input id="page-input" type="number" min="1" style="width: 60px;" class="form-control form-control-sm mx-1" value="1">
        <span id="page-count" class="mx-1"></span>
        <div class="ms-auto d-flex align-items-center">
            ${userRole === 'teacher' && mode === 'generation' ? `
                <div id="selected-pages" class="selected-pages-container"></div>
                <button id="mark-page" class="action-btn" title="Отметить страницу">
                    <i id="mark-icon" class="bi"></i>
                </button>
                <button 
                    id="preview-selected" 
                    class="action-btn" 
                    title="Посмотреть выбранные страницы" 
                    style="display:none;">
                    <i class="bi bi-eye"></i>
                </button>
            ` : ''}
            ${userRole === 'teacher' && mode === 'classroom' ? `
                <button id="preview-mode" class="action-btn" title="Показать эту страницу"><i class="bi bi-broadcast"></i></button>
            ` : ''}
        </div>
    `;
    cardBody.append(panel);

    // Контейнер просмотра
    const viewer = document.createElement('div');
    viewer.className = 'pdf-viewer d-flex justify-content-start align-items-start overflow-auto rounded';
    viewer.style.width = '100%';
    viewer.style.height = 'calc(100% - 56px)';
    viewer.style.position = 'relative';
    cardBody.append(viewer);

    // Панель элементы
    const prevBtn = panel.querySelector('#prev-page');
    const nextBtn = panel.querySelector('#next-page');
    const pageInput = panel.querySelector('#page-input');
    const pageCountLabel = panel.querySelector('#page-count');
    const previewBtn = panel.querySelector('#preview-mode');
    const previewSelectedBtn = panel.querySelector('#preview-selected');
    const markBtn = panel.querySelector('#mark-page');
    const markIcon = markBtn ? markBtn.querySelector('#mark-icon') : null;
    const selectedPagesContainer = panel.querySelector('#selected-pages');

    let pdf, totalPages = 0, scale = 1, currentPage = 1;
    let isRendering = false;
    let isDragging = false, dragStart = {};
    let selectedPages = new Set();

    // Функция обновления иконки отметки
    function updateMarkIcon(taskId, currentPage) {
        if (!markIcon) return;

        const selectedPages = taskSelectedPages[taskId] || new Set();

        if (selectedPages.has(currentPage)) {
            markIcon.className = 'bi bi-bookmark-check-fill';
            markBtn.classList.add('active');
        } else {
            markIcon.className = 'bi bi-bookmark';
            markBtn.classList.remove('active');
        }
    }

    // Обновление видимости кнопки предпросмотра
    function updatePreviewButtonVisibility() {
        if (previewSelectedBtn) {
            const selectedPages = taskSelectedPages[taskId] || new Set();
            previewSelectedBtn.style.display = selectedPages.size > 0 ? 'inline-block' : 'none';
        }
    }

    // Обновление отображения отмеченных страниц
    function updateSelectedPagesDisplay(taskId) {
        selectedPagesContainer.innerHTML = '';

        const selectedPages = taskSelectedPages[taskId] || new Set();
        const sortedPages = Array.from(selectedPages).sort((a, b) => a - b);

        sortedPages.forEach(page => {
            const badge = document.createElement('div');
            badge.className = 'page-badge';
            badge.innerHTML = `
                ${page}
                <span class="badge-remove" data-page="${page}">&times;</span>
            `;
            selectedPagesContainer.appendChild(badge);

            badge.addEventListener('click', (e) => {
                if (e.target.classList.contains('badge-remove')) return;
                currentPage = page;
                renderPage({ left: viewer.scrollLeft, top: viewer.scrollTop, scale });
            });

            const removeBtn = badge.querySelector('.badge-remove');
            removeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const selectedPages = taskSelectedPages[taskId] || new Set();
                selectedPages.delete(page);
                taskSelectedPages[taskId] = selectedPages;
                updateSelectedPagesDisplay(taskId);
                updateMarkIcon(taskId, currentPage);
                updatePreviewButtonVisibility(taskId);
            });
        });

        updatePreviewButtonVisibility(taskId);
    }

    // Добавление/удаление текущей страницы
    function togglePageMark(taskId, currentPage) {
        // Инициализируем Set для задачи, если его нет
        if (!taskSelectedPages[taskId]) {
            taskSelectedPages[taskId] = new Set();
        }

        const selectedPages = taskSelectedPages[taskId];

        if (selectedPages.has(currentPage)) {
            selectedPages.delete(currentPage);
        } else {
            if (selectedPages.size >= 3) {
                showNotification('Можно отметить не более 3 страниц', 'warning');
                return;
            }
            selectedPages.add(currentPage);
        }

        updateSelectedPagesDisplay(taskId);
        updateMarkIcon(taskId, currentPage);
    }

    // Fullscreen
    const fullscreenBtn = document.createElement('button');
    fullscreenBtn.type = 'button';
    fullscreenBtn.className = 'btn btn-light position-absolute';
    fullscreenBtn.style.bottom = '16px';
    fullscreenBtn.style.right = '16px';
    fullscreenBtn.innerHTML = '<i class="bi bi-arrows-fullscreen"></i>';
    fullscreenBtn.title = 'На весь экран';
    fullscreenBtn.addEventListener('click', () => {
        const elem = taskContainer;
        if (!document.fullscreenElement) elem.requestFullscreen?.();
        else document.exitFullscreen?.();
    });

    setupFullscreenBehavior(taskContainer, fullscreenBtn);

    // Загрузка PDF
    try {
        const loadingTask = pdfjsLib.getDocument(pdf_url);
        pdf = await loadingTask.promise;
        totalPages = pdf.numPages;
        pageCountLabel.textContent = `/ ${totalPages}`;
        pageInput.max = totalPages;
        renderPage();
    } catch (error) {
        viewer.innerHTML = `<div class="text-center text-danger">Не удалось загрузить PDF.</div>`;
    }

    // Рендер страницы
    async function renderPage(oldState = null) {
        if (isRendering) return;
        isRendering = true;
        const prev = oldState || { left: viewer.scrollLeft, top: viewer.scrollTop, scale };
        const factor = scale / prev.scale;

        viewer.innerHTML = '';
        const page = await pdf.getPage(currentPage);
        const viewport = page.getViewport({ scale });
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        const outScale = window.devicePixelRatio || 1;
        canvas.width = Math.floor(viewport.width * outScale);
        canvas.height = Math.floor(viewport.height * outScale);
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        await page.render({ canvasContext: ctx, viewport, transform: outScale !== 1 ? [outScale,0,0,outScale,0,0] : null }).promise;
        viewer.append(canvas);

        // Восстановление scroll
        let newLeft = prev.left * factor;
        const maxLeft = viewer.scrollWidth - viewer.clientWidth;
        viewer.scrollLeft = Math.max(0, Math.min(newLeft, maxLeft));
        let newTop = prev.top * factor;
        const maxTop = viewer.scrollHeight - viewer.clientHeight;
        viewer.scrollTop = Math.max(0, Math.min(newTop, maxTop));

        pageInput.value = currentPage;
        prevBtn.disabled = currentPage <= 1;
        nextBtn.disabled = currentPage >= totalPages;

        // Обновление иконки отметки при смене страницы
        if (userRole === 'teacher' && mode === 'generation') {
            updateMarkIcon();
        }

        isRendering = false;
    }

    // Навигация
    prevBtn.addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            renderPage({ left: viewer.scrollLeft, top: viewer.scrollTop, scale });
        }
    });
    nextBtn.addEventListener('click', () => {
        if (currentPage < totalPages) {
            currentPage++;
            renderPage({ left: viewer.scrollLeft, top: viewer.scrollTop, scale });
        }
    });
    pageInput.addEventListener('change', () => {
        let v = parseInt(pageInput.value, 10);
        currentPage = Math.max(1, Math.min(v, totalPages));
        renderPage({ left: viewer.scrollLeft, top: viewer.scrollTop, scale });
    });

    // Zoom колесом + pinch
    viewer.addEventListener('wheel', e => {
        if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            const old = { left: viewer.scrollLeft, top: viewer.scrollTop, scale };
            scale = Math.min(3, Math.max(0.5, scale + (e.deltaY < 0 ? 0.1 : -0.1)));
            renderPage(old);
        }
    }, { passive: false });
    let pinchCenter, pinchDist;
    viewer.addEventListener('touchstart', e => {
        if (e.touches.length === 2) {
            e.preventDefault();
            const rect = viewer.getBoundingClientRect();
            const [t1, t2] = e.touches;
            pinchCenter = { x: ((t1.clientX + t2.clientX)/2) - rect.left + viewer.scrollLeft, y: ((t1.clientY + t2.clientY)/2) - rect.top + viewer.scrollTop };
            pinchDist = Math.hypot(t1.pageX - t2.pageX, t1.pageY - t2.pageY);
        }
    }, { passive: false });
    viewer.addEventListener('touchmove', e => {
        if (e.touches.length === 2) {
            e.preventDefault();
            const old = { left: viewer.scrollLeft, top: viewer.scrollTop, scale };
            const [t1, t2] = e.touches;
            const dist = Math.hypot(t1.pageX - t2.pageX, t1.pageY - t2.pageY);
            scale = Math.min(3, Math.max(0.5, scale * (dist/pinchDist)));
            pinchDist = dist;
            renderPage(old);
        }
    }, { passive: false });

    // Панирование
    setupPanning(viewer);

    // Обработчики для учителя
    if (userRole === 'teacher') {
        organizeActionButtons(taskContainer, { edit: true, mark: false, restart: false, deleteListener: true, summon: true }, 'light');
        if (mode === 'generation') {
            // Инициализация иконки отметки
            updateMarkIcon();

            // Отметка страницы
            markBtn.addEventListener('click', () => {
                togglePageMark(taskId, currentPage);
            });

            // Функция для открытия модального окна
            function openPdfModal() {
                pdfModal = createPdfPreviewModal(
                    taskId,
                    taskSelectedPages[taskId],
                    pdf_url,
                    mainContainer.dataset.sectionId
                );

                pdfModal.show();
            };

            previewSelectedBtn.addEventListener('click', () => {
                openPdfModal();
            })
        } else if (mode === 'classroom') {
            // Режим просмотра текущей страницы
            previewBtn.addEventListener('click', () => {
                sendMessage('pdf-page', taskId, { page: currentPage }, 'all');
            });
        }
    }
}






        // Заполнение ответов

function fillWordlistAnswer(taskId, answer, isCorrect = "undefined", animation = true) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer) return;

    const { word_index, select = true } = answer;
    if (typeof word_index !== 'number') return;

    const wordItems = taskContainer.querySelectorAll('.word-item');
    if (word_index < 0 || word_index >= wordItems.length) return;

    const wordItem = wordItems[word_index];
    const btn = wordItem.querySelector('.btn-mark-word');
    const icon = btn.querySelector('i');

    if (select) {
        // Добавляем выделение
        wordItem.classList.add('bg-light');
        icon.classList.remove('bi-square');
        icon.classList.add('bi-square-fill');
        btn.classList.add('text-warning');

        if (animation) {
            wordItem.classList.add('animate-highlight');
            setTimeout(() => {
                wordItem.classList.remove('animate-highlight');
            }, 1000);
        }
    } else {
        // Снимаем выделение
        wordItem.classList.remove('bg-light');
        icon.classList.remove('bi-square-fill');
        icon.classList.add('bi-square');
        btn.classList.remove('text-warning');
    }
}

function fillMatchupthewordsAnswer(taskId, answer, isCorrect, animation=true) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer || !taskContainer.innerHTML) return;

    // Подсветка результата
    const wordBtns = taskContainer.querySelectorAll('[data-word]');
    const wordBtn = [...wordBtns].find(btn => btn.dataset.word === answer['card 1']);
    const transBtns = taskContainer.querySelectorAll('[data-translation]');
    const transBtn = [...transBtns].find(btn => btn.dataset.translation === answer['card 2']);


    if (isCorrect) {
        wordBtn.classList.add('bg-success', 'text-light', 'fw-bold');
        transBtn.classList.add('bg-success', 'text-light', 'fw-bold');
        wordBtn.disabled = true;
        transBtn.disabled = true;
    } else if (animation) {
        wordBtn.classList.add('flash-error');
        transBtn.classList.add('flash-error');
        wordBtn.classList.add('disabled');
        transBtn.classList.add('disabled');
        setTimeout(() => {
            wordBtn.classList.remove('flash-error');
            transBtn.classList.remove('flash-error');
            wordBtn.classList.add('btn-outline-secondary');
            transBtn.classList.add('btn-outline-secondary');
            wordBtn.classList.remove('disabled');
            transBtn.classList.remove('disabled');
        }, 1000);
    }

    // Сброс выбора
    wordBtn.classList.remove('btn-primary');
    transBtn.classList.remove('btn-primary');
    if (selectedMatchup[taskId].word === answer['card 1']) {
        selectedMatchup[taskId].word = null;
    }
    if (selectedMatchup[taskId].translation === answer['card 2']) {
        selectedMatchup[taskId].translation = null;
    }
}

function fillFillintheblanksAnswer(taskId, answer, isCorrect, animation=true) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer || !taskContainer.innerHTML) return;

    const input = taskContainer.querySelectorAll('.blank-input')[answer.index];
    input.value = answer.answer;
    autoResizeInput(input);
    if (isCorrect) {
        input.classList.add('bg-success', 'text-light', 'fw-bold');
        input.disabled = true;

        const tooltip = input.parentElement.querySelector('.correct-tooltip');
        if (tooltip) {
            tooltip.classList.add('d-none');
        }

        const badge = [...taskContainer.querySelectorAll('.word-item')]
            .find(b => normalize(b.dataset.word) === normalize(answer.answer) && !b.classList.contains('text-decoration-line-through'));

        if (badge) {
            badge.classList.add('text-decoration-line-through', 'bg-secondary');
            badge.classList.remove('bg-primary');
        }

        const followingInput = taskContainer.querySelector('input:not([disabled])');
        if (followingInput && animation) {
            followingInput.focus();
        }
    } else if (animation) {
        input.classList.remove('is-valid');
        input.classList.add('flash-error');
        input.classList.add('disabled');
        setTimeout(() => {
            input.classList.remove('flash-error');
            input.classList.remove('disabled');
        }, 1000);
    }
}

function checkAllAnswers(taskContainer) {
    const totalQuestions = taskContainer.querySelectorAll('.question-item').length;
    const answered = new Set();

    taskContainer.querySelectorAll('input[type="radio"]:checked').forEach(input => {
        const index = input.name.split('-')[1]; // пример: name="q-2"
        answered.add(parseInt(index));
    });

    const checkBtn = taskContainer.querySelector('.task-check');
    if (answered.size === totalQuestions) {
        checkBtn.classList.remove('disabled');
        checkBtn.disabled = false;
        return true;
    } else {
        checkBtn.classList.add('disabled');
        checkBtn.disabled = true;
        return false;
    }
}

async function checkTestAnswers(taskId) {
    const data = await submitAnswer(taskId, { flag: "check" }, "complex");

    const taskContainer = document.getElementById(taskId);
    if (!taskContainer) return;

    if (!data || data.status !== "success") {
        showNotification(data?.message || "Ошибка проверки", "warning");
        return;
    }

    const answers = data.answer || [];
    const results = data.isCorrect || [];

    if (!Array.isArray(answers) || !Array.isArray(results)) {
        showNotification("Неверный формат ответа от сервера", "error");
        return;
    }

    answers.forEach((ans, index) => {
        const qIndex = ans.qIndex ?? ans.index ?? index; // поддержка и qIndex, и index
        const selectedValue = ans.aIndex ?? ans.value ?? null;
        const isCorrect = results[index];

        if (qIndex === undefined || selectedValue === null) return;

        const radios = taskContainer.querySelectorAll(`input[name="question-${qIndex}"]`);
        radios.forEach(radio => {
            radio.disabled = true;
            if (String(radio.dataset.answerId) === String(selectedValue)) {
                radio.parentElement.classList.add(isCorrect ? 'correct-answer' : 'incorrect-answer');
            }
        });
    });

    updateProgressBar(taskId, data.correct_count, data.incorrect_count, data.max_score);

    const checkBtn = taskContainer.querySelector(`#task-${taskId} .task-check`);
    if (checkBtn) {
        checkBtn.disabled = true;
    }
}

function fillTestAnswer(taskId, answer, isCorrect = "undefined", animation = true) {
    const { qIndex, aIndex } = answer;

    const taskContainer = document.getElementById(taskId);
    if (!taskContainer) return;

    const questionElem = taskContainer.querySelector(`.question-item[data-question-id="${qIndex}"]`);
    if (!questionElem) return;

    const answerElem = questionElem.querySelector(`input[data-answer-id="${aIndex}"]`);

    if (answerElem) {
        answerElem.checked = true;
        if (isCorrect === true) {
            answerElem.parentElement.classList.add('correct-answer');
        } else if (isCorrect === false) {
            answerElem.parentElement.classList.add('incorrect-answer');
        }
    }

    if (isCorrect === true || isCorrect === false) {
        const radios = taskContainer.querySelectorAll(`input[name="question-${qIndex}"]`);
        radios.forEach(radio => {
            radio.disabled = true;
        });
    } else {
        checkAllAnswers(taskContainer);
    }
}

async function checkTrueFalseAnswers(taskId) {
    const data = await submitAnswer(taskId, { flag: "check" }, "complex");

    const taskContainer = document.getElementById(taskId);
    if (!taskContainer) return;

    if (!data || data.status !== "success") {
        showNotification(data?.message || "Ошибка проверки", "warning");
        return;
    }

    const answers = data.answer || [];
    const results = data.isCorrect || [];

    answers.forEach((ans, index) => {
        const answer = ans["answer"];
        const statementIndex = answer["index"];
        const selectedValue = answer["value"];
        const isCorrect = results[index];

        const radios = taskContainer.querySelectorAll(`input[name="statement-${Number(statementIndex) + 1}"]`);
        radios.forEach(radio => {
            radio.disabled = true;
            if (radio.checked) {
                radio.parentElement.classList.add(isCorrect ? 'correct-answer' : 'incorrect-answer');
            }
        });
    });

    const checkBtn = taskContainer.querySelector('.task-check');
    if (checkBtn) {
        checkBtn.disabled = true;
    }
}

function fillTrueorfalseAnswer(taskId, answer, isCorrect = "undefined") {
    const { index, value } = answer;

    const taskContainer = document.getElementById(taskId);
    if (!taskContainer) return;

    // Найти input с нужным index и value
    const inputSelector = `input[name="statement-${parseInt(index) + 1}"][value="${value}"]`;
    const answerElem = taskContainer.querySelector(inputSelector);

    if (answerElem) {
        answerElem.checked = true;
        if (isCorrect === true) {
            answerElem.parentElement.classList.add('correct-answer');
        } else if (isCorrect === false) {
            answerElem.parentElement.classList.add('incorrect-answer');
        }
    }

    if (isCorrect === true || isCorrect === false) {
        // Заблокировать все радио для этого утверждения
        const radios = taskContainer.querySelectorAll(`input[name="statement-${parseInt(index) + 1}"]`);
        radios.forEach(radio => {
            radio.disabled = true;
        });
    } else {
        checkAllAnswers(taskContainer);
    }
}

function fillUnscrambleAnswer(taskId, answer, isCorrect, animation = true) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer || !taskContainer.innerHTML) return;

    const wordContainer = taskContainer.querySelectorAll('.word-container')[answer.word_index];
    const slots = wordContainer.querySelectorAll('.empty-slot');
    const currentSlot = slots[answer.gap_index];
    const button = wordContainer.querySelectorAll('.letter-button')[answer.letter_index];
    if (!currentSlot || !button) return;

    if (isCorrect) {
        const letter = wordContainer.querySelectorAll('.letter-button')[answer.letter_index].dataset.letter;
        if (letter) {
            currentSlot.textContent = letter;
        }
        currentSlot.classList.add('bg-success', 'text-light', 'border-0', 'evaluated', 'filled');
        button.dataset.used = "true";
        button.disabled = true;
        const tooltip = currentSlot.parentElement.querySelector('.correct-tooltip');
        if (tooltip) tooltip.classList.add('d-none');

        // Проверяем завершение слова
        const allFilled = wordContainer.querySelectorAll('.empty-slot').length ===
                          wordContainer.querySelectorAll('.empty-slot.filled.evaluated').length;

        if (allFilled) {
            const hint = wordContainer.querySelector('.hint-container');
            if (hint) hint.style.display = 'none';

            const letterButtonsBlock = wordContainer.querySelector('.letter-buttons');
            if (letterButtonsBlock) letterButtonsBlock.style.display = 'none';

            if (animation) {
                const next = wordContainer.nextElementSibling;
                if (next) next.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    } else {
        // Очистка неправильного слота
        currentSlot.textContent = '';
        currentSlot.classList.remove('filled');

        // Ошибки
        const currentErrors = parseInt(wordContainer.dataset.errors || '0') + 1;
        wordContainer.dataset.errors = currentErrors;

        const statusIcons = wordContainer.querySelectorAll('.bi-x-circle');
        if (statusIcons[currentErrors - 1]) {
            statusIcons[currentErrors - 1].classList.remove('text-success');
            statusIcons[currentErrors - 1].classList.add('text-danger');
        }

        if (currentErrors >= 3) {
            // Блокируем все кнопки и слоты
            wordContainer.querySelectorAll('.letter-button').forEach(btn => btn.disabled = true);
            wordContainer.querySelectorAll('.empty-slot').forEach(slot => slot.classList.add('disabled'));
            currentSlot.textContent = '';
        } else if (animation) {
            currentSlot.classList.add('flash-error');
            setTimeout(() => {
                currentSlot.classList.remove('flash-error');
            }, 1000);
        } else {
            currentSlot.textContent = '';
        }
    }
}

function fillMakeasentenceAnswer(taskId, answer, isCorrect, animation = true) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer) return;

    const sentenceContainer = taskContainer.querySelectorAll('.sentence-container')[answer.sentenceIndex];
    const slots = sentenceContainer.querySelectorAll('.empty-slot');
    const currentSlot = slots[answer.gap_index];
    const button = sentenceContainer.querySelectorAll('.word-button')[answer.word_index];
    const word = button.dataset.word;

    if (!currentSlot || !button) return;

    const updateStatusIcons = (errors) => {
        const icons = sentenceContainer.querySelectorAll('.bi-x-circle');
        if (icons[errors - 1]) {
            icons[errors - 1].classList.remove('text-success');
            icons[errors - 1].classList.add('text-danger');
        }
    };

    const resetSentence = () => {
        const allSlots = sentenceContainer.querySelectorAll('.empty-slot, .filled');
        allSlots.forEach(slot => {
            slot.textContent = '';
            slot.className = 'border border-primary border-2 rounded text-center fw-bold fs-5 empty-slot position-relative';
            slot.classList.remove('filled');
        });

        sentenceContainer.dataset.errors = 0;

        sentenceContainer.querySelectorAll('.bi-x-circle').forEach(icon => {
            icon.classList.remove('text-danger');
            icon.classList.add('text-success');
        });

        sentenceContainer.querySelectorAll('.word-button').forEach(btn => {
            btn.classList.remove('disabled');
            btn.disabled = false;
            delete btn.dataset.used;
        });
    };

    if (isCorrect) {
        if (word) {
            currentSlot.textContent = word;
        }
        currentSlot.classList.add('bg-success', 'text-light', 'border-0', 'filled', 'px-2', 'evaluated');
        button.disabled = true;
        button.dataset.used = "true";

        const tooltip = currentSlot.parentElement.querySelector('.correct-tooltip');
        if (tooltip) tooltip.classList.add('d-none');

        const allSlotsFilled = sentenceContainer.querySelectorAll('.empty-slot').length ===
                               sentenceContainer.querySelectorAll('.empty-slot.evaluated').length;

        if (allSlotsFilled) {
            const wordButtonsField = sentenceContainer.querySelector('.word-buttons');
            if (wordButtonsField) wordButtonsField.style.display = 'none';

            if (animation) {
                const next = sentenceContainer.nextElementSibling;
                if (next) next.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    } else {
        // Очистка неправильного слота
        currentSlot.textContent = '';
        currentSlot.classList.remove('filled');

        const errors = +sentenceContainer.dataset.errors || 0;
        const newErrors = errors + 1;
        sentenceContainer.dataset.errors = newErrors;
        updateStatusIcons(newErrors);

        if (newErrors >= 3) {
            // Блокируем все кнопки и слоты
            sentenceContainer.querySelectorAll('.word-button').forEach(btn => btn.disabled = true);
            sentenceContainer.querySelectorAll('.empty-slot').forEach(slot => slot.classList.add('disabled'));
            currentSlot.textContent = '';
        } else if (animation) {
            currentSlot.classList.add('flash-error');
            setTimeout(() => {
                currentSlot.classList.remove('flash-error');
            }, 1000);
        } else {
            currentSlot.textContent = '';
        }
    }
}

function fillEssayAnswer(taskId, answer, isCorrect, animation=true) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer) return;

    const editor = taskContainer.querySelector(`#essay-editor-${taskId}`);
    if (!editor) return;

    const currentText = editor.innerText.trim();
    updateWordCount(taskId);

    const trimmedAnswer = answer.trim();
    const similarity = getTextSimilarity(currentText, trimmedAnswer);

    const note = taskContainer.querySelector('.essay-note');

    if (similarity < 0.9 && currentText && animation) {
        if (note) {
            note.style.display = 'block';
            const safeHTML = convertMarkdownToHTML(trimmedAnswer);
            note.innerHTML = `
                <div class="alert alert-warning p-3 border rounded-3 position-relative">
                    <div class="fw-semibold mb-2">Ваш ответ отличается от ответа другого пользователя:</div>
                    <div class="converted-essay mb-1">${safeHTML}</div>
                    <div class="d-flex justify-content-end">
                        <button type="button"
                                class="btn btn-sm btn-link use-answer-btn"
                                title="Использовать"
                                style="text-decoration: none;">
                            <i class="bi bi-clipboard-check fs-5"></i>
                        </button>
                    </div>
                </div>
            `;

            const useBtn = note.querySelector('.use-answer-btn');
            useBtn.addEventListener('click', () => {
                editor.innerHTML = safeHTML;
                note.style.display = 'none';
                updateWordCount(taskId);
            });
        }
    } else {
        if (note) note.style.display = 'none';
        editor.innerHTML = convertMarkdownToHTML(trimmedAnswer);
        updateWordCount(taskId);
    }
}

function fillLabelimagesAnswer(taskId, answer, isCorrect, animation=true) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer) return;

    const inputs = taskContainer.querySelectorAll('.label-image');
    const input = [...inputs].find(i => parseInt(i.dataset.imageIndex) === answer.image_index);
    if (!input) return;

    input.value = answer.label;

    const tooltip = input.parentElement.querySelector('.correct-tooltip');

    if (isCorrect) {
        input.classList.add('bg-success', 'text-center', 'fw-bold', 'text-light');
        input.disabled = true;
        if (tooltip) tooltip.classList.add('d-none');

        const badge = [...taskContainer.querySelectorAll('.word-item')]
            .find(b => normalize(b.dataset.word) === normalize(answer.label) && !b.classList.contains('text-decoration-line-through'));

        if (badge) {
            badge.classList.add('text-decoration-line-through', 'bg-secondary');
            badge.classList.remove('bg-primary');
        }

        const followingInput = taskContainer.querySelector('input:not([disabled])');
        if (followingInput && animation) {
            followingInput.focus();
        }
    } else if (animation) {
        input.classList.add('flash-error');
        input.classList.add('disabled');
        setTimeout(() => {
            input.classList.remove('disabled');
            input.classList.remove('flash-error');
        }, 1000);
    }
}

function fillSortintocolumnsAnswer(taskId, answer, isCorrect, animation=true) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer) return;

    const dropZone = taskContainer.querySelector(`.column-dropzone[data-column="${escapeHtml(answer.column_name)}"]`);
    if (!dropZone) return;

    const innerZone = dropZone.querySelector('.d-flex');
    let ghost = [...innerZone.children].find(
        el => el.dataset.word === answer.word && !el.draggable
    );

    // Если ghost не существует (например, WebSocket вызвал fill у другого пользователя)
    if (!ghost) {
        ghost = document.createElement('span');
        ghost.className = 'badge fs-6 draggable-word';
        ghost.dataset.word = answer.word;
        ghost.textContent = answer.word;
        ghost.draggable = false;
        innerZone.appendChild(ghost);
    }
    const wordBank = taskContainer.querySelector('.word-bank');
    if (!wordBank) return;
    const wordElem = wordBank.querySelector(`.draggable-word[data-word="${escapeHtml(answer.word)}"]`);

    if (isCorrect) {
        ghost.classList.remove('bg-primary');
        ghost.classList.add('bg-success', 'bg-opacity-50');
        wordElem.style.display = 'none';
    } else {
        if (animation) {
            ghost.classList.remove('bg-primary');
            ghost.classList.add('flash-error');
            wordElem.style.display = 'none';
            setTimeout(() => {
                ghost.remove();
                wordElem.style.display = 'inline-block';
            }, 1000);
        } else {
            ghost.remove();
        }
    }
}







        // Очистка контейнеров

function clearWordlistAnswer(taskId) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer) return;

    const wordItems = taskContainer.querySelectorAll('.word-item');
    wordItems.forEach(wordItem => {
        wordItem.classList.remove('bg-light');

        const btn = wordItem.querySelector('.btn-mark-word');
        if (btn) {
            btn.classList.remove('text-warning');
            const icon = btn.querySelector('i');
            if (icon) {
                icon.classList.remove('bi-square-fill');
                icon.classList.add('bi-square');
            }
        }
    });
}

function clearMatchupthewordsAnswer(taskId) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer || !taskContainer.innerHTML) return;

    // Находим все кнопки в контейнере задачи
    const wordButtons = taskContainer.querySelectorAll('[data-word]');
    const translationButtons = taskContainer.querySelectorAll('[data-translation]');

    // Сбрасываем стили и состояния для всех кнопок
    wordButtons.forEach(button => {
        button.classList.remove('bg-success', 'text-light', 'flash-error', 'btn-primary');
        button.classList.add('btn-outline-secondary'); // Возвращаем исходный стиль
        button.disabled = false; // Делаем кнопку активной
    });

    translationButtons.forEach(button => {
        button.classList.remove('bg-success', 'text-light', 'flash-error', 'btn-primary');
        button.classList.add('btn-outline-secondary'); // Возвращаем исходный стиль
        button.disabled = false; // Делаем кнопку активной
    });

    // Сбрасываем состояние выбора
    if (selectedMatchup && selectedMatchup[taskId]) {
        selectedMatchup[taskId].word = null;
        selectedMatchup[taskId].translation = null;
    }
}

function clearFillintheblanksAnswer(taskId) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer || !taskContainer.innerHTML) return;

    // Находим все поля ввода в контейнере задачи
    const inputs = taskContainer.querySelectorAll('.blank-input');

    // Восстанавливаем слова (word-item)
    const wordItems = taskContainer.querySelectorAll('.word-item');
    wordItems.forEach(wordItem => {
        wordItem.classList.remove('text-decoration-line-through', 'bg-secondary');
        wordItem.classList.add('bg-primary'); // Возвращаем исходный стиль
    });

    // Сбрасываем значения, стили и состояния для всех полей ввода
    inputs.forEach(input => {
        input.value = ''; // Очищаем значение
        input.classList.remove('bg-success', 'text-light', 'fw-bold', 'flash-error', 'is-valid');
        input.classList.remove('disabled'); // Удаляем атрибут disabled
        input.disabled = false; // Делаем поле доступным для редактирования

        const tooltip = input.parentElement.querySelector('.correct-tooltip');
        tooltip.classList.remove('d-none');
    });
}

function clearTestAnswer(taskId) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer) return;

    const form = taskContainer.querySelector('.test-form');
    if (!form) return;

    // Находим все вопросы и радиокнопки
    const allQuestions = form.querySelectorAll('.question-item');
    const allInputs = form.querySelectorAll('input[type="radio"]');

    // Проходим по всем вопросам и сбрасываем состояние
    allQuestions.forEach(questionElem => {
        // Удаляем стили для контейнеров ответов
        const answerItems = questionElem.querySelectorAll('.answer-item');
        answerItems.forEach(container => {
            container.classList.remove('correct-answer', 'incorrect-answer', 'fw-bold');
        });
    });

    // Сбрасываем состояние всех радиокнопок
    allInputs.forEach(input => {
        input.checked = false; // Снимаем выбор
        input.disabled = false; // Делаем радиокнопку доступной
    });
}

function clearTrueorfalseAnswer(taskId) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer) return;

    const form = taskContainer.querySelector('.statements-list');
    if (!form) return;

    // Находим все утверждения и радиокнопки
    const allStatements = form.querySelectorAll('.question-item');
    const allInputs = form.querySelectorAll('input[type="radio"]');

    // Проходим по всем утверждениям и сбрасываем состояние
    allStatements.forEach(statementElem => {
        // Удаляем стили для контейнеров ответов
        const answerItems = statementElem.querySelectorAll('.form-check');
        answerItems.forEach(container => {
            container.classList.remove('correct-answer', 'incorrect-answer', 'fw-bold');
        });
    });

    // Сбрасываем состояние всех радиокнопок
    allInputs.forEach(input => {
        input.checked = false; // Снимаем выбор
        input.disabled = false; // Делаем радиокнопку доступной
    });
}

function clearUnscrambleAnswer(taskId) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer || !taskContainer.innerHTML) return;

    // Находим все контейнеры слов
    const wordContainers = taskContainer.querySelectorAll('.word-container');

    wordContainers.forEach(wordContainer => {
        // Очищаем слоты
        const slots = wordContainer.querySelectorAll('.empty-slot, .filled');
        slots.forEach(slot => {
            slot.textContent = '';
            slot.className = 'border border-primary border-2 rounded text-center fw-bold fs-5 empty-slot position-relative';
            slot.classList.remove('filled', 'bg-success', 'text-light', 'bg-warning', 'text-white');
        });

        // Восстанавливаем кнопки с буквами
        const buttons = wordContainer.querySelector('.letter-buttons');
        buttons.style.display = 'flex';
        buttons.querySelectorAll('button').forEach(button => {
            button.classList.remove('bg-success', 'text-light', 'flash-error', 'btn-primary');
            button.classList.add('btn-outline-secondary'); // Возвращаем исходный стиль
            button.disabled = false; // Делаем кнопку активной
            delete button.dataset.used;
        });

        const hintContainers = wordContainer.querySelectorAll('.hint-container');
        hintContainers.forEach(hintContainer => {
            hintContainer.style.display = 'block';
        });

        // Сбрасываем счетчик ошибок
        wordContainer.dataset.errors = 0;

        // Восстанавливаем статусные иконки
        const statusIcons = wordContainer.querySelectorAll('.bi-x-circle');
        statusIcons.forEach(icon => {
            icon.classList.remove('text-danger');
            icon.classList.add('text-success');
        });

        const tooltips = wordContainer.parentElement.querySelectorAll('.correct-tooltip');
        tooltips.forEach(tooltip => {
            tooltip.classList.remove('d-none');
        });
    });
}

function clearMakeasentenceAnswer(taskId) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer || !taskContainer.innerHTML) return;

    // Находим все контейнеры предложений
    const sentenceContainers = taskContainer.querySelectorAll('.sentence-container');

    sentenceContainers.forEach(sentenceContainer => {
        // Очищаем слоты
        const slots = sentenceContainer.querySelectorAll('.empty-slot, .filled');
        slots.forEach(slot => {
            slot.textContent = '';
            slot.className = 'border border-primary border-2 rounded text-center fw-bold fs-5 empty-slot position-relative';
            slot.classList.remove('filled', 'bg-success', 'text-light', 'bg-warning', 'text-white');
        });

        // Восстанавливаем кнопки со словами
        const buttons = sentenceContainer.querySelectorAll('.word-button');
        buttons.forEach(button => {
            button.disabled = false;
            delete button.dataset.used;
        });

        const tooltips = sentenceContainer.parentElement.querySelectorAll('.correct-tooltip');
        tooltips.forEach(t => t.classList.remove('d-none'));
        const wordButtonsField = sentenceContainer.querySelector('.word-buttons');
        if (wordButtonsField) {
            wordButtonsField.style.display = 'flex';
        }

        // Сбрасываем счетчик ошибок
        sentenceContainer.dataset.errors = 0;

        // Восстанавливаем статусные иконки
        const statusIcons = sentenceContainer.querySelectorAll('.bi-x-circle');
        statusIcons.forEach(icon => {
            icon.classList.remove('text-danger');
            icon.classList.add('text-success');
        });

        // Восстанавливаем контейнер с кнопками, если он был удален
        if (!sentenceContainer.querySelector('.word-buttons')) {
            const wordButtonsField = document.createElement('div');
            wordButtonsField.className = 'word-buttons d-flex gap-2 mt-2';

            const words = sentenceContainer.dataset.words.split(',');
            words.forEach((word, index) => {
                const button = document.createElement('button');
                button.className = 'btn btn-outline-primary word-button';
                button.dataset.word = word.trim();
                button.textContent = word.trim();
                wordButtonsField.appendChild(button);
            });

            sentenceContainer.appendChild(wordButtonsField);
        }
    });
}

function clearEssayAnswer(taskId) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer || !taskContainer.innerHTML) return;

    const note = taskContainer.querySelector('.essay-note');
    if (note) {
        note.style.display = 'none';
    }

    const editor = taskContainer.querySelector(`#essay-editor-${taskId}`);
    if (editor) {
        editor.innerHTML = '';
    }
    updateWordCount(taskId);
}

function clearLabelimagesAnswer(taskId) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer) return;

    // Находим все поля ввода
    const inputs = taskContainer.querySelectorAll('.label-image');

    // Очищаем поля ввода и сбрасываем стили
    inputs.forEach(input => {
        input.value = ''; // Очищаем значение
        input.classList.remove('bg-success', 'text-center', 'fw-bold', 'text-light', 'flash-error');
        input.disabled = false; // Делаем поле доступным
    });

    // Восстанавливаем слова (word-item)
    const wordItems = taskContainer.querySelectorAll('.word-item');
    wordItems.forEach(wordItem => {
        wordItem.classList.remove('text-decoration-line-through', 'bg-secondary');
        wordItem.classList.add('bg-primary'); // Возвращаем исходный стиль
    });

    // Восстанавливаем подсказки, если они были удалены
    const tooltips = taskContainer.querySelectorAll('.correct-tooltip');
    tooltips.forEach(tooltip => {
        if (!tooltip.parentElement.querySelector('.label-image').value) {
            tooltip.classList.remove('d-none');
        }
    });
}

function clearSortintocolumnsAnswer(taskId) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer) return;

    // Находим банк слов
    const wordBank = taskContainer.querySelector('.word-bank');
    if (!wordBank) return;
    const words = wordBank.querySelectorAll('.draggable-word');
    words.forEach(word => {
        word.style.display = 'inline-block';
    });

    // Находим все колонки
    const dropZones = taskContainer.querySelectorAll('.column-dropzone');

    // Перемещаем все слова обратно в банк слов
    dropZones.forEach(dropZone => {
        const innerZone = dropZone.querySelector('.d-flex');
        if (!innerZone) return;

        // Очищаем колонку
        innerZone.innerHTML = '';
    });
}









        // Вспомогательные функции

function correctTooltipContainer(answer) {
    if (userRole !== 'teacher') {
        return "";
    }
    return `<span class="correct-tooltip position-absolute start-50 translate-middle-x bg-success text-white px-3 py-2 rounded shadow-sm fw-bold"
              style="
                  display: none;
                  z-index: 2;
                  bottom: 100%;
                  transform: translate(-50%, -8px);
                  font-size: 0.875rem;
                  max-width: 240px;
                  width: max-content;
                  white-space: normal;
                  text-align: center;
                  pointer-events: none;
              ">
            ${answer}
        </span>`;
}

function shuffleArray(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [array[i], array[j]] = [array[j], array[i]];
    }
    return array;
}

function getWordEnding(count) {
    if (count === 1) return "слово";
    if (count >= 2 && count <= 4) return "слова";
    return "слов";
}

function updateWordCount(taskId) {
    const editor = document.getElementById(`essay-editor-${taskId}`);
    const wordCountSpan = document.getElementById(`word-count-${taskId}`);
    if (editor && wordCountSpan) {
        // Получаем текст без лишних пробелов
        const text = editor.innerText.trim();
        // Разбиваем по пробельным символам и отфильтровываем пустые строки
        const words = text.length ? text.split(/\s+/).filter(Boolean) : [];
        wordCountSpan.textContent = words.length + " " + getWordEnding(words.length);

        // Сохраняем текст в скрытый textarea (если нужно для отправки)
        const textarea = document.getElementById(`essay-content-${taskId}`);
        if (textarea) {
            textarea.value = editor.innerHTML;
        }
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

function closeAllEmbeds() {
    document.querySelectorAll('.embed-container').forEach(container => {
        container.classList.add('d-none');
        const iframe = container.querySelector('iframe');
        if (iframe) {
            iframe.src = "";
            iframe.classList.remove('w-100', 'vh-100');
        }
    });

    document.querySelectorAll('.btn.btn-primary.btn-lg.d-none').forEach(button => {
        button.classList.remove('d-none');
    });

    document.querySelectorAll('.badge-element').forEach(header => {
        header.textContent = "Interaction";
    });

    // Поставить на паузу все аудио на странице
    document.querySelectorAll('audio').forEach(audio => {
        if (!audio.paused) {
            audio.pause();
        }
    });
}

function toggleEmbed(button, embedCode) {
    closeAllEmbeds();

    const wrapper = button.closest('.embed-wrapper');
    const iframeContainer = wrapper.querySelector('.embed-container');
    const iframe = iframeContainer.querySelector('iframe');
    const card = button.closest('.card');

    // Показываем контейнер с iframe и скрываем кнопку запуска
    iframeContainer.classList.remove('d-none');
    button.classList.add('d-none');

    // Добавляем элемент загрузки
    let loader = document.createElement('div');
    loader.className = 'loading-spinner d-flex justify-content-center align-items-center position-absolute top-0 start-0 w-100 h-100 bg-white bg-opacity-75';
    loader.innerHTML = `
        <div class="spinner-border text-primary" role="status" style="width: 3rem; height: 3rem;">
            <span class="visually-hidden">Loading...</span>
        </div>
    `;
    iframeContainer.appendChild(loader);

    // Извлекаем URL из embed-кода
    const srcMatch = embedCode.match(/src="([^"]+)"/);
    if (srcMatch && srcMatch[1]) {
        iframe.src = srcMatch[1];
        iframe.classList.add('w-100', 'vh-100');
    }

    // Убираем загрузку при полной загрузке iframe или максимум через 5 секунд
    const removeLoader = () => {
        if (loader) {
            loader.remove();
            loader = null;
        }
    };

    iframe.onload = removeLoader;
    setTimeout(removeLoader, 10000);
}

function closeEmbed(button) {
    const card = button.closest('.card');
    const wrapper = card.querySelector('.embed-wrapper');
    const iframeContainer = wrapper.querySelector('.embed-container');
    const launchButton = wrapper.querySelector('button.btn.btn-primary.btn-lg');
    const iframe = iframeContainer.querySelector('iframe');

    // Скрываем контейнер с iframe и сбрасываем src
    iframeContainer.classList.add('d-none');
    iframe.src = "";
    iframe.classList.remove('w-100', 'vh-100');

    // Показываем кнопку запуска
    launchButton.classList.remove('d-none');
}

function setupModernAudioPlayer(player) {
    if (!(player instanceof HTMLAudioElement)) {
        console.error('Переданный элемент не является аудиоплеером');
        return;
    }

    const container = document.createElement('div');
    container.className = 'd-flex align-items-center gap-3';

    const playBtn = document.createElement('button');
    playBtn.className = 'btn btn-outline-primary rounded d-flex align-items-center justify-content-center';
    playBtn.style.width = '40px';
    playBtn.style.height = '40px';
    playBtn.style.borderRadius = '8px';
    playBtn.innerHTML = '<i class="bi bi-play-fill"></i>';
    playBtn.disabled = false;

    const progressWrap = document.createElement('div');
    progressWrap.className = 'progress flex-grow-1';
    progressWrap.style.height = '8px';
    progressWrap.style.cursor = 'pointer';

    const progressBar = document.createElement('div');
    progressBar.className = 'progress-bar bg-primary';
    progressBar.style.width = '0%';
    progressBar.style.pointerEvents = 'none';

    progressWrap.appendChild(progressBar);

    const time = document.createElement('div');
    time.className = 'text-muted small';
    time.style.minWidth = '40px';
    time.textContent = '0:00';

    container.appendChild(playBtn);
    container.appendChild(progressWrap);
    container.appendChild(time);
    player.parentNode.insertBefore(container, player);
    player.classList.add('d-none');

    function formatTime(seconds) {
        if (!isFinite(seconds)) return '0:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60).toString().padStart(2, '0');
        return `${mins}:${secs}`;
    }

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

    Object.entries(audioEvents).forEach(([event, handler]) => {
        player.addEventListener(event, handler);
    });

    // Если аудио уже загружено — вручную вызываем canplay для разблокировки кнопки
    if (player.readyState >= 3) {
        audioEvents.canplay();
    }

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

    progressWrap.addEventListener('click', (e) => {
        if (!isFinite(player.duration)) return;

        const { left, width } = progressWrap.getBoundingClientRect();
        const clickX = e.clientX - left;
        const percent = Math.max(0, Math.min(1, clickX / width));
        player.currentTime = player.duration * percent;
    });

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

function disableAllLetters(container) {
    const buttons = container.querySelectorAll('.letter-button');
    buttons.forEach(btn => {
        if (!btn.disabled) {
            btn.classList.add('disabled');
            setTimeout(() => {
                btn.classList.remove('disabled');
            }, 1000);
        }
    });

}

function disableAllWordButtons(container) {
    const buttons = container.querySelectorAll('.word-button');
    buttons.forEach(btn => {
        if (!btn.disabled) {
            btn.classList.add('disabled');
            setTimeout(() => {
                btn.classList.remove('disabled');
            }, 1000);
        }
    });
}

function getTextSimilarity(a, b) {
    if (!a || !b) return 0;
    const cleanA = a.trim().toLowerCase();
    const cleanB = b.trim().toLowerCase();
    const longer = cleanA.length > cleanB.length ? cleanA : cleanB;
    const shorter = cleanA.length > cleanB.length ? cleanB : cleanA;

    if (longer.length === 0) return 1.0;
    return (longer.length - editDistance(longer, shorter)) / parseFloat(longer.length);
}

function editDistance(s1, s2) {
    const costs = [];
    for (let i = 0; i <= s1.length; i++) {
        let lastValue = i;
        for (let j = 0; j <= s2.length; j++) {
            if (i === 0)
                costs[j] = j;
            else {
                if (j > 0) {
                    let newValue = costs[j - 1];
                    if (s1.charAt(i - 1) !== s2.charAt(j - 1))
                        newValue = Math.min(Math.min(newValue, lastValue), costs[j]) + 1;
                    costs[j - 1] = lastValue;
                    lastValue = newValue;
                }
            }
        }
        if (i > 0)
            costs[s2.length] = lastValue;
    }
    return costs[s2.length];
}

async function createPdfFromPages(pdf_url, pageNumbers) {
    const { PDFDocument } = PDFLib;
    const response = await fetch(pdf_url);
    const existingPdfBytes = await response.arrayBuffer();
    const srcPdf = await PDFDocument.load(existingPdfBytes);

    const newPdf = await PDFDocument.create();

    for (const pageNum of pageNumbers) {
        const [page] = await newPdf.copyPages(srcPdf, [pageNum - 1]);
        newPdf.addPage(page);
    }

    const newPdfBytes = await newPdf.save();
    return uint8ArrayToBase64(new Uint8Array(newPdfBytes));
}

function uint8ArrayToBase64(uint8Array) {
    let binaryString = '';
    for (let i = 0; i < uint8Array.length; i++) {
        binaryString += String.fromCharCode(uint8Array[i]);
    }
    return `data:application/pdf;base64,${btoa(binaryString)}`;
}

function renderFilePreview(dataUrlOrPath, targetEl) {
    // Проверка типа данных
    console.log('dataUrlOrPath:', dataUrlOrPath, typeof dataUrlOrPath);
    if (typeof dataUrlOrPath !== 'string') {
        console.error('Expected dataUrlOrPath to be a string');
        targetEl.innerHTML = `<div class="text-danger">Ошибка: ожидалась строка URL или base64</div>`;
        return;
    }

    // Если передан base64 — сразу рендерим
    if (dataUrlOrPath.startsWith('data:application/pdf;base64,')) {
        renderFromBase64(dataUrlOrPath);
    } else {
        // Иначе загружаем файл и преобразуем в base64
        fetch(dataUrlOrPath)
            .then(response => response.blob())
            .then(blob => {
                const reader = new FileReader();
                reader.onload = () => {
                    renderFromBase64(reader.result);
                };
                reader.readAsDataURL(blob);
            })
            .catch(err => {
                console.error('Ошибка при загрузке PDF:', err);
                targetEl.innerHTML = `<div class="text-danger">Ошибка загрузки PDF</div>`;
            });
    }

    function renderFromBase64(dataUrl) {
        targetEl.innerHTML = `
            <div class="pdf-page-viewer position-relative text-center">
                <div class="canvas-wrapper overflow-auto mb-2">
                    <canvas class="pdf-page-canvas border"></canvas>
                </div>
                <div class="d-flex justify-content-center align-items-center mb-2">
                    <button type="button" class="btn btn-secondary btn-sm me-2" id="prevPageBtn">&larr;</button>
                    <span id="pageIndicator" class="mx-2"></span>
                    <button type="button" class="btn btn-secondary btn-sm ms-2" id="nextPageBtn">&rarr;</button>
                </div>
            </div>
        `;
        const wrapper = targetEl.querySelector('.canvas-wrapper');
        const canvas = targetEl.querySelector('.pdf-page-canvas');
        const ctx = canvas.getContext('2d');
        const indicator = targetEl.querySelector('#pageIndicator');
        const prevBtn = targetEl.querySelector('#prevPageBtn');
        const nextBtn = targetEl.querySelector('#nextPageBtn');
        let pdfDoc = null, pageNum = 1, pageCount = 0;

        try {
            const binary = atob(dataUrl.split(',')[1]);
            const len = binary.length;
            const buffer = new Uint8Array(len);
            for (let i = 0; i < len; i++) buffer[i] = binary.charCodeAt(i);
            pdfjsLib.getDocument({ data: buffer }).promise
                .then(doc => {
                    pdfDoc = doc;
                    pageCount = doc.numPages;
                    indicator.textContent = `${pageNum} / ${pageCount}`;
                    updateNavButtons();
                    return doc.getPage(pageNum);
                })
                .then(page => renderPage(page));
        } catch (e) {
            console.error('Ошибка при декодировании PDF:', e);
            targetEl.innerHTML = `<div class="text-danger">Ошибка декодирования PDF</div>`;
        }

        function renderPage(page) {
            const viewport = page.getViewport({ scale: 1 });
            canvas.width = viewport.width;
            canvas.height = viewport.height;
            canvas.style.width = '100%';
            canvas.style.height = 'auto';
            page.render({ canvasContext: ctx, viewport }).promise.then(() => {
                indicator.textContent = `${pageNum} / ${pageCount}`;
                updateNavButtons();
            });
        }

        function queueRenderPage(num) {
            pdfDoc.getPage(num).then(renderPage);
        }

        function updateNavButtons() {
            prevBtn.style.visibility = pageNum > 1 ? 'visible' : 'hidden';
            nextBtn.style.visibility = pageNum < pageCount ? 'visible' : 'hidden';
        }

        prevBtn.addEventListener('click', () => {
            if (pageNum <= 1) return;
            pageNum--;
            queueRenderPage(pageNum);
        });

        nextBtn.addEventListener('click', () => {
            if (pageNum >= pageCount) return;
            pageNum++;
            queueRenderPage(pageNum);
        });
    }
}

function setupFullscreenBehavior(taskContainer, fullscreenBtn) {
    fullscreenBtn.addEventListener('click', () => {
        const elem = taskContainer;
        if (!document.fullscreenElement) elem.requestFullscreen?.();
        else document.exitFullscreen?.();
    });

    document.addEventListener('fullscreenchange', () => {
        const inFull = document.fullscreenElement === taskContainer;
        const bodyEl = taskContainer.querySelector('.card-body');
        if (inFull) {
            taskContainer.style.width = '100vw';
            taskContainer.style.height = '100vh';
            bodyEl.style.height = '95vh';
            fullscreenBtn.innerHTML = '<i class="bi bi-arrows-angle-contract"></i>';
            fullscreenBtn.title = 'Выйти из полного экрана';
        } else {
            taskContainer.style.width = '';
            taskContainer.style.height = '';
            bodyEl.style.height = '80vh';
            fullscreenBtn.innerHTML = '<i class="bi bi-arrows-fullscreen"></i>';
            fullscreenBtn.title = 'На весь экран';
        }
    });
}

function setupPanning(viewer) {
    let isDragging = false;
    let dragStart = {};

    function onDragStart(e) {
        e.preventDefault();
        isDragging = true;
        dragStart = {
            x: (e.touches ? e.touches[0].clientX : e.clientX) + viewer.scrollLeft,
            y: (e.touches ? e.touches[0].clientY : e.clientY) + viewer.scrollTop
        };
        document.addEventListener('mousemove', onDragMove);
        document.addEventListener('mouseup', onDragEnd);
        document.addEventListener('touchmove', onDragMove, { passive: false });
        document.addEventListener('touchend', onDragEnd);
    }

    function onDragMove(e) {
        if (!isDragging) return;
        e.preventDefault();
        const x = (e.touches ? e.touches[0].clientX : e.clientX);
        const y = (e.touches ? e.touches[0].clientY : e.clientY);
        viewer.scrollLeft = dragStart.x - x;
        viewer.scrollTop = dragStart.y - y;
    }

    function onDragEnd() {
        isDragging = false;
        document.removeEventListener('mousemove', onDragMove);
        document.removeEventListener('mouseup', onDragEnd);
        document.removeEventListener('touchmove', onDragMove);
        document.removeEventListener('touchend', onDragEnd);
    }

    // Включаем панорамирование
    viewer.style.cursor = 'grab';
    viewer.addEventListener('mousedown', onDragStart);
    viewer.addEventListener('touchstart', onDragStart, { passive: false });
}

const generationMessages = [
    "Анализируем страницы",
    "Ищем ключевые моменты",
    "Готовим структуру задания",
    "Обрабатываем PDF",
    "Формулируем вопросы",
    "Генерируем ответы",
    "Добавляем интерактивность",
    "Настраиваем форматирование",
    "Оптимизируем данные",
    "Формируем карточки заданий",
    "Задаём параметры",
    "Финализируем результат",
    "Почти готово",
    "Последние штрихи",
    "Заканчиваем генерацию"
];

function createPdfPreviewModal(taskId, selectedPages, pdfUrl, sectionId) {
    const modalId = `pdfPreviewModal-${taskId}`;
    console.log(taskId, selectedPages, pdfUrl, sectionId);

    // Удаляем предыдущее модальное окно с таким ID, если есть
    const existingModal = document.getElementById(modalId);
    if (existingModal) {
        console.warn(`[PDF Modal] Удаление предыдущего модального окна: ${modalId}`);
        existingModal.remove();
    }

    const modalElement = document.createElement('div');
    modalElement.className = 'modal fade';
    modalElement.id = modalId;
    modalElement.setAttribute('tabindex', '-1');
    modalElement.setAttribute('aria-hidden', 'true');

    modalElement.innerHTML = `
        <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content">
                <div class="modal-header">
                    <h6 class="modal-title">Интерактивизация</h6>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <div class="mb-3 controls-wrapper">
                        <div class="input-group">
                            <input type="text" class="form-control query-input" maxlength="255"
                                   placeholder="Введите запрос (опционально)">
                        </div>
                        <div class="d-flex justify-content-between mt-2 align-items-center">
                            <div class="form-check me-2">
                                <input type="checkbox" class="form-check-input new-section-checkbox" id="${modalId}-new-section">
                                <label class="form-check-label" for="${modalId}-new-section">Новый раздел</label>
                            </div>
                            <button type="button" class="generate-pdf-btn btn btn-primary rounded-pill btn-sm">
                                Сгенерировать
                            </button>
                        </div>
                    </div>

                    <div class="preview-pdf-container text-center border-0">
                        <button class="show-preview-btn btn text-primary border-0 fw-bold mx-auto">
                            Посмотреть выбранный контент
                        </button>
                        <div class="preview-content mt-3"></div>
                    </div>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modalElement);

    // 🔍 Проверка перед инициализацией
    if (!modalElement || !(modalElement instanceof HTMLElement)) {
        console.error(`[PDF Modal] modalElement невалиден:`, modalElement);
        return;
    }

    try {
        const modal = new bootstrap.Modal(modalElement, {
            backdrop: true,
            keyboard: true
        });

        const controlsWrapper = modalElement.querySelector('.controls-wrapper');
        const queryInput = modalElement.querySelector('.query-input');
        const newSectionCheckbox = modalElement.querySelector('.new-section-checkbox');
        const showPreviewBtn = modalElement.querySelector('.show-preview-btn');
        const generateBtn = modalElement.querySelector('.generate-pdf-btn');
        const previewContent = modalElement.querySelector('.preview-content');

        if (!showPreviewBtn || !generateBtn || !previewContent || !controlsWrapper) {
            console.error(`[PDF Modal] Не найдены кнопки/контейнеры в modalElement`);
            return;
        }

        const hideControlsForLoading = () => {
            // скрываем элементы управления пока идёт загрузка/генерация
            if (controlsWrapper) controlsWrapper.style.display = 'none';
            if (showPreviewBtn) showPreviewBtn.style.display = 'none';
        };

        const restoreControlsAfterError = () => {
            if (controlsWrapper) controlsWrapper.style.display = '';
            if (showPreviewBtn && selectedPages && selectedPages.size > 0) showPreviewBtn.style.display = 'block';
            if (generateBtn) generateBtn.disabled = false;
        };

        modalElement.addEventListener('shown.bs.modal', () => {
            showPreviewBtn.style.display = selectedPages && selectedPages.size > 0 ? 'block' : 'none';
            generateBtn.disabled = false;
        });

        modalElement.addEventListener('hidden.bs.modal', () => {
            console.log(`[PDF Modal] Модальное окно скрыто и удаляется: ${modalId}`);
            try {
                modal.dispose();
            } catch (e) {
                // ignore
            }
            modalElement.remove();
        });

        // Предпросмотр выбранных страниц
        showPreviewBtn.addEventListener('click', async () => {
            if (!selectedPages || selectedPages.size === 0) return;

            // показываем спиннер и скрываем контролы
            hideControlsForLoading();
            previewContent.innerHTML = `
                <div class="d-flex flex-column justify-content-center align-items-center w-100" style="min-height: 200px;">
                    <div class="spinner-border" role="status" aria-hidden="true"></div>
                    <div class="mt-2 small text-muted">Модальное окно можно закрыть</div>
                </div>
            `;

            try {
                const pages = Array.from(selectedPages).sort((a, b) => a - b);
                const pdfBase64 = await createPdfFromPages(pdfUrl, pages);
                renderFilePreview(pdfBase64, previewContent);
            } catch (error) {
                console.error('Ошибка предпросмотра:', error);
                previewContent.innerHTML = `
                    <div class="alert alert-danger">
                        Не удалось создать предпросмотр: ${error && error.message ? error.message : error}
                    </div>
                `;
                showNotification(`Не удалось создать предпросмотр: ${error && error.message ? error.message : error}`, "danger");
                // восстановим контролы чтобы пользователь мог попытаться снова
                restoreControlsAfterError();
            }
        });

        // Генерация интерактивных заданий из PDF
        generateBtn.addEventListener('click', async () => {
            const query = queryInput ? queryInput.value : '';
            const isNewSection = newSectionCheckbox ? newSectionCheckbox.checked : false;

            let messageIndex = 0;
            let intervalId = null;

            const updateMessage = () => {
                if (messageIndex < generationMessages.length) {
                    const statusTextElem = previewContent.querySelector('.loading-status');
                    if (statusTextElem) statusTextElem.textContent = generationMessages[messageIndex++];
                }
            };

            // Показываем спиннер и скрываем контролы
            hideControlsForLoading();
            previewContent.innerHTML = `
                <div class="d-flex flex-column justify-content-center align-items-center w-100" style="min-height: 200px;">
                    <div class="spinner-border text-primary mb-3" role="status"></div>
                    <div class="loading-status text-primary fw-semibold"></div>
                    <div class="mt-2 small text-muted">Модальное окно можно закрыть</div>
                </div>
            `;

            const statusText = previewContent.querySelector('.loading-status');
            if (statusText) statusText.textContent = generationMessages[messageIndex++] || '';

            generateBtn.disabled = true;
            showPreviewBtn.style.display = "none";

            intervalId = setInterval(updateMessage, 5000);

            try {
                const pages = Array.from(selectedPages).sort((a, b) => a - b);
                const pdfBase64 = await createPdfFromPages(pdfUrl, pages);

                // 1️⃣ Запускаем задачу на сервере
                const response = await fetch('/generate-pdf/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRFToken': getCookie('csrftoken')
                    },
                    body: new URLSearchParams({
                        base64: pdfBase64,
                        query: query,
                        section_id: sectionId,
                        is_new_section: isNewSection
                    })
                });

                if (!response.ok) {
                    const text = await response.text();
                    throw new Error(text || 'Ошибка отправки запроса на генерацию');
                }

                const { task_id, res_section_id } = await response.json();
                if (!task_id || !res_section_id) throw new Error("Не получен task_id или section_id");

                // 2️⃣ Опрос статуса задачи
                const checkStatus = async () => {
                    try {
                        const statusResp = await fetch(`/pdf-status/${task_id}/`);
                        if (!statusResp.ok) throw new Error(await statusResp.text());
                        const statusData = await statusResp.json();
                        console.log("Статус задачи:", statusData);

                        if (statusData.status === "SUCCESS" && statusData.result && !statusData.result.error) {
                            clearInterval(intervalId);

                            const result = statusData.result;

                            if (isNewSection) {
                                result.result.forEach(item => {
                                    initializeBasicContainer(item.task_id, res_section_id, item.task_type);
                                });
                                addSectionToList(res_section_id, "New Section");
                                initSectionsFromDOM();
                                renderSectionList();
                            } else {
                                result.result.forEach(item => {
                                    initializeBasicContainer(item.task_id, res_section_id, item.task_type);
                                });
                            }

                            // уведомляем пользователя и закрываем модал
                            showNotification("Интерактивизация учебника выполнена", "success");

                            try {
                                modal.hide();
                            } catch (e) {
                                // ignore
                            }

                            await loadSection(res_section_id);

                            // скроллим к последнему элементу (пытаемся получить id последнего задания)
                            try {
                                const lastItemObj = result.result[result.result.length - 1];
                                const lastTaskId = lastItemObj && lastItemObj.task_id ? lastItemObj.task_id : null;
                                if (lastTaskId) {
                                    await new Promise(r => setTimeout(r, 500));
                                    const lastTaskContainer = document.getElementById(lastTaskId);
                                    if (lastTaskContainer) {
                                        lastTaskContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                    }
                                }
                            } catch (e) {
                                // non-fatal
                            }

                        } else if (
                            ["FAILURE", "RETRY", "error"].includes(statusData.status) ||
                            (statusData.status === "SUCCESS" && statusData.result?.error)
                        ) {
                            clearInterval(intervalId);
                            throw new Error(statusData.result?.error || "Ошибка генерации");
                        } else {
                            // ещё не закончено — повторяем через 3 сек
                            setTimeout(checkStatus, 3000);
                        }
                    } catch (error) {
                        console.error('Ошибка генерации:', error);
                        clearInterval(intervalId);
                        previewContent.innerHTML = `
                            <div class="alert alert-danger">
                                Ошибка при генерации: ${error && error.message ? error.message : error}
                            </div>
                        `;
                        showNotification(error && error.message ? error.message : "Ошибка генерации", "danger");
                        restoreControlsAfterError();
                    }
                };

                // старт опроса
                checkStatus();

            } catch (error) {
                console.error('Ошибка генерации:', error);
                clearInterval(intervalId);
                previewContent.innerHTML = `
                    <div class="alert alert-danger">
                        Ошибка при генерации: ${error && error.message ? error.message : error}
                    </div>
                `;
                showNotification(error && error.message ? error.message : "Ошибка генерации", "danger");
                restoreControlsAfterError();
            }
        });

        return modal;
    } catch (e) {
        console.error(`[PDF Modal] Ошибка при инициализации bootstrap.Modal:`, e);
        console.debug('modalElement:', modalElement.outerHTML);
        showNotification("Не удалось открыть модальное окно предпросмотра PDF", "danger");
        return;
    }
}






        // Анимации

function updateProgressBar(taskId, correctScore, incorrectScore, maxScore, showAnimation=true) {
    const taskContainer = document.getElementById(taskId);
    if (!taskContainer) return;
    return;

    // Рассчитываем проценты
    const taskType = taskContainer.getAttribute('data-task-type');
    if (taskType === 'essay') {
        return;
    }
    const correctPercent = Math.round((correctScore / maxScore) * 100);
    const incorrectPercent = Math.min(Math.round((incorrectScore / maxScore) * 100), 100 - correctPercent);
    const remainingPercent = 100 - correctPercent - incorrectPercent;

    // Ищем или создаем контейнер для progress bar
    let progressContainer = taskContainer.querySelector('.progress-container');
    if (!progressContainer) {
        progressContainer = document.createElement('div');
        progressContainer.className = 'progress-container mt-3 px-3';
        taskContainer.querySelector('.card-body').appendChild(progressContainer);
    }

    // Обновляем или создаем progress bar
    let progressBar = progressContainer.querySelector('.progress');
    if (!progressBar) {
        progressBar = document.createElement('div');
        progressBar.className = 'progress';
        progressBar.style.height = '25px';
        progressBar.style.borderRadius = '10px';
        progressBar.style.overflow = 'hidden';
        progressBar.style.boxShadow = 'inset 0 1px 3px rgba(0,0,0,0.2)';
        progressBar.innerHTML = `
            <div class="progress-bar bg-success" role="progressbar" style="width: 0%; transition: width 0.6s ease;" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
            <div class="progress-bar bg-danger" role="progressbar" style="width: 0%; transition: width 0.6s ease 0.3s;" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
            <div class="progress-bar bg-light" role="progressbar" style="width: 100%; transition: width 0.6s ease 0.6s;" aria-valuenow="100" aria-valuemin="0" aria-valuemax="100"></div>
        `;
        progressContainer.appendChild(progressBar);
    }

    // Обновляем значения
    const successBar = progressBar.querySelector('.bg-success');
    const dangerBar = progressBar.querySelector('.bg-danger');
    const remainingBar = progressBar.querySelector('.bg-light');

    successBar.style.width = `${correctPercent}%`;
    successBar.setAttribute('aria-valuenow', correctPercent);
    successBar.title = `Правильные ответы: ${correctScore}`;

    dangerBar.style.width = `${incorrectPercent}%`;
    dangerBar.setAttribute('aria-valuenow', incorrectPercent);
    dangerBar.title = `Ошибки: ${incorrectScore}`;

    remainingBar.style.width = `${remainingPercent}%`;
    remainingBar.setAttribute('aria-valuenow', remainingPercent);

    // Добавляем подпись с эмодзи
    let progressText = progressContainer.querySelector('.progress-text');
    if (!progressText) {
        progressText = document.createElement('div');
        progressText.className = 'progress-text d-flex justify-content-between align-items-center mt-2';
        progressContainer.appendChild(progressText);
    }

    // Определяем эмодзи и сообщение в зависимости от результата
    let emoji, message, animation = '';
    const completionRatio = correctScore / maxScore;

    if (correctPercent + incorrectPercent >= 60) {
        if (completionRatio >= 0.8) {
            emoji = '🎉';
            message = 'Отличный результат!';
            animation = 'correct';
        } else if (completionRatio >= 0.6) {
            emoji = '👍';
            message = 'Хорошая работа!';
            animation = 'incorrect';
    } else if (completionRatio >= 0.4) {
        emoji = '🙂';
        message = 'Неплохо!';
        animation = 'incorrect';
    } else {
        emoji = '🤔';
        message = 'Попробуй еще раз!';
        animation = 'incorrect';
    }
    } else {
        emoji = '';
        message = '';
        animation = '';
    }
    if (correctPercent + incorrectPercent === 0) {
        progressBar.style.height = '1px';
    } else {
        progressBar.style.height = '';
    };

    // Если задание завершено (прогресс 100%)
    if (correctPercent + incorrectPercent >= 100) {
        emoji = completionRatio >= 0.8 ? '🏆' : completionRatio >= 0.6 ? '🎯' : '✅';
        if (showAnimation) {
            triggerCompletionAnimation(taskContainer, animation);
        }
    }

    progressText.innerHTML = `
        <span class="text-muted">${message}</span>
        <span class="emoji-display fs-3">${emoji}</span>
    `;

    // Добавляем стили для эмодзи
    const emojiDisplay = progressText.querySelector('.emoji-display');
    emojiDisplay.style.transition = 'transform 0.3s ease';
    emojiDisplay.style.display = 'inline-block';

    // Анимация при наведении на эмодзи
    emojiDisplay.addEventListener('mouseover', () => {
        emojiDisplay.style.transform = 'scale(1.3) rotate(10deg)';
    });
    emojiDisplay.addEventListener('mouseout', () => {
        emojiDisplay.style.transform = 'scale(1)';
    });
}

function triggerCompletionAnimation(container, type) {
    // Проверка на существование контейнера
    if (!container) {
        console.error("Контейнер не найден");
        return;
    }

    // Цвета подсветки
    const bgColor = type === 'correct'
        ? 'rgba(40, 167, 69, 0.8)' // Прозрачность 80%
        : 'rgba(255, 108, 0, 0.8)'; // Прозрачность 80%

    // Создание полупрозрачного слоя (overlay)
    const overlay = createOverlay(bgColor);
    container.style.position = 'relative';
    container.appendChild(overlay);

    // Генерация случайных эмодзи
    const positiveEmojis = ['🎉', '✨', '🌟', '💫', '🔥', '⭐️', '💥', '🚀', '🏆', '🎯'];
    const warningEmojis = ['💣', '💢', '🎃', '⚠️', '🌀', '🔶', '🔸', '❌', '❗', '🔴'];
    const emojis = type === 'correct' ? positiveEmojis : warningEmojis;

    // Количество эмодзи (например, 10)
    const emojiCount = 10;

    // Массив для хранения созданных элементов эмодзи
    const emojiElements = [];

    // Создаем эмодзи и добавляем их в контейнер
    for (let i = 0; i < emojiCount; i++) {
        const emoji = emojis[Math.floor(Math.random() * emojis.length)];
        const emojiElement = createEmojiElement(emoji);

        // Устанавливаем случайное начальное положение внутри контейнера
        const randomX = Math.random() * 100; // Случайное смещение по X (в процентах)
        const randomY = Math.random() * 100; // Случайное смещение по Y (в процентах)
        emojiElement.style.left = `${randomX}%`;
        emojiElement.style.top = `${randomY}%`;

        // Добавляем элемент в контейнер
        container.appendChild(emojiElement);
        emojiElements.push(emojiElement);
    }

    // Запуск синхронных анимаций через минимальную задержку
    setTimeout(() => {
        // Анимация исчезновения оверлея
        opacityOneToZero(overlay, () => {
            // Удаляем оверлей после завершения анимации
            if (overlay.parentNode === container) {
                container.removeChild(overlay);
            }
        });

        // Анимация всех эмодзи
        emojiElements.forEach((emojiElement) => {
            animateEmoji(emojiElement, container, () => {
                // Удаляем эмодзи после завершения анимации
                if (emojiElement.parentNode === container) {
                    container.removeChild(emojiElement);
                }
            });
        });
    }, 10);

    // Сброс стилей контейнера
    setTimeout(() => {
        container.style.position = '';
    }, 6000); // Соответствует длительности всех анимаций
}

function createOverlay(bgColor) {
    const overlay = document.createElement('div');
    overlay.style.position = 'absolute';
    overlay.style.top = '0';
    overlay.style.left = '0';
    overlay.style.width = '100%';
    overlay.style.height = '100%';
    overlay.style.backgroundColor = bgColor;
    overlay.style.pointerEvents = 'none';
    overlay.style.zIndex = '100';
    overlay.style.opacity = '1';
    return overlay;
}

function createEmojiElement(emoji) {
    const emojiElement = document.createElement('div');
    emojiElement.textContent = emoji;
    emojiElement.style.position = 'absolute';
    emojiElement.style.left = '50%';
    emojiElement.style.top = '50%';
    emojiElement.style.transform = 'translate(-50%, -50%) rotate(0deg)'; // Начальное положение
    emojiElement.style.fontSize = '10em';
    emojiElement.style.textAlign = 'center';
    emojiElement.style.width = 'fit-content';
    emojiElement.style.zIndex = '101';
    emojiElement.style.transition = 'font-size 1.5s ease, opacity 1.5s ease, transform 1.5s ease';
    return emojiElement;
}

function animateEmoji(emojiElement, container, onAnimationEnd) {
    // Получаем размеры контейнера
    const containerRect = container.getBoundingClientRect();
    const containerWidth = containerRect.width;
    const containerHeight = containerRect.height;

    // Генерация случайных смещений для улетания
    const randomX = (Math.random() - 0.5) * containerWidth * 1.5; // Случайное смещение по X (-75% до +75% ширины)
    const randomY = -(Math.random() * containerHeight * 0.7); // Смещение только вверх (от -70% высоты)

    // Устанавливаем начальные стили для анимации
    emojiElement.style.position = 'absolute';
    emojiElement.style.fontSize = '4em'; // Начальный размер шрифта
    emojiElement.style.opacity = '1';

    // Получаем текущее значение transform
    const currentTransform = window.getComputedStyle(emojiElement).transform;

    // Если transform уже установлен, используем его как начальную точку
    emojiElement.style.transform = currentTransform || 'translate(0, 0)';
    emojiElement.style.transition = `
        transform 1.5s cubic-bezier(0.68, -0.55, 0.27, 1.55),
        opacity 1.5s ease-out,
        font-size 1.5s ease-out
    `;

    // Добавляем задержку перед началом анимации
    setTimeout(() => {
        // Анимация: уменьшение размера шрифта, вращение, смещение и исчезновение
        emojiElement.style.fontSize = '2em'; // Конечный размер шрифта
        emojiElement.style.opacity = '0';
        emojiElement.style.transform = `translate(${randomX}px, ${randomY}px) rotate(720deg)`; // Улетание и вращение

        // Удаление элемента после завершения анимации
        setTimeout(onAnimationEnd, 3000); // Длительность анимации
    }, 10); // Небольшая задержка для корректного старта transition
}

function opacityOneToZero(element, onAnimationEnd) {
    if (!element) {
        console.error("Элемент не найден");
        return;
    }

    let opacity = 1;
    const duration = 500; // 0.5 секунды
    const start = performance.now();

    function updateOpacity(timestamp) {
        const elapsed = timestamp - start;
        opacity = 1 - (elapsed / duration);

        if (opacity < 0) {
            opacity = 0;
        }

        element.style.opacity = opacity;

        if (opacity > 0) {
            requestAnimationFrame(updateOpacity);
        } else {
            onAnimationEnd?.(); // Вызываем callback после завершения анимации
        }
    }

    requestAnimationFrame(updateOpacity);
}








        // Загрузка раздела и заданий

async function fetchTaskData(taskId) {
    try {
        const response = await fetch(`/hub/api/tasks/${taskId}/`);
        if (!response.ok) {
            throw new Error(`Ошибка HTTP: ${response.status}`);
        }
        const data = await response.json();
        return data;
    } catch (error) {
        showNotification("Ошибка при получении данных.", "danger");
        return null; // Возвращаем null в случае ошибки
    }
}

async function loadSection(sectionId) {
    // Блокируем кнопки разделов
    const sectionButtons = document.querySelectorAll('.section-link');
    sectionButtons.forEach(btn => btn.disabled = true);
    sectionButtons.forEach(btn => btn.classList.remove('fw-bold'));

    const actualSectionButton = document.querySelector(`.section-link[data-section-id="${sectionId}"]`);
    actualSectionButton.classList.add('fw-bold');

    // Находим все обёртки заданий и очищаем их содержимое
    const taskItems = document.querySelectorAll(`.task-item`);
    taskItems.forEach(item => resetContainer(item));

    // Инициализируем загрузку раздела (например, AJAX-запрос или другая логика)
    await showSectionTasks(sectionId);

    // Проверяем, загрузились ли задания для данного раздела
    const tasksLoaded = await checkTasksLoaded(sectionId);

    // Если задачи загружены, активируем кнопки
    if (tasksLoaded) {
        sectionButtons.forEach(btn => btn.disabled = false);
    }

    closeAllEmbeds();
}

async function showSectionTasks(sectionId) {
    if (!sectionId) {
        return;
    }

    let hasSuccessfulTasks = false;
    const taskItems = [...document.querySelectorAll('.task-item')].filter(task => {
        if (task.getAttribute('data-section-id') === sectionId) {
            if (task.innerHTML.trim() !== '') {
                task.parentElement.style.display = 'flex'; //Отображаем уже загруженные задания
                task.classList.add('border-light');
                task.classList.add('mb-4');
                hasSuccessfulTasks = true;
                return false;
            } else {
                return true;
            }
        }
        return false;
    });

    mainContainer.dataset.sectionId = sectionId;

    for (const taskContainer of taskItems) {
        const taskId = taskContainer.id;
        const taskType = taskContainer.getAttribute('data-task-type');

        try {
            const taskData = await fetchTaskData(taskId);
            const functionName = `handle${taskType.charAt(0).toUpperCase() + taskType.slice(1).toLowerCase()}`;

            if (typeof window[functionName] === 'function') {
                try {
                    window[functionName](taskId, taskData);
                } catch (error) {
                    showNotification(`Ошибка при загрузке данных задания ${taskType}.`, "danger");
                }
            } else {
                showNotification(`Тип задания ${functionName} не найден.`, "danger");
            }
            taskContainer.closest('.full-task-container').style.display = 'flex';
            taskContainer.classList.add('border-light');
            taskContainer.classList.add('mb-4');
            taskContainer.style.display = 'block';
            hasSuccessfulTasks = true;
        } catch (error) {
            taskContainer.closest('.full-task-container').remove();
            showNotification(`Ошибка при загрузке данных задания ${taskType}.`, "danger");
        }
    }

    const button = document.querySelector('#add-task-button-wrapper');
    if (button) {
        if (hasSuccessfulTasks && userRole === 'teacher') {
            button.classList.add('mt-3', 'mt-lg-4');
        } else if (userRole === 'teacher') {
            button.classList.remove('mt-3', 'mt-lg-4');
        }
    }
}

async function checkTasksLoaded(sectionId) {
    // Функция для проверки загрузки задач
    const checkAllLoaded = () => {
        const taskItems = document.querySelectorAll(`.task-item[data-section-id="${sectionId}"]`);
        return Array.from(taskItems).every(task => task.innerHTML.trim() !== "");
    };

    return new Promise((resolve) => {
        const interval = setInterval(() => {
            if (checkAllLoaded()) {
                clearInterval(interval); // Останавливаем интервал
                resolve(true); // Завершаем, когда задачи загружены
            }
        }, 300); // Проверяем каждые 300 мс
    });
}

function initializeBasicContainer(taskId, sectionId, taskType) {
    // Создаем основной контейнер
    const fullTaskContainer = document.createElement('div');
    fullTaskContainer.classList.add('align-items-start', 'm-3', 'full-task-container');
    fullTaskContainer.style.display = 'none'; // по умолчанию скрыт, как в шаблоне
    fullTaskContainer.style.flexWrap = 'nowrap'; // чтобы сохранить выравнивание как flex
    fullTaskContainer.style.display = 'flex'; // чтобы включить flex (после flexWrap)

    fullTaskContainer.dataset.taskId = taskId;

    // Добавляем handle для перетаскивания (только для учителя)
    if (userRole === 'teacher') {
        const dragHandle = document.createElement('div');
        dragHandle.classList.add('drag-handle', 'me-3');
        dragHandle.style.cursor = 'grab';
        dragHandle.style.display = 'none'; // по умолчанию скрыт

        const dragIcon = document.createElement('i');
        dragIcon.classList.add('bi', 'bi-grip-vertical');

        dragHandle.appendChild(dragIcon);
        fullTaskContainer.appendChild(dragHandle);
    }

    // Создаем основной контейнер задачи
    const taskDiv = document.createElement('div');
    taskDiv.classList.add('task-item', 'card', 'border-0', 'rounded', 'flex-grow-1');
    taskDiv.id = taskId;
    taskDiv.dataset.sectionId = sectionId;
    taskDiv.dataset.taskType = taskType.toLowerCase();

    // Добавляем основной контейнер задачи в обертку
    fullTaskContainer.appendChild(taskDiv);

    // Вставляем в DOM
    taskList.appendChild(fullTaskContainer);

    return fullTaskContainer;
}

function resetContainer(taskContainer) {
    taskContainer.parentElement.style.display = 'none';
    taskContainer.classList.add('border-0');
    taskContainer.classList.remove('border-light');
    taskContainer.classList.remove('mb-4');
}

const SECTION_TYPES = ['completion', 'learning', 'hometask', 'revision'];
let sections = [];

function initSectionsFromDOM() {
    const items = document.querySelectorAll('#section-list > li');
    sections = Array.from(items)
        .filter(li => !li.classList.contains('separator'))
        .map(li => ({
            id: li.dataset.sectionId,
            name: li.querySelector('.section-link').textContent.trim(),
            type: li.dataset.sectionType
        }));
}

function renderSectionList() {
    const ul = document.getElementById('section-list');
    ul.innerHTML = '';

    SECTION_TYPES.forEach((type, typeIndex) => {
        const group = sections.filter(s => s.type === type);
        if (!group.length) return;

        // разделитель между группами
        if (
            typeIndex > 0 &&
            SECTION_TYPES.slice(0, typeIndex).some(t => sections.some(s => s.type === t))
        ) {
            const hr = document.createElement('hr');
            hr.className = 'm-0 p-0 w-100 border-top border-secondary';
            ul.appendChild(hr);
        }

        group.forEach(s => {
            const li = document.createElement('li');
            li.className =
                'list-group-item d-flex justify-content-between align-items-center border-0 rounded-0';
            li.dataset.sectionId = s.id;
            li.dataset.sectionType = s.type;

            li.innerHTML = `
                <div class="d-flex align-items-center gap-2" style="flex:1; min-width:0;">
                    <span class="drag-handle text-muted" title="Перетащить" style="cursor: grab; display: none;">
                        <i class="bi bi-grip-vertical"></i>
                    </span>
                    <button type="button"
                        class="btn btn-link section-link text-decoration-none text-truncate text-primary p-0 me-2"
                        data-section-id="${s.id}">
                        ${s.name}
                    </button>
                </div>
                <div class="section-action-buttons align-items-center"
                    style="display: ${userRole === 'teacher' ? 'flex' : 'none'}; gap: 0.5rem;">
                    <button type="button" class="btn btn-link p-0 edit-section-button"
                        data-section-id="${s.id}" title="Редактировать">
                        <i class="bi bi-pencil-fill text-secondary"></i>
                    </button>
                    <button type="button" class="btn btn-link p-0 delete-btn"
                        data-section-id="${s.id}" title="Удалить">
                        <i class="bi bi-trash3-fill text-secondary"></i>
                    </button>
                </div>
            `;

            ul.appendChild(li);
        });
    });
}

function attachListDelegation() {
    const ul = document.getElementById('section-list');

    // Очищаем все старые обработчики, удаляя и пересоздавая содержимое
    const currentHTML = ul.innerHTML;
    ul.innerHTML = '';
    ul.innerHTML = currentHTML;

    if (userRole === "teacher") {
        // Редактирование
        ul.addEventListener('click', async e => {
            const editBtn = e.target.closest('.edit-section-button');
            if (!editBtn) return;

            const li = editBtn.closest('li');
            const link = li.querySelector('.section-link');
            const id = link.dataset.sectionId;
            const oldName = link.textContent.trim();

            const section = sections.find(s => s.id === id);
            if (!section) return;

            openEditSectionModal(section.id, section.name, section.type);
        });

        // Удаление
        ul.addEventListener('click', e => {
            const delBtn = e.target.closest('.delete-btn');
            if (!delBtn) return;
            const id = delBtn.dataset.sectionId;
            handleDeleteSection(id);
        });
    }

    // Переход по разделу
    ul.addEventListener('click', e => {
        const link = e.target.closest('.section-link');
        if (!link) return;
        const id = link.dataset.sectionId;
        loadSection(id);
    });
}

function initializeFirstSection() {
    if (!sections.length) return;
    const firstId = sections[0].id;
    const firstLink = document.querySelector(`#section-list li[data-section-id="${firstId}"] .section-link`);
    if (firstLink) {
        document.querySelectorAll('.section-link.fw-bold').forEach(el => el.classList.remove('fw-bold'));
        firstLink.classList.add('fw-bold');
        loadSection(firstId);
    }
}

function addSectionToList(sectionId, name) {
    const sectionList = document.getElementById('section-list');
    if (!sectionList) {
        console.error('[addSectionToList] Элемент #section-list не найден');
        return;
    }

    const li = document.createElement('li');
    li.className = 'list-group-item d-flex justify-content-between align-items-center border-0 rounded-0';
    li.dataset.sectionId = sectionId;
    li.dataset.sectionType = 'learning';

    li.innerHTML = `
        <button type="button"
                class="btn btn-link section-link text-decoration-none text-truncate text-primary p-0 me-2"
                data-section-id="${sectionId}">
            ${name}
        </button>
        <div class="section-action-buttons align-items-center" style="display: flex; gap: 0.5rem;">
            <button type="button" class="btn btn-link p-0 edit-section-button"
                    data-section-id="${sectionId}" title="Редактировать">
                <i class="bi bi-pencil-fill text-secondary"></i>
            </button>
            <button type="button" class="btn btn-link p-0 delete-btn"
                    data-section-id="${sectionId}" title="Удалить">
                <i class="bi bi-trash3-fill text-secondary"></i>
            </button>
        </div>
    `;

    sectionList.appendChild(li);
}

document.addEventListener('DOMContentLoaded', () => {
    initSectionsFromDOM();
    renderSectionList();
    attachListDelegation();
    initializeFirstSection();
    getContext(lessonId);

    const sectionActionButtons = document.querySelectorAll('.section-action-buttons');
    if (userRole === "teacher") {
        addSectionButtonInitialization();
        setTimeout(() => {
            createAddTaskButton();
        }, 100)

        const addToClassButton = document.querySelector('#addToClassButton');
        if (addToClassButton) addToClassButton.style.display = 'block';

        if (sectionActionButtons) {
            sectionActionButtons.forEach(button => {
                button.style.display = 'flex';
            });
        }

        // Инициализируем кнопку добавления заметки контекста
        if (addTextContextButtons) {
            addTextContextButtons.forEach(button => {
                button.style.display = 'block';
                button.addEventListener('click', addTextContext);
            });
        }

        // Модальное окно для добавления урока в класс
        const cards = document.querySelectorAll('.classroom-card');
        if (cards) {
            cards.forEach(card => {
                const radio = card.querySelector('input[type="radio"]');

                card.addEventListener('click', () => {
                    // Снимаем выделение со всех карточек
                    cards.forEach(c => c.classList.remove('active'));

                    // Выделяем текущую
                    card.classList.add('active');

                    // Активируем radio, если не был выбран
                    if (!radio.checked) {
                        radio.checked = true;
                    }
                });
            });
        }
    }

    if (mode === "public") {
        // Модальное окно для добавления урока в класс
        const cards = document.querySelectorAll('.classroom-card');
        if (cards) {
            cards.forEach(card => {
                const radio = card.querySelector('input[type="radio"]');

                card.addEventListener('click', () => {
                    // Снимаем выделение со всех карточек
                    cards.forEach(c => c.classList.remove('active'));

                    // Выделяем текущую
                    card.classList.add('active');

                    // Активируем radio, если не был выбран
                    if (!radio.checked) {
                        radio.checked = true;
                    }
                });
            });
        }
    }
});







        // Работа с контекстом
        
function removeAccordionElementFromContextWindow(taskId) {
    const dropdownId = `dropdown-${taskId}`;

    // Находим и удаляем элемент в первом контекстном окне
    const accordionElement1 = contextWindows[0].querySelector(`.accordion[data-dropdown-id="${dropdownId}"]`);
    if (accordionElement1) {
        accordionElement1.remove();
    }

    // Находим и удаляем элемент во втором контекстном окне
    const accordionElement2 = contextWindows[1].querySelector(`.accordion[data-dropdown-id="${dropdownId}"]`);
    if (accordionElement2) {
        accordionElement2.remove();
    }

    // Обновляем содержимое задачи
    const taskItem = document.getElementById(taskId);
    if (taskItem) {
        const actionsContainer = taskItem.querySelector(".actions-container");

        if (actionsContainer) {
            const oldIcons = actionsContainer.querySelectorAll('.bi-bookmark-check');
            const newIcons = actionsContainer.querySelectorAll('.bi-bookmark');
            oldIcons.forEach(icon => {
                icon.parentElement.style.display = "none";
            });
            newIcons.forEach(icon => {
                icon.parentElement.style.display = "flex";
            });
        }
    }

    // Проверяем, есть ли еще элементы в контекстных окнах
    const accordionElementsLength = contextWindows[0].querySelectorAll(".accordion").length;
    if (accordionElementsLength === 0) {
        const permanentText = document.querySelectorAll(".permanent-context-text");
        if (permanentText) {
            permanentText.forEach(el => el.style.display = "block");
        }
        if (userRole === 'student') {
            contextWindows.forEach(el => el.style.display = "none");
        }
    }
}

function showTaskInContextWindow(taskId, header, content) {
    const sectionId = document.getElementById("main-container").dataset.sectionId;
    const dropdownId = `dropdown-${taskId || Date.now()}`;

    // Отображаем контекстные окна
    contextWindows.forEach(el => el.style.display = "block");

    const permanentText = document.querySelectorAll(".permanent-context-text");
    if (permanentText) {
        permanentText.forEach(el => el.style.display = "none");
    }

    const taskItem = document.getElementById(taskId);
    let taskType;

    if (taskItem && taskItem.dataset.sectionId === sectionId) {
        taskType = taskItem.getAttribute("data-task-type");
        const actionsContainer = taskItem.querySelector(".actions-container");

        if (actionsContainer) {
            const oldIcons = actionsContainer.querySelectorAll('.bi-bookmark');
            const newIcons = actionsContainer.querySelectorAll('.bi-bookmark-check');

            // Скрываем старые иконки
            oldIcons.forEach(icon => {
                icon.closest('button').style.display = "none";  // Скрываем всю кнопку
            });

            // Показываем новые иконки
            newIcons.forEach(icon => {
                icon.closest('button').style.display = "flex";  // Показываем всю кнопку
            });
        }

    }

    const dropdownContainer = document.createElement("div");
    dropdownContainer.classList.add("mb-2");

    dropdownContainer.innerHTML = `
        <div class="accordion bg-none" id="accordion-${dropdownId}" data-dropdown-id="${dropdownId}">
            <div class="accordion-item" data-task-id="${taskId}" data-task-type="${taskType || 'undefined'}">
                <h2 class="accordion-header position-relative d-flex align-items-center rounded bg-primary text-white" id="heading-${dropdownId}">
                    <button class="accordion-button bg-primary fw-bold text-light flex-grow-1 border-0 shadow-none text-start rounded-bottom text-nowrap text-truncate d-inline-block ms-auto"
                            type="button" data-bs-toggle="collapse" data-bs-target="#${dropdownId}"
                            aria-expanded="true" aria-controls="${dropdownId}">
                        ${clearText(header) || "Заметка"}
                    </button>
                    ${userRole === 'teacher' ? `
                        <button class="btn btn-sm btn-close btn-close-white ms-2 me-2 remove-task-btn" data-task-id="${taskId}" aria-label="Удалить"></button>
                    ` : ''}
                </h2>
                <div id="${dropdownId}" class="accordion-collapse collapse" aria-labelledby="heading-${dropdownId}">
                    <div class="accordion-body">
                        ${clearText(content)}
                    </div>
                </div>
            </div>
        </div>
    `;


    const accordionItem = dropdownContainer.querySelector(".accordion-item");
    const accordionBody = dropdownContainer.querySelector(".accordion-body");

    const dropdownContainerCopy = dropdownContainer.cloneNode(true);

    // Привязываем обработчик на кнопку удаления задачи
    if (userRole === 'teacher') {
        dropdownContainer.querySelector(".remove-task-btn").addEventListener("click", function () {
            removeTaskFromContext(taskId);
        });
        dropdownContainerCopy.querySelector(".remove-task-btn").addEventListener("click", function () {
            removeTaskFromContext(taskId);
        });
    }
    if (userRole === 'teacher') {
        const removeBtn1 = dropdownContainer.querySelector(".remove-task-btn");
        removeBtn1.addEventListener("click", function (e) {
            e.stopPropagation(); // чтобы не раскрывался аккордеон
            removeTaskFromContext(taskId);
        });
        const removeBtn2 = dropdownContainerCopy.querySelector(".remove-task-btn");
        removeBtn2.addEventListener("click", function (e) {
            e.stopPropagation(); // чтобы не раскрывался аккордеон
            removeTaskFromContext(taskId);
        });
    }

    contextWindows[0].appendChild(dropdownContainer);
    contextWindows[1].appendChild(dropdownContainerCopy);
}

function getContext(lesson_id, mode = "upload") {
    // 3 варианта: upload (отображение в контекстном окне), isAvailable (есть ли контекст вообще) и view (получение контекста)
    return fetch(`/hub/context/${lesson_id}/get/`)
        .then(response => {
            if (!response.ok) {
                throw new Error("Ошибка получения данных контекста");
            }
            return response.json();
        })
        .then(data => {
            if (mode === "upload") {
                // Работа с DOM
                contextWindows.forEach(el => el.querySelectorAll(".accordion").forEach(elem => elem.remove()));
                const permanentText = document.querySelectorAll(".permanent-context-text");
                if (permanentText) {
                    permanentText.forEach(el => el.style.display = "block");
                }
                if (userRole === 'student') {
                    contextWindows.forEach(el => el.style.display = "none");
                }
                Object.entries(data.context).forEach(([task_id, taskData]) => {
                    if (typeof taskData === 'object' && taskData !== null) {
                        let header = taskData.header ? taskData.header : "Заметка";
                        let content = taskData.content || "";
                        showTaskInContextWindow(task_id, header, content);
                    } else {
                        console.warn(`Неожиданный формат данных для ${task_id}:`, taskData);
                    }
                });
                const accordionElementsLength = contextWindows[0].querySelectorAll(".accordion").length;
                if (userRole === 'student' && accordionElementsLength === 0) {
                    contextWindows.forEach(el => el.style.display = "none");
                }
                return null;
            } else {
                if (data.context) {
                    if (mode === "isAvailable") {
                        return true;
                    } else {
                        return data.context;
                    }
                } else {
                    return false;
                }
            }
        })
        .catch(error => {
            console.error(error);
            showNotification("Не удалось загрузить контекст", "danger");
            return false;
        });
}







        // Общие функции для всего документа

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

            // Стиль для центрирования по экрану
            alertContainer.style.position = 'fixed';
            alertContainer.style.top = '50%';
            alertContainer.style.left = '50%';
            alertContainer.style.transform = 'translate(-50%, -50%)';
            alertContainer.style.zIndex = '9999'; // поверх всего
            alertContainer.style.display = 'block';
            alertContainer.style.width = '60%';
            alertContainer.style.maxWidth = '500px';

            alertContainer.classList.add('text-center', 'p-3');

            document.body.appendChild(alertContainer);
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
    alert.className = `alert alert-${color} fade show m-2`;
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
        setTimeout(() => alertContainer.remove(), 500);
    }, time);
}

function convertMarkdownToHTML(text) {
    text = text.replace(/\n/g, '<br>');
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
    text = text.replace(/_(.*?)_/g, '<u>$1</u>');
    return DOMPurify.sanitize(text);
}

function convertHTMLToMarkdown(html) {
    html = html.replace(/<br\s*\/?>/g, '\n');
    html = html.replace(/<strong>(.*?)<\/strong>/g, '**$1**');
    html = html.replace(/<em>(.*?)<\/em>/g, '*$1*');
    html = html.replace(/<u>(.*?)<\/u>/g, '_$1_');
    return html;
}

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

const allowedSources = [
    // Wordwall (основной и staging) с языковым кодом
    /^https:\/\/(?:www\.)?(?:wordwall\.net|wordwall-live-staging\.azurewebsites\.net)(?:\/[a-z]{2})?\/embed\//,

    // Miro
    /^https:\/\/(?:www\.)?miro\.com\/app\/(?:live-)?embed\//,

    // Quizlet (любой тип встраиваемого модуля)
    /^https:\/\/(?:www\.)?quizlet\.com\/\d+\/[^/]+\/embed/,

    // LearningApps
    /^https:\/\/learningapps\.org\/(?:embed|watch)(?:\/|$|\?).*/,

    // Rutube
    /^https:\/\/rutube\.ru\/play\/embed\//,

    // YouTube
    /^https:\/\/(?:www\.)?youtube(?:-nocookie)?\.com\/embed\//,

    // sBoard
    /^https:\/\/sboard\.online\/boards\/[a-f0-9\-]+$/,
];

function checkEmbed(embedCode) {
    if (!embedCode) return false;

    try {
        const parser = new DOMParser();
        const doc = parser.parseFromString(embedCode, 'text/html');
        const iframe = doc.querySelector('iframe');

        if (!iframe || !iframe.src) return false;

        const src = iframe.src;
        return allowedSources.some(pattern => pattern.test(src));
    } catch (error) {
        console.warn('Ошибка разбора embed-кода:', error);
        return false;
    }
}

function autoResizeInput(input) {
  input.style.boxSizing = 'border-box';
  input.style.width = 'auto';

  const container = input.parentElement;
  const maxWidth = container.clientWidth;

  const desiredWidth = input.scrollWidth + 4;

  // Обрезаем до ширины контейнера
  const finalWidth = Math.min(desiredWidth, maxWidth);

  input.style.width = finalWidth + 'px';
}

function normalize(text, keepEmojis = false) {
    if (typeof text !== 'string') return '';

    // Замена разных типов кавычек, апострофов и похожих символов на стандартные аналоги
    const replacements = {
        // Апострофы
        '‘': "'", '’': "'", '‛': "'", 'ʼ': "'", '＇': "'", '`': "'",
        // Кавычки
        '“': '"', '”': '"', '„': '"', '‟': '"', '«': '"', '»': '"',
        // Кавычки-ёлочки
        '‹': "'", '›': "'", '❮': '"', '❯': '"',
        // Запятые
        '‚': ',', '，': ',', '､': ',',
        // Точки
        '。': '.', '．': '.', '｡': '.',
        // Дефисы и тире (замена на дефис)
        '–': '-', '—': '-', '―': '-', '‑': '-',  // включая non-breaking hyphen
        // Многоточие
        '…': '...',
        // Разные пробелы на обычный пробел
        '\u00A0': ' ', '\u2000': ' ', '\u2001': ' ', '\u2002': ' ', '\u2003': ' ', '\u2004': ' ', '\u2005': ' ', '\u2006': ' ',
        '\u2007': ' ', '\u2008': ' ', '\u2009': ' ', '\u200A': ' ', '\u202F': ' ', '\u205F': ' ', '\u3000': ' '
    };

    for (const [orig, repl] of Object.entries(replacements)) {
        const re = new RegExp(orig, 'g');
        text = text.replace(re, repl);
    }

    // Специальная замена для "won't" -> "will not"
    text = text.replace(/\bwon't\b/gi, 'will not');

    // Заменяем окончания n't на not
    text = text.replace(/n't\b/gi, ' not');

    // Обрабатываем сокращения
    text = text.replace(/\bI'm\b/gi, 'I am')
               .replace(/\b(\w+)'re\b/gi, '$1 are')
               .replace(/\b(\w+)'s\b/gi, (match, p1) => {
                   const lower = p1.toLowerCase();
                   if (['he', 'she', 'it', 'that', 'what', 'where', 'who', 'how', 'there'].includes(lower)) {
                       return p1 + ' is';
                   } else {
                       // убираем 's, если не из списка
                       return p1;
                   }
               });

    // Обрабатываем 'let's' -> 'let us'
    text = text.replace(/\blet's\b/gi, 'let us');

    // Удаление лишних символов (с учетом keepEmojis)
    if (keepEmojis) {
        // Регулярка для удаления всего кроме букв, цифр, пробелов и эмодзи
        // Эмодзи диапазоны Unicode
        const emojiPattern = /[^\w\s\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F1E0}-\u{1F1FF}\u{2700}-\u{27BF}\u{1F900}-\u{1F9FF}\u{2600}-\u{26FF}\u{2B50}]/gu;
        text = text.replace(emojiPattern, '');
    } else {
        // Удаляем всё кроме букв, цифр и пробелов
        text = text.replace(/[^\w\s]/g, '');
    }

    // Заменяем множественные пробелы одним
    text = text.replace(/\s+/g, ' ');

    // Нижний регистр и обрезка
    return text.trim().toLowerCase();
}








        // Отправка ответов

async function submitAnswer(taskId, answer, type = "fast") {
    try {
        const response = await fetch('/api/receive-answer/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                task_id: taskId,
                answer: answer,
                user_id: studentId || userId,
                type: type,
                ...(classroomId && { classroom_id: classroomId }),
            })
        });

        const data = await response.json();
        if (data.status === 'success') {
            if (mode === "classroom" || mode === "homework") {
                sendMessage('task-answer', taskId, {'answer': answer, 'isCorrect': data.isCorrect, "correct_count": data.correct_count, "incorrect_count": data.incorrect_count, "max_score": data.max_score}, 'student');
            }
            if (data.correct_count) {
                updateProgressBar(taskId, data.correct_count, data.incorrect_count, data.max_score);
            }
            if (type === "complex") {
                return data;
            }
            return data.isCorrect
        } else {
            showNotification(data.message || "Ошибка ответа", "warning");
            return false;
        }
    } catch (error) {
        showNotification("Не удалось проверить ответ.", "warning");
        return false;
    }
}

async function displayUserStats(taskId) {
    let viewedUserId = "";
    if (studentId) {
        viewedUserId = studentId;
    } else {
        viewedUserId = userId;
    }
    if (mode === 'classroom' || mode === 'homework') {
        const answersData = await fetchUserAnswers(viewedUserId, taskId, classroomId);

        const taskContainer = document.getElementById(taskId);
        if (taskContainer) {
            const taskType = taskContainer.getAttribute('data-task-type');

            if (answersData) {
                updateProgressBar(taskId, answersData.correct_answers, answersData.incorrect_answers, answersData.max_score, false);
            }

            const capitalizedTaskType = taskType.charAt(0).toUpperCase() + taskType.slice(1);
            const functionName = `fill${capitalizedTaskType}Answer`;
            console.log(functionName, typeof window[functionName] === 'function', answersData.answers_history);
            if (typeof window[functionName] === 'function') {
                answersData.answers_history.forEach(answer => {
                    console.log(answer.answer, answer.is_correct);
                    window[functionName](taskId, answer.answer, answer.is_correct, false);
                });
            }
        }
    }
}



function isTouchDevice() {
    return 'ontouchstart' in window ||
           navigator.maxTouchPoints > 0 ||
           navigator.msMaxTouchPoints > 0;
}

function clearText(input) {
    return DOMPurify.sanitize(input, {
        ALLOWED_TAGS: ["b", "i", "u", "em", "strong", "p", "br",
                       "ul", "ol", "li", "span", "div",
                       "h1", "h2", "h3", "h4", "h5", "h6"],
        ALLOWED_ATTR: ["class", "style"]
    });
}
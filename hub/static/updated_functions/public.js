// Получить данные с сервера (POST)
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

// Проверить пользовательские ответы на фронтенде
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

function sharePage() {
    if (navigator.share) {
        navigator.share({
            title: document.title,
            text: '',
            url: window.location.href
        }).catch((error) => console.log('Ошибка при шаринге:', error));
    } else {
        // Копируем ссылку в буфер обмена
        navigator.clipboard.writeText(window.location.href)
            .then(() => {
                showNotification("Ссылка скопирована!", "success");
            })
            .catch(err => {
                console.error('Ошибка копирования ссылки:', err);
                showNotification("Не удалось скопировать ссылку", "danger");
            });
    }
}

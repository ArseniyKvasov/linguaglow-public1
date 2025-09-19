const express = require('express');
const cors = require('cors');
const edgeTTS = require('edge-tts');
const { PassThrough } = require('stream');
const app = express();

app.use(cors());
app.use(express.json());

// Роут для генерации речи
app.post('/api/edge-tts', async (req, res) => {
    try {
        const { text, voice = 'en-US-JennyNeural' } = req.body;

        if (!text || text.length < 3 || text.length > 5000) {
            return res.status(400).send('Text length must be between 3 and 5000 characters');
        }

        // Создаем поток для аудио
        const audioStream = new PassThrough();

        // Генерируем речь с помощью Edge TTS
        const synthesize = edgeTTS.synthesize({
            text: text,
            voice: voice,
        });

        // Передаем аудио потоком
        for await (const chunk of synthesize) {
            audioStream.push(chunk);
        }
        audioStream.push(null); // Завершаем поток

        // Устанавливаем заголовки для аудио потока
        res.setHeader('Content-Type', 'audio/mpeg');
        res.setHeader('Content-Disposition', 'inline; filename="speech.mp3"');

        // Отправляем аудио потоком
        audioStream.pipe(res);

    } catch (error) {
        console.error('TTS Error:', error);
        res.status(500).send('Error generating speech');
    }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
});
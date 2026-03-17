document.addEventListener('DOMContentLoaded', () => {
    // Adimlar
    const stepUpload = document.getElementById('step-upload');
    const stepProcessing = document.getElementById('step-processing');
    const stepResult = document.getElementById('step-result');

    // Upload
    const uploadBox = document.getElementById('upload-box');
    const fileInput = document.getElementById('file-input');

    // Processing
    const processingFilename = document.getElementById('processing-filename');
    const progressFill = document.getElementById('progress-fill');
    const progressPercent = document.getElementById('progress-percent');
    const processingStatus = document.getElementById('processing-status');

    // Result
    const audioVocals = document.getElementById('audio-vocals');
    const audioInstrumental = document.getElementById('audio-instrumental');
    const downloadVocals = document.getElementById('download-vocals');
    const downloadInstrumental = document.getElementById('download-instrumental');
    const btnNew = document.getElementById('btn-new');

    // Gorunur adim degistir
    function showStep(step) {
        stepUpload.classList.remove('active');
        stepProcessing.classList.remove('active');
        stepResult.classList.remove('active');
        step.classList.add('active');
    }

    // Drag & Drop
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(evt => {
        uploadBox.addEventListener(evt, e => { e.preventDefault(); e.stopPropagation(); }, false);
    });
    ['dragenter', 'dragover'].forEach(evt => {
        uploadBox.addEventListener(evt, () => uploadBox.classList.add('dragover'));
    });
    ['dragleave', 'drop'].forEach(evt => {
        uploadBox.addEventListener(evt, () => uploadBox.classList.remove('dragover'));
    });

    uploadBox.addEventListener('drop', e => {
        const files = e.dataTransfer.files;
        if (files.length > 0) processFile(files[0]);
    });

    uploadBox.addEventListener('click', e => {
        if (e.target.tagName !== 'BUTTON') fileInput.click();
    });

    fileInput.addEventListener('change', e => {
        if (e.target.files.length > 0) processFile(e.target.files[0]);
    });

    // Ana islem
    async function processFile(file) {
        processingFilename.textContent = file.name;
        showStep(stepProcessing);

        // Ilerleme cubugu animasyonu
        let progress = 0;
        const interval = setInterval(() => {
            progress += 0.5;
            if (progress > 90) progress = 90;
            progressFill.style.width = progress + '%';
            progressPercent.textContent = Math.round(progress) + '%';

            if (progress < 25) processingStatus.textContent = 'Dosya sunucuya gonderiliyor...';
            else if (progress < 50) processingStatus.textContent = 'Yapay zeka sesi analiz ediyor...';
            else if (progress < 75) processingStatus.textContent = 'Vokaller ayristiriliyor...';
            else processingStatus.textContent = 'Neredeyse bitti, lutfen bekleyin...';
        }, 150);

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/separate', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();
            clearInterval(interval);

            if (!response.ok) {
                throw new Error(data.error || 'Sunucu hatasi');
            }

            // Basarili - sonuclari goster
            progressFill.style.width = '100%';
            progressPercent.textContent = '100%';
            processingStatus.textContent = 'Tamamlandi!';

            setTimeout(() => {
                // Audio player'lara kaynaklari ata
                audioVocals.src = data.vocals_url;
                audioInstrumental.src = data.instrumental_url;

                // Indirme linklerini ata
                downloadVocals.href = data.vocals_url;
                downloadInstrumental.href = data.instrumental_url;

                showStep(stepResult);
            }, 800);

        } catch (err) {
            clearInterval(interval);
            processingStatus.textContent = 'Hata: ' + err.message;
            progressFill.style.background = '#ef4444';
            progressFill.style.width = '100%';
            progressPercent.textContent = '!';

            setTimeout(() => {
                resetAll();
            }, 4000);
        }
    }

    function resetAll() {
        fileInput.value = '';
        progressFill.style.width = '0%';
        progressFill.style.background = 'linear-gradient(to right, #6366f1, #ec4899)';
        progressPercent.textContent = '0%';
        processingStatus.textContent = 'Dosya sunucuya gonderiliyor...';
        audioVocals.src = '';
        audioInstrumental.src = '';
        showStep(stepUpload);
    }

    btnNew.addEventListener('click', resetAll);
});

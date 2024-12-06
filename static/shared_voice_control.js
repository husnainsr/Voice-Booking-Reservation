function initializeVoiceControl() {
    const voiceButton = document.getElementById('voiceButton');
    const voiceStatus = document.getElementById('voiceStatus');
    let mediaRecorder;
    let audioChunks = [];

    voiceButton.addEventListener('click', async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    channelCount: 1,
                    sampleRate: 16000
                } 
            });
            
            voiceStatus.textContent = "Listening...";
            voiceButton.classList.add('btn-danger');
            voiceButton.classList.remove('btn-primary');

            let mimeType = 'audio/webm';
            if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
                mimeType = 'audio/webm;codecs=opus';
            }

            mediaRecorder = new MediaRecorder(stream, {
                mimeType: mimeType,
                audioBitsPerSecond: 16000
            });
            
            audioChunks = [];

            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunks.push(event.data);
                }
            };

            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: mimeType });
                const formData = new FormData();
                formData.append('audio', audioBlob, 'recording.webm');

                try {
                    voiceStatus.textContent = "Processing...";
                    const response = await fetch('/process-voice', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const result = await response.json();
                    handleVoiceResponse(result, voiceStatus);

                } catch (error) {
                    console.error('Error:', error);
                    voiceStatus.textContent = "Error processing command";
                }

                voiceButton.classList.remove('btn-danger');
                voiceButton.classList.add('btn-primary');
            };

            mediaRecorder.start();
            console.log("Recording started...");

            setTimeout(() => {
                mediaRecorder.stop();
                stream.getTracks().forEach(track => track.stop());
                console.log("Recording stopped");
            }, 3000);

        } catch (error) {
            console.error('Error:', error);
            voiceStatus.textContent = "Error accessing microphone";
        }
    });
} 

import time
import streamlit as st
import os
import uuid
import requests
import assemblyai as aai
import base64
import streamlit.components.v1 as components
import shutil
from openai import OpenAI

# ========= CONFIG =========


ASSEMBLYAI_API_KEY = st.secrets.get("ASSEMBLYAI_API_KEY")
FPT_API_KEY = st.secrets.get("FPT_API_KEY")
FPT_TTS_URL = st.secrets.get("FPT_TTS_URL")
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)


# ========= UTILS =========
def generate_session_id():
    return str(uuid.uuid4())


def rfile(name_file):
    try:
        with open(name_file, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        st.error(f"File {name_file} không tồn tại.")


# ======== AUDIO RECORDER COMPONENT ========
def gencomponent(name, template="", script=""):
    def html():
        return f"""
            <!DOCTYPE html>
            <html lang="en">
                <head>
                    <meta charset="UTF-8" />
                    <title>{name}</title>
                    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css" crossorigin="anonymous"/>
                    <style>
                        body {{
                            background-color: transparent;
                            margin: 0;
                            padding: 0;
                        }}
                        #toggleBtn {{
                            padding: 10px 20px;
                            border-radius: 4px;
                            border: none;
                            cursor: pointer;
                            color: #282828;
                            font-size: 16px;
                        }}
                        #toggleBtn.recording {{
                            background-color: red;
                        }}
                    </style>
                    <script>
                        function sendMessageToStreamlitClient(type, data) {{
                            const outData = Object.assign({{
                                isStreamlitMessage: true,
                                type: type,
                            }}, data);
                            window.parent.postMessage(outData, "*");
                        }}

                        const Streamlit = {{
                            setComponentReady: function() {{
                                sendMessageToStreamlitClient("streamlit:componentReady", {{apiVersion: 1}});
                            }},
                            setFrameHeight: function(height) {{
                                sendMessageToStreamlitClient("streamlit:setFrameHeight", {{height: height}});
                            }},
                            setComponentValue: function(value) {{
                                sendMessageToStreamlitClient("streamlit:setComponentValue", {{value: value}});
                            }},
                            RENDER_EVENT: "streamlit:render",
                            events: {{
                                addEventListener: function(type, callback) {{
                                    window.addEventListener("message", function(event) {{
                                        if (event.data.type === type) {{
                                            event.detail = event.data
                                            callback(event);
                                        }}
                                    }});
                                }}
                            }}
                        }}
                    </script>
                </head>
                <body>
                    {template}
                </body>
                <script src="https://unpkg.com/hark@1.2.0/hark.bundle.js"></script>
                <script>
                    {script}
                </script>
            </html>
        """

    dir = f"{os.getcwd()}/temp_component/{name}"
    os.makedirs(dir, exist_ok=True)
    fname = f'{dir}/index.html'
    with open(fname, 'w', encoding='utf-8') as f:
        f.write(html())
    func = components.declare_component(name, path=str(dir))
    def f(**params):
        component_value = func(**params)
        return component_value
    return f


template = """<button id="toggleBtn"><i class="fa-solid fa-microphone fa-lg" ></i> Bấm để nói</button>"""

script = """
    let mediaStream = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let speechEvents = null;
    let silenceTimeout = null;
    let isRecording = false;
    const toggleBtn = document.getElementById('toggleBtn');
    
    Streamlit.setComponentReady();
    Streamlit.setFrameHeight(60);
    
    function blobToBase64(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => {
                const base64String = reader.result.split(',')[1];
                resolve(base64String);
            };
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    }
    
    async function handleRecordingStopped() {
        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        const base64Data = await blobToBase64(audioBlob);
        
        Streamlit.setComponentValue({
            audioData: base64Data,
            status: 'stopped',
            timestamp: Date.now()
        });
    }
    
    function onRender(event) {
        const args = event.detail.args;
        window.harkConfig = {
            interval: args.interval || 50,
            threshold: args.threshold || -60,
            play: args.play !== undefined ? args.play : false,
            silenceTimeout: args.silenceTimeout || 1500
        };
    }
    
    Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender);
    
    toggleBtn.addEventListener('click', async () => {
        if (!isRecording) {
            try {
                mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(mediaStream, { mimeType: 'audio/webm' });
                audioChunks = [];
                
                mediaRecorder.ondataavailable = event => {
                    if (event.data.size > 0) {
                        audioChunks.push(event.data);
                    }
                };
                
                mediaRecorder.onstop = () => {
                    handleRecordingStopped().catch(err => {
                        console.error('Error handling recording:', err);
                        Streamlit.setComponentValue({
                            error: 'Failed to process recording',
                            timestamp: Date.now()
                        });
                    });
                };
                
                speechEvents = hark(mediaStream, {
                    interval: window.harkConfig.interval,
                    threshold: window.harkConfig.threshold,
                    play: window.harkConfig.play
                });
                
                speechEvents.on('stopped_speaking', () => {
                    silenceTimeout = setTimeout(() => {
                        if (mediaRecorder && mediaRecorder.state === 'recording') {
                            mediaRecorder.stop();
                        }
                    }, window.harkConfig.silenceTimeout);
                });
                
                speechEvents.on('speaking', () => {
                    if (silenceTimeout) {
                        clearTimeout(silenceTimeout);
                        silenceTimeout = null;
                    }
                });
                
                mediaRecorder.start();
                isRecording = true;
                toggleBtn.classList.add('recording');
                toggleBtn.innerHTML = '<i class="fa-solid fa-stop fa-lg" ></i> Dừng';
                
            } catch (err) {
                console.error('Error accessing microphone:', err);
                Streamlit.setComponentValue({
                    error: err.message,
                    timestamp: Date.now()
                });
                audioChunks = [];
            }
        } else {
            isRecording = false;
            toggleBtn.classList.remove('recording');
            toggleBtn.innerHTML = '<i class="fa-solid fa-microphone fa-lg" ></i> Bấm để nói';
            
            if (speechEvents) {
                speechEvents.stop();
                speechEvents = null;
            }
            
            if (silenceTimeout) {
                clearTimeout(silenceTimeout);
                silenceTimeout = null;
            }
            
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                mediaRecorder.stop();
            }
            
            if (mediaStream) {
                mediaStream.getTracks().forEach(track => track.stop());
                mediaStream = null;
            }
        }
    });
"""

def audio_recorder(interval=50, threshold=-60, play=False, silenceTimeout=1500, key=None):
    component_func = gencomponent('configurable_audio_recorder', template=template, script=script)
    return component_func(interval=interval, threshold=threshold, play=play, silenceTimeout=silenceTimeout, key=key)


# ========= AUDIO FUNCTIONS =========
def generate_fpt_audio(text, voice):
    headers = {"api-key": FPT_API_KEY, "voice": voice, "format": "mp3"}
    try:
        response = requests.post(FPT_TTS_URL, headers=headers, data=text.encode('utf-8'))
        response.raise_for_status()
        data = response.json()
        if data.get("error") == 0 and "async" in data:
            url = data["async"]
            for _ in range(5):
                check = requests.head(url)
                if check.status_code == 200:
                    return url
                time.sleep(1.5)
            return None
        else:
            return None
    except Exception as e:
        print(f"❌ Error generating audio with FPT.AI: {e}")
        return None


def send_message_to_llm(session_id, message):
    payload = {"sessionId": session_id, "chatInput": message}
    try:
        response = requests.post( json=payload)
        response.raise_for_status()
        response_data = response.json()
        contract = response_data.get('output', "No contract received")
        url = response_data.get('url', "No URL received")
        north_audio = generate_fpt_audio(contract, "lannhi")
        south_audio = generate_fpt_audio(contract, "banmai")
        audio_urls = {}
        if north_audio: audio_urls["north"] = north_audio
        if south_audio: audio_urls["south"] = south_audio
        return [{"json": {"contract": contract, "url": url, "audio": audio_urls}}]
    except requests.exceptions.RequestException as e:
        return [{"json": {"contract": f"Error: {str(e)}", "url": "", "audio": {}}}]


def transcribe_audio(audio_bytes, mode="assembly"):
    temp_dir = os.path.join(os.getcwd(), "temp_audio")
    os.makedirs(temp_dir, exist_ok=True)

    if mode == "assembly":
        aai.settings.api_key = ASSEMBLYAI_API_KEY
        transcriber = aai.Transcriber()
        temp_webm_path = os.path.join(temp_dir, f"audio_{uuid.uuid4()}.webm")
        try:
            with open(temp_webm_path, 'wb') as f:
                f.write(audio_bytes)
            config = aai.TranscriptionConfig(language_code="vi")
            transcript = transcriber.transcribe(temp_webm_path, config=config)
            if transcript.status == aai.TranscriptStatus.error:
                return f"Lỗi khi chuyển đổi giọng nói: {transcript.error}"
            return transcript.text or "Không thể nhận diện giọng nói. Vui lòng thử lại."
        finally:
            if os.path.exists(temp_webm_path):
                os.remove(temp_webm_path)

    elif mode == "whisper":
        temp_mp3_path = os.path.join(temp_dir, f"audio_{uuid.uuid4()}.mp3")
        try:
            print("🎤 Đang dùng OpenAI Whisper để nhận diện giọng nói...")
            st.info("🎤 Đang dùng **OpenAI Whisper** để nhận diện giọng nói...")
            with open(temp_mp3_path, "wb") as f:
                f.write(audio_bytes)
            with open(temp_mp3_path, "rb") as f:
                transcript = openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="text",
                    language="vi"
                )
            return transcript.strip()
        finally:
            if os.path.exists(temp_mp3_path):
                os.remove(temp_mp3_path)


def display_output(output):
    contract = output.get('json', {}).get('contract')
    audio_urls = output.get('json', {}).get('audio', {})

    if contract and contract.strip():
        st.markdown(f"""<div class="assistant">🤖 {contract}</div>""", unsafe_allow_html=True)

    if audio_urls and isinstance(audio_urls, dict):
        st.markdown('<div class="assistant"><div class="audio-container">', unsafe_allow_html=True)
        if audio_urls.get('north'):
            st.markdown('<div class="audio-item"><div class="audio-label">🎵 Giọng miền Nam (Lan Nhi)</div>', unsafe_allow_html=True)
            st.audio(audio_urls['north'], format="audio/mp3")
            st.markdown('</div>', unsafe_allow_html=True)
        if audio_urls.get('south'):
            st.markdown('<div class="audio-item"><div class="audio-label">🎵 Giọng miền Bắc (Ban Mai)</div>', unsafe_allow_html=True)
            st.audio(audio_urls['south'], format="audio/mp3")
            st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div></div>', unsafe_allow_html=True)


def process_audio_input(audio_data, mode="assembly"):
    try:
        audio_bytes = base64.b64decode(audio_data["audioData"])
        st.audio(audio_bytes, format="audio/webm")
        with st.spinner("Đang chuyển giọng nói thành văn bản..."):
            transcript = transcribe_audio(audio_bytes, mode=mode)
        with st.spinner("Đang chờ phản hồi từ AI..."):
            llm_response = send_message_to_llm(st.session_state.session_id, transcript)
        return transcript, llm_response[0]
    except Exception as e:
        st.error(f"Lỗi xử lý audio: {e}")
        return None, None


def reset_conversation():
    st.session_state.messages = []
    for key in ["audio_data", "last_audio_timestamp", "processing_audio", "previous_audio_data"]:
        if key in st.session_state: del st.session_state[key]
    for d in ["temp_audio", "temp_component"]:
        path = os.path.join(os.getcwd(), d)
        if os.path.exists(path): shutil.rmtree(path)
    st.session_state.session_id = generate_session_id()
    st.session_state.component_key = str(uuid.uuid4())
    st.cache_data.clear()
    st.cache_resource.clear()


# ========= MAIN =========
def main():
    st.set_page_config(page_title="Trợ Lý AI", page_icon="🤖", layout="centered")

    # UI Style
    st.markdown("""
        <style>
            .assistant {
                padding: 10px;
                border-radius: 10px;
                max-width: 75%;
                text-align: left;
            }
            .user {
                padding: 10px;
                border-radius: 10px;
                max-width: 75%;
                text-align: right;
                margin-left: auto;
            }
            .voice-mode {
                margin-top: 20px;
                margin-bottom: 10px;
            }
            .stRadio > div {
                display: flex !important;
                flex-direction: row !important;
                gap: 14px;
                align-items: center;
            }
            .stRadio > div > label {
                padding: 6px 12px;
                border-radius: 16px;
                border: 1px solid #e5e7eb;
                background: #f8fafc;
                cursor: pointer;
            }
            .stRadio > div > label[data-checked="true"] {
                background: #3b82f6;
                color: white;
                border-color: #3b82f6;
            }
            .audio-container {
                display: flex;
                gap: 15px;
                margin: 10px 0;
                flex-wrap: wrap;
            }
            .audio-item {
                flex: 1;
                min-width: 200px;
            }
            .audio-label {
                font-size: 14px;
                font-weight: 500;
                margin-bottom: 5px;
            }
            @media (max-width: 520px) {
                .voice-mode h3 { font-size: 16px; }
            }
        </style>
    """, unsafe_allow_html=True)

    # Logo
    try:
        col1, col2, col3 = st.columns([3, 2, 3])
        with col2: st.image("logo.png")
    except: pass

    # Title
    try:
        with open("00.xinchao.txt", "r", encoding="utf-8") as file:
            title_content = file.read()
    except: title_content = "Trợ Lý AI"
    st.markdown(f"""<h1 style="text-align: center; font-size: 24px;">{title_content}</h1>""", unsafe_allow_html=True)

    # Session init
    if "messages" not in st.session_state: st.session_state.messages = []
    if "session_id" not in st.session_state: st.session_state.session_id = generate_session_id()
    if "component_key" not in st.session_state: st.session_state.component_key = str(uuid.uuid4())
    if "last_audio_timestamp" not in st.session_state: st.session_state.last_audio_timestamp = None
    if "processing_audio" not in st.session_state: st.session_state.processing_audio = False

    # Voice mode
    st.markdown('<div class="voice-mode">', unsafe_allow_html=True)
    st.markdown("### 🎤 Voice mode")
    voice_option = st.radio("Chọn chế độ nhận diện giọng nói", ("Nói -> Text (miễn phí)", "Nói -> Text (Whisper/OpenAI)"), index=0)

    audio_data = audio_recorder(
        interval=50, threshold=-60, play=False, silenceTimeout=1500,
        key=f"audio_recorder_{st.session_state.component_key}"
    )

    if (audio_data and isinstance(audio_data, dict) and "audioData" in audio_data and not st.session_state.processing_audio):
        current_timestamp = audio_data.get("timestamp")
        if current_timestamp != st.session_state.last_audio_timestamp:
            st.session_state.processing_audio = True
            st.session_state.last_audio_timestamp = current_timestamp
            mode = "assembly" if voice_option == "Nói -> Text (miễn phí)" else "whisper"
            transcript, llm_response = process_audio_input(audio_data, mode=mode)
            if transcript and llm_response:
                st.session_state.messages.append({"role": "user", "content": transcript})
                st.session_state.messages.append({"role": "assistant", "content": llm_response})
                st.session_state.processing_audio = False
                st.rerun()
            else:
                st.session_state.processing_audio = False
    elif audio_data and "error" in audio_data:
        st.error(f"Lỗi ghi âm: {audio_data['error']}")

    # Reset button
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🗑️ Xóa hết", help="Xóa lịch sử chat", type="primary"):
            reset_conversation()
            st.success("✅ Đã xóa hết!")
            st.rerun()

    # Render messages
    for message in st.session_state.messages:
        if message["role"] == "user":
            st.markdown(f'<div class="user">{message["content"]}</div>', unsafe_allow_html=True)
        elif message["role"] == "assistant":
            display_output(message["content"])

    # Chat input
    if prompt := st.chat_input("Nhập nội dung cần trao đổi ở đây nhé?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.spinner("Đang chờ phản hồi từ AI..."):
            llm_response = send_message_to_llm(st.session_state.session_id, prompt)
        st.session_state.messages.append({"role": "assistant", "content": llm_response[0]})
        st.rerun()


if __name__ == "__main__":
    main()

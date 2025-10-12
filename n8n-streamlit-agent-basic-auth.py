import time
import streamlit as st
import os
import uuid
import base64
import streamlit.components.v1 as components
import shutil
from openai import OpenAI

# ========= CONFIG =========
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# ========= UTILS =========
def generate_session_id():
    return str(uuid.uuid4())

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
                            padding: 12px 24px;
                            border-radius: 8px;
                            border: none;
                            cursor: pointer;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                            font-size: 16px;
                            font-weight: 600;
                            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
                            transition: all 0.3s ease;
                        }}
                        #toggleBtn:hover {{
                            transform: translateY(-2px);
                            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
                        }}
                        #toggleBtn.recording {{
                            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                            animation: pulse 1.5s infinite;
                        }}
                        @keyframes pulse {{
                            0%, 100% {{ box-shadow: 0 4px 15px rgba(245, 87, 108, 0.4); }}
                            50% {{ box-shadow: 0 4px 25px rgba(245, 87, 108, 0.8); }}
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
                toggleBtn.innerHTML = '<i class="fa-solid fa-stop fa-lg" ></i> Dừng ghi âm';
                
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

# ========= OPENAI FUNCTIONS =========
def generate_openai_audio(text):
    """Generate audio using OpenAI TTS"""
    try:
        response = openai_client.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=text
        )
        
        temp_dir = os.path.join(os.getcwd(), "temp_audio")
        os.makedirs(temp_dir, exist_ok=True)
        audio_path = os.path.join(temp_dir, f"tts_{uuid.uuid4()}.mp3")
        
        response.stream_to_file(audio_path)
        return audio_path
    except Exception as e:
        print(f"❌ Error generating audio with OpenAI TTS: {e}")
        return None

def chat_with_openai(message, conversation_history):
    """Chat directly with OpenAI"""
    try:
        messages = conversation_history + [{"role": "user", "content": message}]
        
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        
        assistant_message = response.choices[0].message.content
        audio_path = generate_openai_audio(assistant_message)
        
        return {"contract": assistant_message, "audio_path": audio_path}
    except Exception as e:
        return {"contract": f"Lỗi: {str(e)}", "audio_path": None}

def transcribe_audio(audio_bytes):
    temp_dir = os.path.join(os.getcwd(), "temp_audio")
    os.makedirs(temp_dir, exist_ok=True)
    temp_mp3_path = os.path.join(temp_dir, f"audio_{uuid.uuid4()}.mp3")
    
    try:
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
    contract = output.get('contract')
    audio_path = output.get('audio_path')

    if contract and contract.strip():
        st.markdown(f"""<div class="assistant">🤖 {contract}</div>""", unsafe_allow_html=True)

    if audio_path and os.path.exists(audio_path):
        st.audio(audio_path, format="audio/mp3")

def process_audio_input(audio_data):
    try:
        audio_bytes = base64.b64decode(audio_data["audioData"])
        st.audio(audio_bytes, format="audio/webm")
        
        with st.spinner("🎤 Đang nhận diện giọng nói..."):
            transcript = transcribe_audio(audio_bytes)
        
        # Get conversation history for context
        conversation_history = []
        for msg in st.session_state.messages:
            if msg["role"] == "user":
                conversation_history.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                conversation_history.append({"role": "assistant", "content": msg["content"].get("contract", "")})
        
        with st.spinner("🤖 Đang suy nghĩ..."):
            response = chat_with_openai(transcript, conversation_history)
        
        return transcript, response
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
    st.session_state.component_key = str(uuid.uuid4())
    st.cache_data.clear()
    st.cache_resource.clear()

# ========= MAIN =========
def main():
    st.set_page_config(page_title="Trợ Lý AI", page_icon="🤖", layout="centered")

    # UI Style
    st.markdown("""
        <style>
        
            
            /* Messages */
            .assistant {
                background: rgba(255, 255, 255, 0.95);
                backdrop-filter: blur(10px);
                padding: 16px 22px;
                border-radius: 20px;
                max-width: 75%;
                text-align: left;
                margin: 12px 0;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.12);
                color: #1a202c;
                font-size: 15px;
                line-height: 1.6;
                border-left: 5px solid #667eea;
            }
            
            .user {
                padding: 16px 22px;
                border-radius: 20px;
                max-width: 75%;
                text-align: right;
                margin: 12px 0 12px auto;
                font-size: 15px;
                line-height: 1.6;
            }
            
            /* Voice mode section */
            .voice-mode {
                margin-top: 20px;
                margin-bottom: 10px;
                display: flex;
                justify-content: flex-end;
            }
            
            /* Reset button */
            .stButton > button {
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%) !important;
                color: white !important;
                border: none !important;
                border-radius: 10px;
                padding: 10px 20px;
                font-weight: 600;
                box-shadow: 0 4px 15px rgba(245, 87, 108, 0.4);
                transition: all 0.3s ease;
            }
            
            .stButton > button:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(245, 87, 108, 0.5);
            }
            
            /* Title */
            h1 {
                
                font-weight: 700;
            }
            
            /* Audio player */
            audio {
                width: 100%;
                margin-top: 10px;
                border-radius: 10px;
            }
            
            /* Spinner */
            .stSpinner > div {
                border-top-color: white !important;
            }
            
            /* Success message */
            .stSuccess {
                background: rgba(255, 255, 255, 0.95);
                backdrop-filter: blur(10px);
                border-radius: 10px;
                border-left: 4px solid #48bb78;
            }
            
            /* Error message */
            .stError {
                background: rgba(255, 255, 255, 0.95);
                backdrop-filter: blur(10px);
                border-radius: 10px;
                border-left: 4px solid #f56565;
            }
            
            @media (max-width: 520px) {
                .assistant, .user {
                    max-width: 85%;
                    font-size: 14px;
                }
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
    if "component_key" not in st.session_state: st.session_state.component_key = str(uuid.uuid4())
    if "last_audio_timestamp" not in st.session_state: st.session_state.last_audio_timestamp = None
    if "processing_audio" not in st.session_state: st.session_state.processing_audio = False

    # Reset button
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🗑️ Xóa hết", help="Xóa lịch sử chat"):
            reset_conversation()
            st.success("✅ Đã xóa hết!")
            st.rerun()

    # Render messages
    for message in st.session_state.messages:
        if message["role"] == "user":
            st.markdown(f'<div class="user">{message["content"]}</div>', unsafe_allow_html=True)
        elif message["role"] == "assistant":
            display_output(message["content"])

    # Voice recorder ở dưới cùng, căn phải
    st.markdown('<div class="voice-mode">', unsafe_allow_html=True)
    
    _, col_right = st.columns([3, 1])
    with col_right:
        audio_data = audio_recorder(
            interval=50, threshold=-60, play=False, silenceTimeout=1500,
            key=f"audio_recorder_{st.session_state.component_key}"
        )

    st.markdown('</div>', unsafe_allow_html=True)

    # Process audio
    if (audio_data and isinstance(audio_data, dict) and "audioData" in audio_data and not st.session_state.processing_audio):
        current_timestamp = audio_data.get("timestamp")
        if current_timestamp != st.session_state.last_audio_timestamp:
            st.session_state.processing_audio = True
            st.session_state.last_audio_timestamp = current_timestamp
            transcript, response = process_audio_input(audio_data)
            if transcript and response:
                st.session_state.messages.append({"role": "user", "content": transcript})
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.session_state.processing_audio = False
                st.rerun()
            else:
                st.session_state.processing_audio = False
    elif audio_data and "error" in audio_data:
        st.error(f"Lỗi ghi âm: {audio_data['error']}")

    # Chat input
    if prompt := st.chat_input("Nhập nội dung cần trao đổi ở đây nhé?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        conversation_history = []
        for msg in st.session_state.messages[:-1]:
            if msg["role"] == "user":
                conversation_history.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                conversation_history.append({"role": "assistant", "content": msg["content"].get("contract", "")})
        
        with st.spinner("🤖 Đang suy nghĩ..."):
            response = chat_with_openai(prompt, conversation_history)
        
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()

if __name__ == "__main__":
    main()
"""
Web UI для чата с AI-менеджером турагентства
Flask + Server-Sent Events для streaming
"""

import asyncio
import os
from datetime import datetime
from flask import Flask, render_template, request, Response, jsonify, stream_with_context
from flask_cors import CORS
from yandex_handler import YandexGPTHandler
import json
import queue
import threading

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# === ЛОГИРОВАНИЕ ===
import sys
def log(msg, level="INFO"):
    """Красивый лог с цветами"""
    colors = {
        "INFO": "\033[94m",    # синий
        "OK": "\033[92m",      # зелёный
        "WARN": "\033[93m",    # жёлтый
        "ERROR": "\033[91m",   # красный
        "MSG": "\033[95m",     # фиолетовый
        "FUNC": "\033[96m",    # голубой
    }
    reset = "\033[0m"
    time_str = datetime.now().strftime("%H:%M:%S")
    color = colors.get(level, "")
    print(f"{color}[{time_str}] [{level}] {msg}{reset}", flush=True)
    sys.stdout.flush()

# Глобальный handler (для простоты — один на всех, в production нужно по сессиям)
handlers = {}

def get_handler(session_id: str) -> YandexGPTHandler:
    """Получить или создать handler для сессии"""
    if session_id not in handlers:
        handlers[session_id] = YandexGPTHandler()
    return handlers[session_id]


@app.route('/')
def index():
    """Главная страница с чатом"""
    return render_template('chat.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    """Обычный chat без streaming"""
    data = request.json
    message = data.get('message', '')
    session_id = data.get('session_id', 'default')
    
    if not message:
        return jsonify({'error': 'Empty message'}), 400
    
    handler = get_handler(session_id)
    
    try:
        # Запускаем async функцию
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        response = loop.run_until_complete(handler.chat(message))
        loop.close()
        
        return jsonify({'response': response})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    """Chat со streaming через SSE"""
    data = request.json
    message = data.get('message', '')
    session_id = data.get('session_id', 'default')
    
    log(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "INFO")
    log(f"📨 Новое сообщение от {session_id[:8]}...", "MSG")
    log(f"   └─ \"{message[:100]}{'...' if len(message) > 100 else ''}\"", "MSG")
    
    if not message:
        log("❌ Пустое сообщение!", "ERROR")
        return jsonify({'error': 'Empty message'}), 400
    
    handler = get_handler(session_id)
    log(f"📊 Модель: {handler.model}", "INFO")
    log(f"📊 История: {len(handler.input_list)} сообщений", "INFO")
    
    def generate():
        token_queue = queue.Queue()
        result = {'response': '', 'error': None}
        token_count = [0]  # Счётчик токенов
        
        def on_token(token):
            token_queue.put(('token', token))
            token_count[0] += 1
        
        def run_chat():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                log("🚀 Отправляю запрос в YandexGPT...", "INFO")
                response = loop.run_until_complete(
                    handler.chat_stream(message, on_token=on_token)
                )
                loop.close()
                result['response'] = response
                log(f"✅ Ответ получен: {len(response)} символов, {token_count[0]} токенов", "OK")
                log(f"   └─ \"{response[:150]}{'...' if len(response) > 150 else ''}\"", "OK")
                token_queue.put(('done', response))
            except Exception as e:
                result['error'] = str(e)
                log(f"❌ ОШИБКА: {e}", "ERROR")
                token_queue.put(('error', str(e)))
        
        # Запускаем в отдельном потоке
        thread = threading.Thread(target=run_chat)
        thread.start()
        
        # Стримим токены
        while True:
            try:
                event_type, data = token_queue.get(timeout=60)
                
                if event_type == 'token':
                    yield f"data: {json.dumps({'type': 'token', 'content': data})}\n\n"
                elif event_type == 'done':
                    yield f"data: {json.dumps({'type': 'done', 'content': data})}\n\n"
                    break
                elif event_type == 'error':
                    yield f"data: {json.dumps({'type': 'error', 'content': data})}\n\n"
                    break
            except queue.Empty:
                log("⏳ Таймаут ожидания...", "WARN")
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        
        thread.join()
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/api/reset', methods=['POST'])
def reset():
    """Сбросить историю диалога"""
    data = request.json or {}
    session_id = data.get('session_id', 'default')
    
    if session_id in handlers:
        handlers[session_id].reset()
        log(f"🔄 Сессия {session_id[:8]}... сброшена", "WARN")
    
    return jsonify({'status': 'ok'})


@app.route('/api/status')
def status():
    """Статус сервера"""
    return jsonify({
        'status': 'running',
        'sessions': len(handlers)
    })


if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()
    
    model = os.getenv("YANDEX_MODEL", "yandexgpt")
    folder = os.getenv("YANDEX_FOLDER_ID", "???")
    
    print("\n" + "="*50)
    print("🚀 AI ТУРМЕНЕДЖЕР - Web UI")
    print("="*50)
    print(f"📍 URL: http://localhost:8080")
    print(f"🤖 Модель: {model}")
    print(f"📁 Folder: {folder[:8]}...")
    print("="*50 + "\n")
    
    app.run(host='0.0.0.0', port=8080, debug=True, threaded=True)

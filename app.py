from flask import Flask, request, jsonify
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from flask_cors import CORS

from locali import LocalI
from config import DEFAULT_API_URL, DEFAULT_MODEL_NAME_1B, DEFAULT_MODEL_NAME_3B

app = Flask(__name__)
CORS(app)

@app.route('/api/select_model', methods=['POST'])
def select_model():
    data = request.json
    model_param = data.get('model_param')
    if model_param == "1B":
        model_name = DEFAULT_MODEL_NAME_1B
    elif model_param == "3B":
        model_name = DEFAULT_MODEL_NAME_3B
    else:
        return jsonify({"error": "Invalid model parameter"}), 400

    return jsonify({"model_name": model_name})

@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    model_name = data.get('model_name')
    user_input = data.get('user_input')

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(generate_text(model_name, user_input))
    return jsonify({"response": result})

async def generate_text(model_name, user_input):
    api_url = DEFAULT_API_URL
    async with LocalI(model_name, api_url) as assistant:
        response = ""
        async for text_chunk in assistant.generate_text(user_input):
            response += text_chunk
        return response

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(debug=True)
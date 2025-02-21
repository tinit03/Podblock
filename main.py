
from flask import Flask, request, jsonify, send_file
from dotenv import load_dotenv, find_dotenv
from flask_cors import CORS
from config import Config
from routes import audio_bp
app = Flask(__name__)
app.config.from_object(Config)
app.register_blueprint(audio_bp)
CORS(app)
if __name__ == '__main__':
    app.run(host='0.0.0.0')

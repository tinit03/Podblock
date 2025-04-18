from flask import Flask
from flask_cors import CORS
from config import Config
from router import audio_bp
from helpers import url_helpers
import redis

app = Flask(__name__)
app.config.from_object(Config)
app.register_blueprint(audio_bp)
CORS(app)
if __name__ == '__main__':
    app.run(host='0.0.0.0',
            port=5000,
            debug=False,
            use_reloader=False)

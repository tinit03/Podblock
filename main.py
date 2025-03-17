from flask import Flask
from flask_cors import CORS
from config import Config
from router import audio_bp
from helpers.cache_helpers import setup_cache
from helpers import url_helpers
import redis

app = Flask(__name__)
app.config.from_object(Config)
app.register_blueprint(audio_bp)
redis_client = redis.Redis(host='127.0.0.1', port=6379, db=0)
setup_cache(app, redis_client)
CORS(app)
if __name__ == '__main__':
    app.run(host='0.0.0.0')

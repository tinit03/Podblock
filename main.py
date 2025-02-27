from flask import Flask
from flask_cors import CORS
from config import Config
from routes import audio_bp
from cache_helpers import setup_cache
import redis

app = Flask(__name__)
app.config.from_object(Config)
app.register_blueprint(audio_bp)
redis_client = redis.Redis(host='localhost', port=6379, db=0)
setup_cache(app)
CORS(app)
if __name__ == '__main__':
    app.run(host='0.0.0.0')

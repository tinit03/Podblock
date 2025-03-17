import os

class Config:
    """Application Configuration Class"""
    UPLOAD_FOLDER = './uploads'
    CACHE_TYPE = 'redis'
    CACHE_REDIS_HOST = 'localhost'
    CACHE_REDIS_PORT = 6379
    CACHE_REDIS_DB = 0
    REDIS_URL = "redis://localhost:6379/0"

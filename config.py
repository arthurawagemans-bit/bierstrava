import os
import secrets

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Generate a random key if none is set (safe for dev, logs a warning)
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    # Use DATABASE_URL env var if set, otherwise default to local ~/.bierstrava/
    _default_db = os.path.join(os.path.expanduser('~'), '.bierstrava', 'bierstrava.db')
    _db_path = os.environ.get('DATABASE_PATH', _default_db)
    os.makedirs(os.path.dirname(_db_path), exist_ok=True)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + _db_path
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB max upload
    POSTS_PER_PAGE = 20
    LEADERBOARD_PER_PAGE = 50
    # Rate limiting defaults
    RATELIMIT_STORAGE_URI = 'memory://'
    RATELIMIT_DEFAULT = '200 per minute'

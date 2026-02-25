import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Secret key: MUST set SECRET_KEY env var on Railway
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Database: use DATABASE_PATH env var or default to local path
    # On Railway, set DATABASE_PATH=/data/bierstrava.db (persistent volume)
    # Locally, defaults to ~/.veau/veau.db
    _default_db = os.path.join(os.path.expanduser('~'), '.veau', 'veau.db')
    _db_path = os.environ.get('DATABASE_PATH', _default_db)
    _db_dir = os.path.dirname(_db_path)
    if _db_dir:
        os.makedirs(_db_dir, exist_ok=True)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + _db_path
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Uploads: use UPLOAD_FOLDER env var or default to app/static/uploads
    # On Railway, set UPLOAD_FOLDER=/app/data/uploads (persistent volume)
    UPLOAD_FOLDER = os.environ.get(
        'UPLOAD_FOLDER',
        os.path.join(basedir, 'app', 'static', 'uploads')
    )
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB max upload

    # Pagination
    POSTS_PER_PAGE = 20
    LEADERBOARD_PER_PAGE = 50

    # Backup: set BACKUP_SECRET env var to enable the /api/backup endpoint
    BACKUP_SECRET = os.environ.get('BACKUP_SECRET', '')

    # Rate limiting
    RATELIMIT_STORAGE_URI = 'memory://'
    RATELIMIT_DEFAULT = '200 per minute'

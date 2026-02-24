import os
import logging
from flask import Flask, render_template, jsonify, request
from .extensions import db, login_manager, csrf, limiter
from config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # ── Logging ──────────────────────────────────────────
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    logger = logging.getLogger('bierstrava')

    # Warn if using default secret key
    if app.config['SECRET_KEY'] == 'dev-secret-key-change-in-production':
        logger.warning('⚠️  Using default SECRET_KEY — set SECRET_KEY env var for production!')

    # ── Extensions ───────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ── Blueprints ───────────────────────────────────────
    from .auth import bp as auth_bp
    from .main import bp as main_bp
    from .posts import bp as posts_bp
    from .groups import bp as groups_bp
    from .profiles import bp as profiles_bp
    from .leaderboard import bp as leaderboard_bp
    from .search import bp as search_bp
    from .settings import bp as settings_bp
    from .api import bp as api_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)
    app.register_blueprint(posts_bp, url_prefix='/posts')
    app.register_blueprint(groups_bp, url_prefix='/groups')
    app.register_blueprint(profiles_bp)
    app.register_blueprint(leaderboard_bp, url_prefix='/leaderboard')
    app.register_blueprint(search_bp, url_prefix='/search')
    app.register_blueprint(settings_bp, url_prefix='/settings')
    app.register_blueprint(api_bp, url_prefix='/api')

    # ── Template filters ─────────────────────────────────
    from .template_filters import timeago, format_time, render_mentions
    app.jinja_env.filters['timeago'] = timeago
    app.jinja_env.filters['format_time'] = format_time
    app.jinja_env.filters['render_mentions'] = render_mentions

    # ── Context processor (optimised: single query) ──────
    @app.context_processor
    def inject_notifications():
        from flask_login import current_user as cu
        if cu.is_authenticated:
            from .models import GroupMember, GroupJoinRequest
            count = db.session.query(db.func.count(GroupJoinRequest.id)).join(
                GroupMember,
                db.and_(
                    GroupMember.group_id == GroupJoinRequest.group_id,
                    GroupMember.user_id == cu.id,
                    GroupMember.role == 'admin',
                )
            ).filter(
                GroupJoinRequest.status == 'pending'
            ).scalar() or 0
            return {'group_notification_count': count}
        return {'group_notification_count': 0}

    # ── Error handlers ───────────────────────────────────
    @app.errorhandler(404)
    def not_found_error(error):
        if request.path.startswith('/api/'):
            return jsonify(error='Not found'), 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden_error(error):
        if request.path.startswith('/api/'):
            return jsonify(error='Forbidden'), 403
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        logger.error('Internal server error: %s', error)
        if request.path.startswith('/api/'):
            return jsonify(error='Internal server error'), 500
        return render_template('errors/500.html'), 500

    @app.errorhandler(429)
    def ratelimit_error(error):
        if request.path.startswith('/api/'):
            return jsonify(error='Too many requests. Please slow down.'), 429
        return render_template('errors/429.html'), 429

    # ── Enable WAL mode for SQLite (better concurrency) ──
    with app.app_context():
        db.create_all()
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        # Enable WAL mode for better read/write concurrency
        if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
            db.session.execute(db.text('PRAGMA journal_mode=WAL'))
            db.session.execute(db.text('PRAGMA synchronous=NORMAL'))
            db.session.commit()

    logger.info('BierStrava app initialised')
    return app

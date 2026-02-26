import os
import logging
from flask import Flask, render_template, jsonify, request, send_from_directory
from .extensions import db, migrate, login_manager, csrf, limiter
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
    logger = logging.getLogger('veau')

    # Warn if using default secret key
    if app.config['SECRET_KEY'] == 'dev-secret-key-change-in-production':
        logger.warning('⚠️  Using default SECRET_KEY — set SECRET_KEY env var for production!')

    # ── Extensions ───────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
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

    # ── Uploads route (serves from UPLOAD_FOLDER, even if outside static/) ──
    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    # ── Template global for upload URLs ───────────────────
    @app.template_global()
    def upload_url(filename):
        """Generate URL for an uploaded file. Works with any UPLOAD_FOLDER location."""
        if filename:
            from flask import url_for as _url_for
            return _url_for('uploaded_file', filename=filename)
        return ''

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

    # ── Database init & upload folder ─────────────────────
    with app.app_context():
        db.create_all()
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        # Enable WAL mode for better read/write concurrency
        if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
            db.session.execute(db.text('PRAGMA journal_mode=WAL'))
            db.session.execute(db.text('PRAGMA synchronous=NORMAL'))
            db.session.commit()

            # Ensure new columns exist (fallback if migration didn't run)
            try:
                db.session.execute(db.text('SELECT countdown_enabled FROM users LIMIT 1'))
                db.session.rollback()
            except Exception:
                db.session.rollback()
                db.session.execute(db.text(
                    'ALTER TABLE users ADD COLUMN countdown_enabled BOOLEAN DEFAULT 0'
                ))
                db.session.commit()
                logger.info('Added missing countdown_enabled column')

        # Seed tiered achievements
        from .models import Achievement, UserAchievement
        _achievements = [
            # Bier tiers (total beers posted)
            ('bier_1', 'First Bier', '🍺', 'Post your first bier'),
            ('bier_10', '10 Biers', '🍺', 'Post 10 biers'),
            ('bier_100', 'Centurion', '🍺', 'Post 100 biers'),
            ('bier_500', 'Legend', '🍺', 'Post 500 biers'),
            ('bier_1000', 'Machine', '🍺', 'Post 1000 biers'),
            ('bier_2000', 'GOAT', '🍺', 'Post 2000 biers'),
            # Speed tiers (fastest single time)
            ('speed_5', 'Quick Sip', '🏃', 'Under 5 seconds'),
            ('speed_3', 'Speed Demon', '🏃', 'Under 3 seconds'),
            ('speed_2', 'Lightning', '🏃', 'Under 2 seconds'),
            ('speed_1.5', 'Inhuman', '🏃', 'Under 1.5 seconds'),
            # Social tiers (connections)
            ('social_1', 'First Mate', '🫂', 'Connect with 1 person'),
            ('social_5', 'Social', '🫂', 'Connect with 5 people'),
            ('social_10', 'Popular', '🫂', 'Connect with 10 people'),
            ('social_25', 'Influencer', '🫂', 'Connect with 25 people'),
            # Streak tiers (consecutive days posting)
            ('streak_3', 'Hat Trick', '🎯', '3 days in a row'),
            ('streak_7', 'Full Week', '🎯', '7 days in a row'),
            ('streak_14', 'Fortnight', '🎯', '14 days in a row'),
            ('streak_30', 'Iron Will', '🎯', '30 days in a row'),
            # PB tiers (personal bests beaten)
            ('pb_1', 'Record Breaker', '🥇', 'Beat your PB'),
            ('pb_5', 'PB Hunter', '🥇', 'Beat your PB 5 times'),
            ('pb_10', 'PB Machine', '🥇', 'Beat your PB 10 times'),
            ('pb_25', 'PB Legend', '🥇', 'Beat your PB 25 times'),
            # Challenge tiers (Kan/Spies/etc completed)
            ('challenge_1', 'Challenger', '🏆', 'Complete a challenge'),
            ('challenge_5', 'Veteran', '🏆', 'Complete 5 challenges'),
            ('challenge_10', 'Champion', '🏆', 'Complete 10 challenges'),
            ('challenge_25', 'Master', '🏆', 'Complete 25 challenges'),
            # Weekly tiers (posts in one week)
            ('weekly_5', 'On Fire', '🔥', '5 posts in one week'),
            ('weekly_10', 'Blazing', '🔥', '10 posts in one week'),
            ('weekly_20', 'Inferno', '🔥', '20 posts in one week'),
        ]
        new_slugs = {slug for slug, _, _, _ in _achievements}
        # Remove old non-tiered achievements
        old_achs = Achievement.query.filter(~Achievement.slug.in_(new_slugs)).all()
        for old in old_achs:
            UserAchievement.query.filter_by(achievement_slug=old.slug).delete()
            db.session.delete(old)
        # Add new achievements
        for slug, name, icon, desc in _achievements:
            existing = Achievement.query.filter_by(slug=slug).first()
            if existing:
                existing.name = name
                existing.icon = icon
                existing.description = desc
            else:
                db.session.add(Achievement(slug=slug, name=name, icon=icon, description=desc))
        db.session.commit()

    logger.info('VEAU app initialised')
    return app

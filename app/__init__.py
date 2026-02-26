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
    from .competitions import bp as competitions_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)
    app.register_blueprint(posts_bp, url_prefix='/posts')
    app.register_blueprint(groups_bp, url_prefix='/groups')
    app.register_blueprint(profiles_bp)
    app.register_blueprint(leaderboard_bp, url_prefix='/leaderboard')
    app.register_blueprint(search_bp, url_prefix='/search')
    app.register_blueprint(settings_bp, url_prefix='/settings')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(competitions_bp, url_prefix='/competities')

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
            ('bier_1', 'Eerste Bier', '🍺', 'Post je eerste bier'),
            ('bier_10', '10 Bieren', '🍺', 'Post 10 bieren'),
            ('bier_100', 'Centurion', '🍺', 'Post 100 bieren'),
            ('bier_500', 'Legende', '🍺', 'Post 500 bieren'),
            ('bier_1000', 'Machine', '🍺', 'Post 1000 bieren'),
            ('bier_2000', 'GOAT', '🍺', 'Post 2000 bieren'),
            # Speed tiers (fastest single time)
            ('speed_5', 'Vlugge Slok', '🏃', 'Onder 5 seconden'),
            ('speed_3', 'Snelheidsduivel', '🏃', 'Onder 3 seconden'),
            ('speed_2', 'Bliksem', '🏃', 'Onder 2 seconden'),
            ('speed_1.5', 'Onmenselijk', '🏃', 'Onder 1.5 seconden'),
            # Social tiers (connections)
            ('social_1', 'Eerste Maat', '🫂', 'Verbind met 1 persoon'),
            ('social_5', 'Sociaal', '🫂', 'Verbind met 5 mensen'),
            ('social_10', 'Populair', '🫂', 'Verbind met 10 mensen'),
            ('social_25', 'Influencer', '🫂', 'Verbind met 25 mensen'),
            # Streak tiers (consecutive days posting)
            ('streak_3', 'Hat Trick', '🎯', '3 dagen op rij'),
            ('streak_7', 'Volle Week', '🎯', '7 dagen op rij'),
            ('streak_14', 'Twee Weken', '🎯', '14 dagen op rij'),
            ('streak_30', 'IJzeren Wil', '🎯', '30 dagen op rij'),
            # PB tiers (personal bests beaten)
            ('pb_1', 'Recordbreker', '🥇', 'Versla je PR'),
            ('pb_5', 'PR Jager', '🥇', 'Versla je PR 5 keer'),
            ('pb_10', 'PR Machine', '🥇', 'Versla je PR 10 keer'),
            ('pb_25', 'PR Legende', '🥇', 'Versla je PR 25 keer'),
            # Challenge tiers (Kan/Spies/etc completed)
            ('challenge_1', 'Uitdager', '🏆', 'Voltooi een challenge'),
            ('challenge_5', 'Veteraan', '🏆', 'Voltooi 5 challenges'),
            ('challenge_10', 'Kampioen', '🏆', 'Voltooi 10 challenges'),
            ('challenge_25', 'Meester', '🏆', 'Voltooi 25 challenges'),
            # Weekly tiers (posts in one week)
            ('weekly_5', 'On Fire', '🔥', '5 posts in één week'),
            ('weekly_10', 'Vlammend', '🔥', '10 posts in één week'),
            ('weekly_20', 'Inferno', '🔥', '20 posts in één week'),
            # Competition winner tiers
            ('comp_win_1', 'Eerste Overwinning', '🏆', 'Win je eerste competitie'),
            ('comp_win_3', 'Competitiebeest', '🏆', 'Win 3 competities'),
            ('comp_win_10', 'Onverslaanbaar', '🏆', 'Win 10 competities'),
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

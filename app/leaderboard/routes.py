from flask import render_template
from flask_login import login_required, current_user
from . import bp
from ..extensions import db
from ..models import (User, BeerPost, DrinkingSession, SessionBeer,
                      GroupMember, Group)
from datetime import datetime


CATEGORY_DEFS = [
    ('Beer', None),
    ('Spies', 'Spies'),
    ('Golden Triangle', 'Golden Triangle'),
    ('Kan', 'Kan'),
    ('Platinum Triangle', 'Platinum Triangle'),
    ('1/2 Krat', '1/2 Krat'),
    ('Krat', 'Krat'),
]

MONTH_NAMES_NL = [
    '', 'januari', 'februari', 'maart', 'april', 'mei', 'juni',
    'juli', 'augustus', 'september', 'oktober', 'november', 'december'
]


@bp.route('/')
@login_required
def index():
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_name = MONTH_NAMES_NL[now.month]

    # ── Gladjakkers: fastest user per category (all time) ──
    gladjakkers = []

    # Beer category: fastest single BeerPost.drink_time_seconds
    beer_fastest = db.session.query(
        User.id, User.username, User.display_name, User.avatar_filename,
        db.func.min(BeerPost.drink_time_seconds).label('best_time')
    ).join(BeerPost, BeerPost.user_id == User.id).filter(
        BeerPost.drink_time_seconds.isnot(None)
    ).group_by(User.id).order_by(
        db.asc(db.func.min(BeerPost.drink_time_seconds))
    ).first()

    if beer_fastest:
        gladjakkers.append({
            'category': 'Beer',
            'user': beer_fastest,
            'time': beer_fastest.best_time,
        })

    # Session categories: fastest SessionBeer per label
    for cat_name, cat_label in CATEGORY_DEFS:
        if cat_label is None:
            continue
        row = db.session.query(
            User.id, User.username, User.display_name, User.avatar_filename,
            db.func.min(SessionBeer.drink_time_seconds).label('best_time')
        ).join(
            DrinkingSession, DrinkingSession.user_id == User.id
        ).join(
            SessionBeer, SessionBeer.session_id == DrinkingSession.id
        ).filter(
            SessionBeer.label == cat_label,
            SessionBeer.drink_time_seconds.isnot(None)
        ).group_by(User.id).order_by(
            db.asc(db.func.min(SessionBeer.drink_time_seconds))
        ).first()

        if row:
            gladjakkers.append({
                'category': cat_name,
                'user': row,
                'time': row.best_time,
            })

    # ── Bier Buffels: most beers this month ──
    buffels = db.session.query(
        User.id, User.username, User.display_name, User.avatar_filename,
        db.func.sum(BeerPost.beer_count).label('total_beers'),
        db.func.count(BeerPost.id).label('post_count')
    ).join(BeerPost, BeerPost.user_id == User.id).filter(
        BeerPost.created_at >= month_start
    ).group_by(User.id).order_by(
        db.desc(db.func.sum(BeerPost.beer_count))
    ).limit(50).all()

    return render_template('leaderboard/index.html',
                           gladjakkers=gladjakkers,
                           buffels=buffels,
                           month_name=month_name,
                           active_nav='leaderboard')

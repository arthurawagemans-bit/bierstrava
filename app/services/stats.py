"""Shared statistics calculations used by profiles and achievements."""

from datetime import datetime, date as dt_date, timedelta
from ..extensions import db
from ..models import (BeerPost, SessionBeer, DrinkingSession, Connection,
                      Competition, UserAchievement)


def calculate_max_streak(user_id, limit=60):
    """Calculate the maximum consecutive-day posting streak for a user.
    Returns an integer (0 if no posts)."""
    recent_dates = db.session.query(
        db.func.date(BeerPost.created_at)
    ).filter(BeerPost.user_id == user_id).distinct().order_by(
        db.func.date(BeerPost.created_at).desc()
    ).limit(limit).all()

    dates = []
    for r in recent_dates:
        d = r[0] if isinstance(r[0], str) else str(r[0])
        try:
            dates.append(dt_date.fromisoformat(d))
        except (ValueError, TypeError):
            pass

    if not dates:
        return 0

    max_streak = 1
    streak = 1
    for i in range(1, len(dates)):
        if (dates[i - 1] - dates[i]).days == 1:
            streak += 1
        else:
            streak = 1
        if streak > max_streak:
            max_streak = streak

    return max_streak


def get_user_achievement_stats(user_id):
    """Get all stats needed for achievement checking in minimal queries.
    Returns a dict with keys: total_beers, fastest, conn_count, max_streak,
    pb_count, challenge_count, week_posts, comp_wins."""

    challenge_labels = ['Kan', 'Spies', 'Golden Triangle',
                        'Platinum Triangle', '1/2 Krat', 'Krat']
    week_ago = datetime.utcnow() - timedelta(days=7)

    # Query 1: total beers + weekly posts from BeerPost
    row1 = db.session.query(
        db.func.coalesce(db.func.sum(BeerPost.beer_count), 0).label('total_beers'),
        db.func.count(db.case(
            (BeerPost.created_at >= week_ago, BeerPost.id),
        )).label('week_posts'),
    ).filter(BeerPost.user_id == user_id).one()

    # Query 2: fastest time, pb count, challenge count from SessionBeer
    row2 = db.session.query(
        db.func.min(SessionBeer.drink_time_seconds).label('fastest'),
        db.func.count(db.case(
            (SessionBeer.is_pb == True, SessionBeer.id),
        )).label('pb_count'),
        db.func.count(db.case(
            (db.and_(
                SessionBeer.label.in_(challenge_labels),
                SessionBeer.drink_time_seconds.isnot(None),
            ), SessionBeer.id),
        )).label('challenge_count'),
    ).join(
        DrinkingSession, DrinkingSession.id == SessionBeer.session_id
    ).filter(
        DrinkingSession.user_id == user_id,
    ).one()

    # Query 3: connection count + competition wins
    conn_count = Connection.query.filter(
        db.or_(Connection.follower_id == user_id, Connection.followed_id == user_id),
        Connection.status == 'accepted'
    ).count()

    comp_wins = Competition.query.filter_by(
        winner_id=user_id, status='completed'
    ).count()

    # Query 4: streak
    max_streak = calculate_max_streak(user_id)

    return {
        'total_beers': int(row1.total_beers),
        'fastest': row2.fastest,
        'conn_count': conn_count,
        'max_streak': max_streak,
        'pb_count': int(row2.pb_count),
        'challenge_count': int(row2.challenge_count),
        'week_posts': int(row1.week_posts),
        'comp_wins': comp_wins,
    }

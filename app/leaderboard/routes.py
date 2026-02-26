from flask import render_template, request
from flask_login import login_required, current_user
from . import bp
from ..extensions import db
from ..models import User, BeerPost, BeerPostGroup, GroupMember, Group, Competition
from datetime import datetime, timedelta


@bp.route('/')
@login_required
def index():
    period = request.args.get('period', 'all')
    sort = request.args.get('sort', 'snelste')
    group_id = request.args.get('group', None, type=int)

    user_groups = GroupMember.query.filter_by(user_id=current_user.id).all()
    groups = [m.group for m in user_groups]

    if group_id:
        group = Group.query.get_or_404(group_id)
        if not group.is_member(current_user):
            group_id = None
            rankings = get_global_leaderboard(period, sort)
        else:
            rankings = get_group_leaderboard(group_id, period, sort)
    else:
        rankings = get_global_leaderboard(period, sort)

    # Competition wins (separate query, not period-filtered)
    comp_wins = {}
    if sort == 'overwinningen':
        win_counts = db.session.query(
            Competition.winner_id,
            db.func.count(Competition.id).label('wins')
        ).filter(
            Competition.status == 'completed',
            Competition.winner_id.isnot(None)
        ).group_by(Competition.winner_id).all()
        comp_wins = {w.winner_id: w.wins for w in win_counts}

    return render_template('leaderboard/index.html',
                           rankings=rankings,
                           groups=groups,
                           current_period=period,
                           current_sort=sort,
                           current_group_id=group_id,
                           comp_wins=comp_wins,
                           active_nav='leaderboard')


def _build_base_query():
    return db.session.query(
        User.id,
        User.username,
        User.display_name,
        User.avatar_filename,
        db.func.min(BeerPost.drink_time_seconds).label('best_time'),
        db.func.sum(BeerPost.beer_count).label('total_beers'),
        db.func.avg(BeerPost.drink_time_seconds).label('avg_time'),
        db.func.count(BeerPost.id).label('post_count')
    )


def _apply_sort(query, sort):
    if sort == 'bieren':
        return query.order_by(db.desc(db.func.sum(BeerPost.beer_count)))
    elif sort == 'gemiddelde':
        return query.order_by(
            db.case((db.func.avg(BeerPost.drink_time_seconds).is_(None), 1), else_=0),
            db.asc(db.func.avg(BeerPost.drink_time_seconds))
        )
    else:  # snelste (default)
        return query.order_by(
            db.case((db.func.min(BeerPost.drink_time_seconds).is_(None), 1), else_=0),
            db.asc(db.func.min(BeerPost.drink_time_seconds))
        )


def get_global_leaderboard(period='all', sort='snelste'):
    if sort == 'overwinningen':
        return get_competition_leaderboard()

    query = _build_base_query().join(
        BeerPost, BeerPost.user_id == User.id
    ).filter(BeerPost.is_public == True)  # noqa: E712

    query = apply_period_filter(query, period)
    query = query.group_by(User.id)
    query = _apply_sort(query, sort)
    return query.limit(100).all()


def get_group_leaderboard(group_id, period='all', sort='snelste'):
    if sort == 'overwinningen':
        return get_competition_leaderboard(group_id)

    query = _build_base_query().join(
        BeerPost, BeerPost.user_id == User.id
    ).join(
        BeerPostGroup, BeerPostGroup.post_id == BeerPost.id
    ).filter(BeerPostGroup.group_id == group_id)

    query = apply_period_filter(query, period)
    query = query.group_by(User.id)
    query = _apply_sort(query, sort)
    return query.limit(100).all()


def get_competition_leaderboard(group_id=None):
    """Rankings by competition wins."""
    query = db.session.query(
        User.id,
        User.username,
        User.display_name,
        User.avatar_filename,
        db.func.count(Competition.id).label('wins')
    ).join(
        Competition, Competition.winner_id == User.id
    ).filter(Competition.status == 'completed')

    if group_id:
        query = query.filter(Competition.group_id == group_id)

    return query.group_by(User.id).order_by(
        db.desc(db.func.count(Competition.id))
    ).limit(100).all()


def apply_period_filter(query, period):
    now = datetime.utcnow()
    if period == 'week':
        query = query.filter(BeerPost.created_at >= now - timedelta(days=7))
    elif period == 'month':
        query = query.filter(BeerPost.created_at >= now - timedelta(days=30))
    return query

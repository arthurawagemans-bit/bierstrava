from flask import render_template, request
from flask_login import login_required, current_user
from . import bp
from ..extensions import db
from ..models import User, BeerPost, BeerPostGroup, GroupMember, Group
from datetime import datetime, timedelta


@bp.route('/')
@login_required
def index():
    period = request.args.get('period', 'all')
    group_id = request.args.get('group', None, type=int)

    user_groups = GroupMember.query.filter_by(user_id=current_user.id).all()
    groups = [m.group for m in user_groups]

    if group_id:
        group = Group.query.get_or_404(group_id)
        if not group.is_member(current_user):
            group_id = None
            rankings = get_global_leaderboard(period)
        else:
            rankings = get_group_leaderboard(group_id, period)
    else:
        rankings = get_global_leaderboard(period)

    return render_template('leaderboard/index.html',
                           rankings=rankings,
                           groups=groups,
                           current_period=period,
                           current_group_id=group_id,
                           active_nav='leaderboard')


def get_global_leaderboard(period='all'):
    query = db.session.query(
        User.id,
        User.username,
        User.display_name,
        User.avatar_filename,
        db.func.min(BeerPost.drink_time_seconds).label('best_time'),
        db.func.count(BeerPost.id).label('total_beers'),
        db.func.avg(BeerPost.drink_time_seconds).label('avg_time')
    ).join(BeerPost, BeerPost.user_id == User.id).filter(
        BeerPost.is_public == True  # noqa: E712
    )

    query = apply_period_filter(query, period)
    return query.group_by(User.id).order_by(
        db.case((db.func.min(BeerPost.drink_time_seconds).is_(None), 1), else_=0),
        db.asc(db.func.min(BeerPost.drink_time_seconds))
    ).limit(100).all()


def get_group_leaderboard(group_id, period='all'):
    query = db.session.query(
        User.id,
        User.username,
        User.display_name,
        User.avatar_filename,
        db.func.min(BeerPost.drink_time_seconds).label('best_time'),
        db.func.count(BeerPost.id).label('total_beers'),
        db.func.avg(BeerPost.drink_time_seconds).label('avg_time')
    ).join(BeerPost, BeerPost.user_id == User.id).join(
        BeerPostGroup, BeerPostGroup.post_id == BeerPost.id
    ).filter(
        BeerPostGroup.group_id == group_id
    )

    query = apply_period_filter(query, period)
    return query.group_by(User.id).order_by(
        db.case((db.func.min(BeerPost.drink_time_seconds).is_(None), 1), else_=0),
        db.asc(db.func.min(BeerPost.drink_time_seconds))
    ).limit(100).all()


def apply_period_filter(query, period):
    now = datetime.utcnow()
    if period == 'week':
        query = query.filter(BeerPost.created_at >= now - timedelta(days=7))
    elif period == 'month':
        query = query.filter(BeerPost.created_at >= now - timedelta(days=30))
    return query

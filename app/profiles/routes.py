from flask import render_template, redirect, url_for, flash, abort, current_app
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from . import bp
from ..extensions import db
from ..models import (User, Connection, BeerPost, SessionBeer, DrinkingSession,
                      Like, Comment, Achievement, UserAchievement)
from .forms import EditProfileForm
from ..posts.utils import process_upload
from datetime import datetime, timedelta


@bp.route('/u/<username>')
@login_required
def view(username):
    user = User.query.filter_by(username=username).first_or_404()
    can_view = current_user.can_view_profile(user)

    stats = None
    posts = None
    category_stats = []

    if can_view:
        now = datetime.utcnow()

        # Single query for all basic post stats
        row = db.session.query(
            db.func.coalesce(db.func.sum(BeerPost.beer_count), 0).label('total'),
            db.func.min(BeerPost.drink_time_seconds).label('best'),
            db.func.avg(BeerPost.drink_time_seconds).label('avg'),
            db.func.coalesce(db.func.sum(
                db.case((BeerPost.created_at >= now - timedelta(days=30), BeerPost.beer_count), else_=0)
            ), 0).label('month'),
        ).filter(BeerPost.user_id == user.id).one()

        stats = {
            'best_time': row.best,
            'avg_time': round(row.avg, 3) if row.avg else None,
            'beers_this_month': int(row.month),
            'total_beers': int(row.total),
        }

        posts = BeerPost.query.filter_by(user_id=user.id).options(
            joinedload(BeerPost.session).joinedload(DrinkingSession.beers),
        ).order_by(BeerPost.created_at.desc()).limit(50).all()

        # Batch annotate posts with like/comment counts
        if posts:
            from ..main.routes import _annotate_posts
            _annotate_posts(posts, current_user)

        # Single query for ALL category PBs and counts (replaces 12 queries with 1)
        cat_rows = db.session.query(
            SessionBeer.label,
            db.func.min(SessionBeer.drink_time_seconds).label('pb'),
            db.func.count(SessionBeer.id).label('cnt'),
        ).join(
            DrinkingSession, DrinkingSession.id == SessionBeer.session_id
        ).filter(
            DrinkingSession.user_id == user.id
        ).group_by(SessionBeer.label).all()

        # Build lookup: label → {pb, count}
        cat_lookup = {}
        for r in cat_rows:
            cat_lookup[r.label] = {'pb': r.pb, 'count': int(r.cnt)}

        category_defs = [
            ('Beer', None),
            ('Spies', 'Spies'),
            ('Golden Triangle', 'Golden Triangle'),
            ('Kan', 'Kan'),
            ('Platinum Triangle', 'Platinum Triangle'),
            ('1/2 Krat', '1/2 Krat'),
            ('Krat', 'Krat'),
        ]
        for cat_name, cat_label in category_defs:
            data = cat_lookup.get(cat_label, {'pb': None, 'count': 0})
            category_stats.append({
                'name': cat_name,
                'pb': data['pb'],
                'count': data['count'],
            })

    # Achievements
    all_achievements = Achievement.query.order_by(Achievement.id).all()
    earned_slugs = {ua.achievement_slug for ua in
                    UserAchievement.query.filter_by(user_id=user.id).all()}
    achievements = [
        {'slug': a.slug, 'name': a.name, 'icon': a.icon,
         'description': a.description, 'earned': a.slug in earned_slugs}
        for a in all_achievements
    ]

    return render_template('profiles/view.html',
                           profile_user=user,
                           can_view=can_view,
                           stats=stats,
                           posts=posts,
                           category_stats=category_stats,
                           achievements=achievements,
                           active_nav='profile' if user.id == current_user.id else '')


@bp.route('/u/<username>/edit', methods=['GET', 'POST'])
@login_required
def edit(username):
    if current_user.username != username:
        abort(403)

    form = EditProfileForm(obj=current_user)
    if form.validate_on_submit():
        current_user.display_name = form.display_name.data
        current_user.bio = form.bio.data
        if form.avatar.data:
            current_user.avatar_filename = process_upload(
                form.avatar.data,
                current_app.config['UPLOAD_FOLDER'],
                max_size=(400, 400)
            )
        db.session.commit()
        flash('Profile updated!', 'success')
        return redirect(url_for('profiles.view', username=current_user.username))

    return render_template('profiles/edit.html', form=form)


@bp.route('/u/<username>/connect', methods=['POST'])
@login_required
def connect(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user.id == current_user.id:
        abort(400)

    existing = Connection.query.filter_by(
        follower_id=current_user.id, followed_id=user.id
    ).first()

    if existing:
        flash('Connection already exists or pending.', 'info')
        return redirect(url_for('profiles.view', username=username))

    # Check if they already sent us a request — auto-accept both
    reverse = Connection.query.filter_by(
        follower_id=user.id, followed_id=current_user.id, status='pending'
    ).first()

    if reverse:
        # They requested us, so accept theirs and create ours as accepted
        reverse.status = 'accepted'
        conn = Connection(
            follower_id=current_user.id,
            followed_id=user.id,
            status='accepted'
        )
        db.session.add(conn)
        db.session.commit()
        flash(f'Connected with {user.display_name}!', 'success')
        return redirect(url_for('profiles.view', username=username))

    # Always requires acceptance (LinkedIn-style)
    conn = Connection(
        follower_id=current_user.id,
        followed_id=user.id,
        status='pending'
    )
    db.session.add(conn)
    db.session.commit()

    flash('Connection request sent!', 'success')

    return redirect(url_for('profiles.view', username=username))


@bp.route('/u/<username>/disconnect', methods=['POST'])
@login_required
def disconnect(username):
    user = User.query.filter_by(username=username).first_or_404()

    # Delete both directions
    conn = Connection.query.filter_by(
        follower_id=current_user.id, followed_id=user.id
    ).first()
    if conn:
        db.session.delete(conn)

    reverse = Connection.query.filter_by(
        follower_id=user.id, followed_id=current_user.id
    ).first()
    if reverse:
        db.session.delete(reverse)

    db.session.commit()
    flash(f'Disconnected from {user.display_name}.', 'success')
    return redirect(url_for('profiles.view', username=username))


@bp.route('/connection-requests')
@login_required
def connection_requests():
    requests_list = Connection.query.filter_by(
        followed_id=current_user.id, status='pending'
    ).order_by(Connection.created_at.desc()).all()
    return render_template('profiles/connection_requests.html', requests=requests_list)


@bp.route('/connection-requests/<int:id>/accept', methods=['POST'])
@login_required
def accept_request(id):
    conn = Connection.query.get_or_404(id)
    if conn.followed_id != current_user.id:
        abort(403)

    conn.status = 'accepted'

    # Two-way: auto-create the reverse connection
    reverse = Connection.query.filter_by(
        follower_id=current_user.id, followed_id=conn.follower_id
    ).first()
    if not reverse:
        reverse = Connection(
            follower_id=current_user.id,
            followed_id=conn.follower_id,
            status='accepted'
        )
        db.session.add(reverse)
    else:
        reverse.status = 'accepted'

    db.session.commit()
    flash('Connection request accepted!', 'success')
    return redirect(url_for('profiles.connection_requests'))


@bp.route('/connection-requests/<int:id>/reject', methods=['POST'])
@login_required
def reject_request(id):
    conn = Connection.query.get_or_404(id)
    if conn.followed_id != current_user.id:
        abort(403)

    db.session.delete(conn)
    db.session.commit()
    flash('Connection request declined.', 'success')
    return redirect(url_for('profiles.connection_requests'))


@bp.route('/u/<username>/connections')
@login_required
def connections(username):
    user = User.query.filter_by(username=username).first_or_404()
    if not current_user.can_view_profile(user):
        abort(403)

    # Get all accepted connections (both directions, deduplicated)
    outgoing = Connection.query.filter_by(
        follower_id=user.id, status='accepted'
    ).all()
    incoming = Connection.query.filter_by(
        followed_id=user.id, status='accepted'
    ).all()

    user_ids = set()
    users = []
    for c in outgoing:
        if c.followed_id not in user_ids:
            user_ids.add(c.followed_id)
            users.append(c.addressee)
    for c in incoming:
        if c.follower_id not in user_ids:
            user_ids.add(c.follower_id)
            users.append(c.requester)

    return render_template('profiles/connections.html', profile_user=user, users=users)


# Redirects for old URLs
@bp.route('/u/<username>/followers')
@login_required
def followers(username):
    return redirect(url_for('profiles.connections', username=username))


@bp.route('/u/<username>/following')
@login_required
def following(username):
    return redirect(url_for('profiles.connections', username=username))

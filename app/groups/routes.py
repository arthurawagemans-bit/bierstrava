import secrets
from datetime import datetime, timedelta
from flask import render_template, redirect, url_for, flash, abort, current_app, request
from flask_login import login_required, current_user
from . import bp
from ..extensions import db, cache
from ..models import Group, GroupMember, GroupJoinRequest, BeerPost, BeerPostGroup, User, Competition
from .forms import CreateGroupForm, EditGroupForm
from ..posts.utils import process_upload


@bp.route('/')
@login_required
def list_groups():
    memberships = GroupMember.query.filter_by(user_id=current_user.id).all()
    groups = [m.group for m in memberships]
    my_group_ids = [m.group_id for m in memberships]

    # Discover groups: groups the user is NOT a member of
    if my_group_ids:
        discover_groups = Group.query.filter(
            ~Group.id.in_(my_group_ids)
        ).order_by(Group.created_at.desc()).limit(20).all()
    else:
        discover_groups = Group.query.order_by(
            Group.created_at.desc()
        ).limit(20).all()

    return render_template('groups/list.html', groups=groups,
                           discover_groups=discover_groups, active_nav='groups')


@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    form = CreateGroupForm()
    if form.validate_on_submit():
        avatar_filename = None
        if form.avatar.data:
            avatar_filename = process_upload(
                form.avatar.data,
                current_app.config['UPLOAD_FOLDER'],
                max_size=(400, 400)
            )

        group = Group(
            name=form.name.data,
            description=form.description.data,
            avatar_filename=avatar_filename,
            invite_code=secrets.token_urlsafe(10),
            created_by_id=current_user.id
        )
        db.session.add(group)
        db.session.flush()

        member = GroupMember(
            user_id=current_user.id,
            group_id=group.id,
            role='admin'
        )
        db.session.add(member)
        db.session.commit()

        flash(f'Groep "{group.name}" aangemaakt!', 'success')
        return redirect(url_for('groups.detail', id=group.id))

    return render_template('groups/create.html', form=form)


@bp.route('/<int:id>')
@login_required
def detail(id):
    group = Group.query.get_or_404(id)
    if not group.is_member(current_user):
        abort(403)

    membership = GroupMember.query.filter_by(
        group_id=group.id, user_id=current_user.id
    ).first()
    membership.last_seen_at = datetime.utcnow()
    db.session.commit()

    is_admin = group.is_admin(current_user)

    # Subquery: posts shared to this group
    group_posts = db.session.query(
        BeerPost.id.label('post_id'),
        BeerPost.user_id,
        BeerPost.drink_time_seconds,
        BeerPost.created_at,
    ).join(BeerPostGroup, BeerPostGroup.post_id == BeerPost.id).filter(
        BeerPostGroup.group_id == group.id
    ).subquery()

    # Base: all members via outerjoin → user → group_posts
    base = db.session.query(
        User.id,
        User.username,
        User.display_name,
        User.avatar_filename,
    ).join(GroupMember, GroupMember.user_id == User.id).filter(
        GroupMember.group_id == group.id
    )

    # 1) Fastest single time — min(drink_time), ASC, NULLs last
    lb_fastest = base.outerjoin(
        group_posts, group_posts.c.user_id == User.id
    ).add_columns(
        db.func.min(group_posts.c.drink_time_seconds).label('metric'),
        db.func.count(group_posts.c.post_id).label('total_beers'),
        db.func.max(group_posts.c.created_at).label('last_active'),
    ).group_by(User.id).order_by(
        db.case((db.func.min(group_posts.c.drink_time_seconds).is_(None), 1), else_=0),
        db.asc(db.func.min(group_posts.c.drink_time_seconds))
    ).all()

    # 2) Most this month — count(posts) where created_at >= first of month, DESC
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_posts = db.session.query(
        BeerPost.id.label('post_id'),
        BeerPost.user_id,
        BeerPost.created_at,
    ).join(BeerPostGroup, BeerPostGroup.post_id == BeerPost.id).filter(
        BeerPostGroup.group_id == group.id,
        BeerPost.created_at >= month_start,
    ).subquery()

    lb_month = base.outerjoin(
        month_posts, month_posts.c.user_id == User.id
    ).add_columns(
        db.func.count(month_posts.c.post_id).label('metric'),
        db.func.count(month_posts.c.post_id).label('total_beers'),
        db.func.max(month_posts.c.created_at).label('last_active'),
    ).group_by(User.id).order_by(
        db.desc(db.func.count(month_posts.c.post_id)),
    ).all()

    # 3) Fastest average — avg(drink_time), ASC, NULLs last
    lb_average = base.outerjoin(
        group_posts, group_posts.c.user_id == User.id
    ).add_columns(
        db.func.avg(group_posts.c.drink_time_seconds).label('metric'),
        db.func.count(group_posts.c.post_id).label('total_beers'),
        db.func.max(group_posts.c.created_at).label('last_active'),
    ).group_by(User.id).order_by(
        db.case((db.func.avg(group_posts.c.drink_time_seconds).is_(None), 1), else_=0),
        db.asc(db.func.avg(group_posts.c.drink_time_seconds))
    ).all()

    # 4) This Week — count(posts) where created_at >= Monday, DESC
    today = datetime.utcnow()
    week_start = (today - timedelta(days=today.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_posts = db.session.query(
        BeerPost.id.label('post_id'),
        BeerPost.user_id,
        BeerPost.created_at,
    ).join(BeerPostGroup, BeerPostGroup.post_id == BeerPost.id).filter(
        BeerPostGroup.group_id == group.id,
        BeerPost.created_at >= week_start,
    ).subquery()

    lb_week = base.outerjoin(
        week_posts, week_posts.c.user_id == User.id
    ).add_columns(
        db.func.count(week_posts.c.post_id).label('metric'),
        db.func.count(week_posts.c.post_id).label('total_beers'),
        db.func.max(week_posts.c.created_at).label('last_active'),
    ).group_by(User.id).order_by(
        db.desc(db.func.count(week_posts.c.post_id)),
    ).all()

    # Group record: fastest single time across all group posts
    group_record = db.session.query(
        BeerPost.drink_time_seconds,
        User.display_name,
        User.username,
    ).join(BeerPostGroup, BeerPostGroup.post_id == BeerPost.id).join(
        User, User.id == BeerPost.user_id
    ).filter(
        BeerPostGroup.group_id == group.id,
        BeerPost.drink_time_seconds.isnot(None),
    ).order_by(BeerPost.drink_time_seconds.asc()).first()

    # Recent posts
    post_ids = db.session.query(BeerPostGroup.post_id).filter(
        BeerPostGroup.group_id == group.id
    )
    posts = BeerPost.query.filter(BeerPost.id.in_(post_ids)).order_by(
        BeerPost.created_at.desc()
    ).limit(50).all()

    pending_count = group.pending_request_count() if is_admin else 0

    # Active competition for this group (if any)
    active_competition = Competition.query.filter_by(
        group_id=group.id, status='active'
    ).order_by(Competition.created_at.desc()).first()

    # Latest completed competition (shown when no active competition)
    latest_completed_competition = None
    if not active_competition:
        latest_completed_competition = Competition.query.filter_by(
            group_id=group.id, status='completed'
        ).order_by(Competition.completed_at.desc()).first()

    return render_template('groups/detail.html',
                           group=group, posts=posts,
                           is_admin=is_admin,
                           pending_count=pending_count,
                           lb_fastest=lb_fastest,
                           lb_month=lb_month,
                           lb_average=lb_average,
                           lb_week=lb_week,
                           group_record=group_record,
                           active_competition=active_competition,
                           latest_completed_competition=latest_completed_competition)


@bp.route('/join/<invite_code>', methods=['GET', 'POST'])
@login_required
def join(invite_code):
    group = Group.query.filter_by(invite_code=invite_code).first_or_404()

    if group.is_member(current_user):
        flash('Je bent al lid van deze groep.', 'info')
        return redirect(url_for('groups.detail', id=group.id))

    if request.method == 'POST':
        member = GroupMember(
            user_id=current_user.id,
            group_id=group.id,
            role='member'
        )
        db.session.add(member)
        db.session.commit()
        flash(f'Je bent lid geworden van "{group.name}"!', 'success')
        return redirect(url_for('groups.detail', id=group.id))

    return render_template('groups/join.html', group=group)


@bp.route('/<int:id>/leave', methods=['POST'])
@login_required
def leave(id):
    group = Group.query.get_or_404(id)
    membership = GroupMember.query.filter_by(
        group_id=group.id, user_id=current_user.id
    ).first()

    if not membership:
        abort(400)

    db.session.delete(membership)
    db.session.commit()
    flash(f'Je hebt "{group.name}" verlaten.', 'success')
    return redirect(url_for('groups.list_groups'))


@bp.route('/<int:id>/manage', methods=['GET', 'POST'])
@login_required
def manage(id):
    group = Group.query.get_or_404(id)
    if not group.is_admin(current_user):
        abort(403)

    members = GroupMember.query.filter_by(group_id=group.id).all()
    return render_template('groups/manage.html', group=group, members=members)


@bp.route('/<int:id>/invite')
@login_required
def invite(id):
    group = Group.query.get_or_404(id)
    if not group.is_member(current_user):
        abort(403)

    is_admin = group.is_admin(current_user)
    pending_requests = []
    if is_admin:
        pending_requests = GroupJoinRequest.query.filter_by(
            group_id=group.id, status='pending'
        ).all()

    return render_template('groups/invite.html', group=group,
                           is_admin=is_admin,
                           pending_requests=pending_requests)


@bp.route('/<int:id>/remove-member/<int:user_id>', methods=['POST'])
@login_required
def remove_member(id, user_id):
    group = Group.query.get_or_404(id)
    if not group.is_admin(current_user):
        abort(403)
    if user_id == current_user.id:
        abort(400)

    membership = GroupMember.query.filter_by(
        group_id=group.id, user_id=user_id
    ).first_or_404()

    db.session.delete(membership)
    db.session.commit()
    flash('Lid verwijderd.', 'success')
    return redirect(url_for('groups.manage', id=group.id))


@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    group = Group.query.get_or_404(id)
    if not group.is_admin(current_user):
        abort(403)

    form = EditGroupForm(obj=group)
    if form.validate_on_submit():
        group.name = form.name.data
        group.description = form.description.data
        if form.avatar.data:
            group.avatar_filename = process_upload(
                form.avatar.data,
                current_app.config['UPLOAD_FOLDER'],
                max_size=(400, 400)
            )
        db.session.commit()
        flash('Groep bijgewerkt!', 'success')
        return redirect(url_for('groups.detail', id=group.id))

    return render_template('groups/edit.html', form=form, group=group)


@bp.route('/<int:id>/approve-request/<int:request_id>', methods=['POST'])
@login_required
def approve_request(id, request_id):
    group = Group.query.get_or_404(id)
    if not group.is_admin(current_user):
        abort(403)

    join_req = GroupJoinRequest.query.get_or_404(request_id)
    if join_req.group_id != group.id or join_req.status != 'pending':
        abort(400)

    join_req.status = 'accepted'
    member = GroupMember(user_id=join_req.user_id, group_id=group.id, role='member')
    db.session.add(member)
    db.session.commit()
    # Invalidate notification cache for all group admins
    admins = GroupMember.query.filter_by(group_id=group.id, role='admin').all()
    for a in admins:
        cache.delete(f'notif_count:{a.user_id}')
    flash(f'{join_req.user.display_name} is toegevoegd aan de groep.', 'success')
    return redirect(url_for('groups.invite', id=group.id))


@bp.route('/<int:id>/reject-request/<int:request_id>', methods=['POST'])
@login_required
def reject_request(id, request_id):
    group = Group.query.get_or_404(id)
    if not group.is_admin(current_user):
        abort(403)

    join_req = GroupJoinRequest.query.get_or_404(request_id)
    if join_req.group_id != group.id or join_req.status != 'pending':
        abort(400)

    join_req.status = 'rejected'
    db.session.commit()
    # Invalidate notification cache for all group admins
    admins = GroupMember.query.filter_by(group_id=group.id, role='admin').all()
    for a in admins:
        cache.delete(f'notif_count:{a.user_id}')
    flash('Verzoek afgewezen.', 'success')
    return redirect(url_for('groups.invite', id=group.id))


@bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    group = Group.query.get_or_404(id)
    if not group.is_admin(current_user):
        abort(403)
    name = group.name
    db.session.delete(group)
    db.session.commit()
    flash(f'Groep "{name}" verwijderd.', 'success')
    return redirect(url_for('groups.list_groups'))

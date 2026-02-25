import logging
import hmac
import io
import os
import shutil
import sqlite3
import tarfile
import tempfile
from sqlalchemy.exc import IntegrityError
from flask import jsonify, request, abort, render_template, current_app, send_file
from flask_login import login_required, current_user
from . import bp
from ..extensions import db, limiter
from ..models import (BeerPost, Like, Comment, Reaction, ALLOWED_REACTIONS,
                      User, Group, Tag, Connection, GroupMember, GroupJoinRequest)

logger = logging.getLogger(__name__)


@bp.route('/posts/<int:id>/like', methods=['POST'])
@login_required
@limiter.limit("60 per minute")
def toggle_like(id):
    post = BeerPost.query.get_or_404(id)
    if not post.visible_to(current_user):
        abort(403)

    existing = Like.query.filter_by(user_id=current_user.id, post_id=post.id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        count = Like.query.filter_by(post_id=post.id).count()
        return jsonify(success=True, liked=False, count=count)
    else:
        like = Like(user_id=current_user.id, post_id=post.id)
        db.session.add(like)
        db.session.commit()
        count = Like.query.filter_by(post_id=post.id).count()
        return jsonify(success=True, liked=True, count=count)


@bp.route('/posts/<int:id>/reaction', methods=['POST'])
@login_required
@limiter.limit("60 per minute")
def toggle_reaction(id):
    post = BeerPost.query.get_or_404(id)
    if not post.visible_to(current_user):
        abort(403)

    data = request.get_json()
    emoji = data.get('emoji', '') if data else ''
    if emoji not in ALLOWED_REACTIONS:
        return jsonify(success=False, error='Invalid reaction'), 400

    existing = Reaction.query.filter_by(
        user_id=current_user.id, post_id=post.id, emoji=emoji
    ).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        toggled = False
    else:
        reaction = Reaction(user_id=current_user.id, post_id=post.id, emoji=emoji)
        db.session.add(reaction)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        toggled = True

    counts = post.get_reaction_counts()
    return jsonify(success=True, toggled=toggled, emoji=emoji, counts=counts)


@bp.route('/posts/<int:id>/comment', methods=['POST'])
@login_required
@limiter.limit("30 per minute")
def add_comment(id):
    post = BeerPost.query.get_or_404(id)
    if not post.visible_to(current_user):
        abort(403)

    data = request.get_json()
    body = data.get('body', '').strip() if data else ''
    if not body or len(body) > 500:
        return jsonify(success=False, error='Invalid comment.'), 400

    comment = Comment(user_id=current_user.id, post_id=post.id, body=body)
    db.session.add(comment)
    db.session.commit()

    count = Comment.query.filter_by(post_id=post.id).count()
    return jsonify(
        success=True,
        comment={
            'id': comment.id,
            'body': comment.body,
            'author': comment.author.display_name,
            'username': comment.author.username,
            'avatar': comment.author.avatar_filename,
            'created_at': comment.created_at.strftime('%b %d, %H:%M')
        },
        count=count
    )


# ── Search ────────────────────────────────────────────────

def _batch_connection_statuses(user_ids):
    """Batch-load connection statuses for a list of user IDs relative to current_user.
    Returns dict: user_id → status string."""
    if not user_ids:
        return {}

    outgoing = Connection.query.filter(
        Connection.follower_id == current_user.id,
        Connection.followed_id.in_(user_ids),
    ).all()

    incoming = Connection.query.filter(
        Connection.follower_id.in_(user_ids),
        Connection.followed_id == current_user.id,
    ).all()

    out_map = {c.followed_id: c.status for c in outgoing}
    in_map = {c.follower_id: c.status for c in incoming}

    result = {}
    for uid in user_ids:
        out_status = out_map.get(uid)
        in_status = in_map.get(uid)
        if out_status == 'accepted':
            result[uid] = 'accepted'
        elif out_status == 'pending':
            result[uid] = 'pending'
        elif in_status == 'pending':
            result[uid] = 'incoming_pending'
        else:
            result[uid] = None
    return result


def _serialize_users_batch(users):
    """Serialize a list of users with batch-loaded connection statuses (2 queries instead of 2N)."""
    if not users:
        return []
    statuses = _batch_connection_statuses([u.id for u in users])
    return [{
        'id': u.id,
        'username': u.username,
        'display_name': u.display_name,
        'avatar': u.avatar_filename,
        'connection_status': statuses.get(u.id),
    } for u in users]


def _serialize_groups_batch(groups):
    """Serialize groups with batch-loaded membership info (2 queries instead of 3N)."""
    if not groups:
        return []
    group_ids = [g.id for g in groups]

    # Batch: member counts
    count_rows = db.session.query(
        GroupMember.group_id, db.func.count(GroupMember.id)
    ).filter(GroupMember.group_id.in_(group_ids)).group_by(GroupMember.group_id).all()
    count_map = dict(count_rows)

    # Batch: which groups current user is member of
    my_memberships = set(
        r[0] for r in db.session.query(GroupMember.group_id).filter(
            GroupMember.user_id == current_user.id,
            GroupMember.group_id.in_(group_ids),
        ).all()
    )

    # Batch: pending join requests
    pending_reqs = set(
        r[0] for r in db.session.query(GroupJoinRequest.group_id).filter(
            GroupJoinRequest.user_id == current_user.id,
            GroupJoinRequest.group_id.in_(group_ids),
            GroupJoinRequest.status == 'pending',
        ).all()
    )

    return [{
        'id': g.id,
        'name': g.name,
        'description': g.description or '',
        'avatar': g.avatar_filename,
        'member_count': count_map.get(g.id, 0),
        'is_member': g.id in my_memberships,
        'is_private': g.is_private,
        'has_pending_request': g.id in pending_reqs,
    } for g in groups]


@bp.route('/search', methods=['GET'])
@login_required
@limiter.limit("30 per minute")
def search():
    q = request.args.get('q', '').strip()

    if not q:
        # Suggestions mode: friends-of-friends + public groups
        my_conn_ids = [c.followed_id for c in Connection.query.filter_by(
            follower_id=current_user.id, status='accepted'
        ).all()]

        suggested_users = []
        fof_ids = []

        if my_conn_ids:
            fof_rows = Connection.query.filter(
                Connection.follower_id.in_(my_conn_ids),
                Connection.status == 'accepted',
                Connection.followed_id != current_user.id,
                ~Connection.followed_id.in_(my_conn_ids + [current_user.id]),
            ).limit(10).all()
            fof_ids = list({c.followed_id for c in fof_rows})
            if fof_ids:
                suggested_users = User.query.filter(User.id.in_(fof_ids)).all()

        # Pad with recent users if fewer than 5
        if len(suggested_users) < 5:
            exclude = [current_user.id] + my_conn_ids + fof_ids
            recent = User.query.filter(
                ~User.id.in_(exclude)
            ).order_by(User.created_at.desc()).limit(5 - len(suggested_users)).all()
            suggested_users.extend(recent)

        # Public groups user is not in
        my_group_ids = [m.group_id for m in current_user.group_memberships.all()]
        suggested_groups = Group.query.filter(
            ~Group.id.in_(my_group_ids) if my_group_ids else db.true(),
            Group.is_private == False,
        ).limit(5).all()

        return jsonify(
            suggestions=True,
            users=_serialize_users_batch(suggested_users),
            groups=_serialize_groups_batch(suggested_groups),
            tags=[],
        )

    # Search mode
    users = User.query.filter(
        User.id != current_user.id,
        db.or_(
            User.username.ilike(f'%{q}%'),
            User.display_name.ilike(f'%{q}%'),
        )
    ).limit(10).all()

    groups = Group.query.filter(
        Group.name.ilike(f'%{q}%')
    ).limit(10).all()

    tags = Tag.query.filter(
        Tag.name.ilike(f'%{q}%')
    ).order_by(Tag.use_count.desc()).limit(10).all()

    return jsonify(
        suggestions=False,
        users=_serialize_users_batch(users),
        groups=_serialize_groups_batch(groups),
        tags=[{'id': t.id, 'name': t.name, 'use_count': t.use_count} for t in tags],
    )


# ── Connect (AJAX) ────────────────────────────────────────

@bp.route('/connect/<username>', methods=['POST'])
@login_required
@limiter.limit("20 per minute")
def api_connect(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user.id == current_user.id:
        return jsonify(success=False, error='Cannot connect with yourself'), 400

    existing = Connection.query.filter_by(
        follower_id=current_user.id, followed_id=user.id
    ).first()
    if existing:
        return jsonify(success=True, status=existing.status)

    # Auto-accept if they already sent us a request
    reverse = Connection.query.filter_by(
        follower_id=user.id, followed_id=current_user.id, status='pending'
    ).first()

    if reverse:
        reverse.status = 'accepted'
        conn = Connection(
            follower_id=current_user.id, followed_id=user.id, status='accepted'
        )
        db.session.add(conn)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
        return jsonify(success=True, status='accepted')

    conn = Connection(
        follower_id=current_user.id, followed_id=user.id, status='pending'
    )
    db.session.add(conn)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        logger.warning('Duplicate connection attempt: %s → %s', current_user.id, user.id)
        # Re-fetch the actual status instead of assuming pending
        existing = Connection.query.filter_by(
            follower_id=current_user.id, followed_id=user.id
        ).first()
        return jsonify(success=True, status=existing.status if existing else 'pending')
    return jsonify(success=True, status='pending')


# ── Group Join (AJAX) ─────────────────────────────────────

@bp.route('/groups/<int:id>/join', methods=['POST'])
@login_required
def api_join_group(id):
    group = Group.query.get_or_404(id)

    if group.is_member(current_user):
        return jsonify(success=True, status='member')

    existing = GroupJoinRequest.query.filter_by(
        user_id=current_user.id, group_id=group.id, status='pending'
    ).first()
    if existing:
        return jsonify(success=True, status='requested')

    req = GroupJoinRequest(user_id=current_user.id, group_id=group.id)
    db.session.add(req)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(success=True, status='requested')
    return jsonify(success=True, status='requested')


# ── Group Invite (AJAX) ──────────────────────────────────

@bp.route('/groups/<int:id>/invitable', methods=['GET'])
@login_required
def invitable_connections(id):
    group = Group.query.get_or_404(id)
    if not group.is_admin(current_user):
        abort(403)

    q = request.args.get('q', '').strip()
    if not q:
        return jsonify(users=[])

    # Single query: connections who are NOT already members (SQL subqueries)
    connected_ids = db.session.query(Connection.followed_id).filter(
        Connection.follower_id == current_user.id,
        Connection.status == 'accepted',
    )
    member_ids = db.session.query(GroupMember.user_id).filter(
        GroupMember.group_id == group.id,
    )

    users = User.query.filter(
        User.id.in_(connected_ids),
        ~User.id.in_(member_ids),
        db.or_(
            User.username.ilike(f'%{q}%'),
            User.display_name.ilike(f'%{q}%'),
        )
    ).limit(10).all()

    return jsonify(users=[{
        'id': u.id,
        'username': u.username,
        'display_name': u.display_name,
        'avatar': u.avatar_filename,
    } for u in users])


@bp.route('/groups/<int:id>/invite/<int:user_id>', methods=['POST'])
@login_required
def invite_to_group(id, user_id):
    group = Group.query.get_or_404(id)
    if not group.is_admin(current_user):
        abort(403)

    user = User.query.get_or_404(user_id)

    # Must be a connection of current user
    if not current_user.is_accepted_connection_of(user):
        return jsonify(success=False, error='Not a connection'), 400

    if group.is_member(user):
        return jsonify(success=True, status='already_member')

    member = GroupMember(user_id=user.id, group_id=group.id, role='member')
    db.session.add(member)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(success=True, status='already_member')

    # Clean up any pending join request
    pending = GroupJoinRequest.query.filter_by(
        user_id=user.id, group_id=group.id, status='pending'
    ).first()
    if pending:
        pending.status = 'accepted'
        db.session.commit()

    return jsonify(success=True, status='invited')


# ── Backup endpoint ──────────────────────────────────────

@bp.route('/backup', methods=['GET'])
@limiter.limit("1 per minute")
def backup():
    """Download a .tar.gz backup of the database and uploads.
    Protected by BACKUP_SECRET env var. Disabled when secret is empty."""
    secret = current_app.config.get('BACKUP_SECRET', '')
    if not secret:
        abort(404)

    provided = request.args.get('secret', '')
    if not hmac.compare_digest(secret, provided):
        abort(403)

    db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
    db_path = db_uri.replace('sqlite:///', '')
    upload_folder = current_app.config['UPLOAD_FOLDER']

    tmp_dir = tempfile.mkdtemp()
    try:
        # Use SQLite backup API for a consistent snapshot
        backup_db_path = os.path.join(tmp_dir, 'bierstrava.db')
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(backup_db_path)
        src.backup(dst)
        src.close()
        dst.close()

        # Create tar.gz in memory
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tar:
            tar.add(backup_db_path, arcname='bierstrava.db')
            if os.path.isdir(upload_folder):
                for fname in os.listdir(upload_folder):
                    fpath = os.path.join(upload_folder, fname)
                    if os.path.isfile(fpath):
                        tar.add(fpath, arcname=f'uploads/{fname}')

        buf.seek(0)
        logger.info('Backup created successfully')
        return send_file(
            buf,
            mimetype='application/gzip',
            as_attachment=True,
            download_name='veau-backup.tar.gz',
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

import re
import json
from flask import render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import login_required, current_user
from . import bp
from ..extensions import db
from ..models import BeerPost, BeerPostGroup, Comment, GroupMember, DrinkingSession, SessionBeer, Tag, User, Group
from .forms import BeerPostForm, CommentForm, SessionPostForm
from .utils import process_upload


def extract_and_save_tags(comment_text):
    """Extract @mentions from caption and save unknown ones as tags."""
    if not comment_text:
        return
    mentions = re.findall(r'@(\w+)', comment_text)
    for name in mentions:
        # Skip if it's a user
        if User.query.filter(db.func.lower(User.username) == name.lower()).first():
            continue
        # Skip if it's a group (underscores back to spaces for matching)
        group_name = name.replace('_', ' ')
        if Group.query.filter(db.func.lower(Group.name) == group_name.lower()).first():
            continue
        # Upsert tag
        existing = Tag.query.filter(db.func.lower(Tag.name) == name.lower()).first()
        if existing:
            existing.use_count = (existing.use_count or 0) + 1
        else:
            tag = Tag(name=name, created_by_id=current_user.id, use_count=1)
            db.session.add(tag)


@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    form = BeerPostForm()
    user_groups = GroupMember.query.filter_by(user_id=current_user.id).all()
    form.groups.choices = [(m.group.id, m.group.name) for m in user_groups]

    if form.validate_on_submit():
        photo_filename = None
        if form.photo.data:
            photo_filename = process_upload(
                form.photo.data,
                current_app.config['UPLOAD_FOLDER']
            )

        is_vdl = form.is_vdl.data == 'true'
        drink_time = None if is_vdl else form.drink_time_seconds.data

        # Must have either a time or be VDL
        if not is_vdl and not drink_time:
            flash('Please time your bier or mark it as VDL.', 'error')
            return redirect(url_for('posts.create'))

        beer_count = form.beer_count.data or 1
        if beer_count < 1:
            beer_count = 1
        elif beer_count > 24:
            beer_count = 24

        post = BeerPost(
            user_id=current_user.id,
            drink_time_seconds=drink_time,
            is_vdl=is_vdl,
            beer_count=beer_count,
            caption=form.caption.data,
            photo_filename=photo_filename,
            is_public=form.is_public.data,
        )
        db.session.add(post)
        db.session.flush()

        for group_id in form.groups.data:
            link = BeerPostGroup(post_id=post.id, group_id=group_id)
            db.session.add(link)

        extract_and_save_tags(form.caption.data)
        db.session.commit()
        flash('Bier posted!', 'success')
        return redirect(url_for('posts.detail', id=post.id))

    personal_best = db.session.query(
        db.func.min(BeerPost.drink_time_seconds)
    ).filter(
        BeerPost.user_id == current_user.id,
        BeerPost.drink_time_seconds.isnot(None)
    ).scalar()

    # Get user's top 3 times per category for client-side PB detection
    all_times = db.session.query(
        SessionBeer.label, SessionBeer.drink_time_seconds
    ).join(
        DrinkingSession, DrinkingSession.id == SessionBeer.session_id
    ).filter(
        DrinkingSession.user_id == current_user.id,
        SessionBeer.drink_time_seconds.isnot(None)
    ).order_by(SessionBeer.drink_time_seconds.asc()).all()

    top_times = {}
    for label, time_val in all_times:
        key = label if label else '__bier__'
        if key not in top_times:
            top_times[key] = []
        if len(top_times[key]) < 3:
            top_times[key].append(time_val)

    # Pre-select same sharing options as last post
    last_post = BeerPost.query.filter_by(user_id=current_user.id).order_by(
        BeerPost.created_at.desc()
    ).first()
    last_public = last_post.is_public if last_post else True
    last_group_ids = set()
    if last_post:
        last_group_ids = {pg.group_id for pg in last_post.group_links}

    return render_template('posts/create.html', form=form,
                           personal_best=personal_best,
                           last_public=last_public,
                           last_group_ids=last_group_ids,
                           top_times_json=json.dumps(top_times),
                           active_nav='')


@bp.route('/create-session', methods=['POST'])
@login_required
def create_session():
    form = SessionPostForm()
    user_groups = GroupMember.query.filter_by(user_id=current_user.id).all()
    form.groups.choices = [(m.group.id, m.group.name) for m in user_groups]

    if form.validate_on_submit():
        # Parse beer times from JSON
        try:
            beers_data = json.loads(form.session_beers_json.data)
        except (json.JSONDecodeError, TypeError):
            flash('Invalid session data.', 'error')
            return redirect(url_for('posts.create'))

        if not beers_data or len(beers_data) < 1:
            flash('A session needs at least 1 bier.', 'error')
            return redirect(url_for('posts.create'))

        # Create the session
        session_obj = DrinkingSession(user_id=current_user.id)
        db.session.add(session_obj)
        db.session.flush()

        # Find the fastest time among all timed beers
        timed_values = [b['time'] for b in beers_data
                        if b.get('time') is not None and not b.get('is_vdl', False)]
        fastest_time = min(timed_values) if timed_values else None

        # Create SessionBeer records; auto-VDL anything slower than fastest
        for beer_data in beers_data:
            beer_time = beer_data.get('time')
            beer_is_vdl = beer_data.get('is_vdl', False)

            # Auto-VDL: if this single beer's time is strictly greater than fastest
            # Skip for challenges (beer_count > 1) since they naturally take longer
            beer_count = beer_data.get('beer_count', 1)
            if (not beer_is_vdl and beer_time is not None
                    and fastest_time is not None and beer_time > fastest_time
                    and beer_count == 1):
                beer_is_vdl = True

            # Check ranking for this category (top 3)
            is_pb = False
            pb_rank = None
            final_time = None if beer_is_vdl else beer_time
            if final_time is not None:
                label = beer_data.get('label')
                if label is None:
                    label_filter = SessionBeer.label.is_(None)
                else:
                    label_filter = (SessionBeer.label == label)
                top3 = db.session.query(SessionBeer.drink_time_seconds).join(
                    DrinkingSession, DrinkingSession.id == SessionBeer.session_id
                ).filter(
                    DrinkingSession.user_id == current_user.id,
                    label_filter,
                    SessionBeer.drink_time_seconds.isnot(None)
                ).order_by(SessionBeer.drink_time_seconds.asc()).limit(3).all()
                top3_times = [t[0] for t in top3]

                # Determine where this time would rank
                rank = 1
                for t in top3_times:
                    if final_time >= t:
                        rank += 1
                    else:
                        break
                if rank <= 3:
                    pb_rank = rank
                    if rank == 1:
                        is_pb = True

            beer_note = (beer_data.get('note') or '').strip() or None

            session_beer = SessionBeer(
                session_id=session_obj.id,
                drink_time_seconds=final_time,
                is_vdl=beer_is_vdl,
                beer_count=beer_data.get('beer_count', 1),
                label=beer_data.get('label'),
                is_pb=is_pb,
                pb_rank=pb_rank,
                note=beer_note
            )
            db.session.add(session_beer)

            # Extract tags from beer note
            if beer_note:
                extract_and_save_tags(beer_note)

        # Photo
        photo_filename = None
        if form.photo.data:
            photo_filename = process_upload(
                form.photo.data,
                current_app.config['UPLOAD_FOLDER']
            )

        # Create the BeerPost (single post in feed)
        post = BeerPost(
            user_id=current_user.id,
            drink_time_seconds=fastest_time,
            is_vdl=(fastest_time is None),
            session_id=session_obj.id,
            beer_count=sum(b.get('beer_count', 1) for b in beers_data),
            caption=form.caption.data,
            photo_filename=photo_filename,
            is_public=form.is_public.data,
        )
        db.session.add(post)
        db.session.flush()

        for group_id in form.groups.data:
            link = BeerPostGroup(post_id=post.id, group_id=group_id)
            db.session.add(link)

        extract_and_save_tags(form.caption.data)
        db.session.commit()
        flash('Session posted!', 'success')
        return redirect(url_for('posts.detail', id=post.id))

    flash('Something went wrong.', 'error')
    return redirect(url_for('posts.create'))


@bp.route('/<int:id>')
@login_required
def detail(id):
    post = BeerPost.query.get_or_404(id)
    if not post.visible_to(current_user):
        abort(403)

    form = CommentForm()
    comments = post._comments.order_by(Comment.created_at.asc()).all()
    return render_template('posts/detail.html', post=post, comments=comments, form=form)


@bp.route('/<int:id>/comment', methods=['POST'])
@login_required
def add_comment(id):
    post = BeerPost.query.get_or_404(id)
    if not post.visible_to(current_user):
        abort(403)

    form = CommentForm()
    if form.validate_on_submit():
        comment = Comment(
            user_id=current_user.id,
            post_id=post.id,
            body=form.body.data
        )
        db.session.add(comment)
        db.session.commit()
        flash('Comment added!', 'success')

    return redirect(url_for('posts.detail', id=post.id))


@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    post = BeerPost.query.get_or_404(id)
    if post.user_id != current_user.id:
        abort(403)

    form = BeerPostForm(obj=post)
    user_groups = GroupMember.query.filter_by(user_id=current_user.id).all()
    form.groups.choices = [(m.group.id, m.group.name) for m in user_groups]

    current_group_ids = {pg.group_id for pg in post.group_links}

    if form.validate_on_submit():
        # Only update time for regular timed posts
        if not post.is_vdl and not post.session_id:
            post.drink_time_seconds = form.drink_time_seconds.data
        post.caption = form.caption.data
        post.is_public = form.is_public.data

        # Photo handling
        remove_photo = request.form.get('remove_photo')
        if remove_photo:
            if post.photo_filename:
                post.photo_removed = True
            post.photo_filename = None
        elif form.photo.data:
            post.photo_filename = process_upload(
                form.photo.data,
                current_app.config['UPLOAD_FOLDER']
            )
            post.photo_removed = False

        # Update group links: remove old, add new
        BeerPostGroup.query.filter_by(post_id=post.id).delete()
        for group_id in form.groups.data:
            link = BeerPostGroup(post_id=post.id, group_id=group_id)
            db.session.add(link)

        extract_and_save_tags(form.caption.data)
        db.session.commit()
        flash('Post updated!', 'success')
        return redirect(url_for('posts.detail', id=post.id))

    # Pre-select current groups on GET
    if request.method == 'GET':
        form.groups.data = list(current_group_ids)

    return render_template('posts/edit.html', form=form, post=post,
                           current_group_ids=current_group_ids)


@bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    post = BeerPost.query.get_or_404(id)
    if post.user_id != current_user.id:
        abort(403)

    # Delete associated session if exists
    if post.session_id:
        session_obj = db.session.get(DrinkingSession, post.session_id)
        if session_obj:
            db.session.delete(session_obj)

    db.session.delete(post)
    db.session.commit()
    flash('Post deleted.', 'success')
    return redirect(url_for('main.feed'))

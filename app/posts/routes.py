import re
import json
from flask import render_template, redirect, url_for, flash, request, abort, current_app, jsonify
from flask_login import login_required, current_user
from . import bp
from ..extensions import db
from datetime import datetime, timedelta
from ..models import (BeerPost, BeerPostGroup, Comment, GroupMember, DrinkingSession,
                      SessionBeer, Tag, User, Group, Achievement, UserAchievement, Connection,
                      Competition, CompetitionParticipant, CompetitionBeer)
from .forms import BeerPostForm, CommentForm, SessionPostForm
from .utils import process_upload


def update_competition_counts(post):
    """Count beers for ALL active competitions the user participates in.
    Any beer post counts, regardless of which group it was shared to.
    Must be called BEFORE db.session.commit()."""
    active_participants = CompetitionParticipant.query.join(
        Competition
    ).filter(
        CompetitionParticipant.user_id == post.user_id,
        Competition.status == 'active'
    ).all()

    for participant in active_participants:
        comp = participant.competition

        # Prevent double counting
        existing = CompetitionBeer.query.filter_by(
            competition_id=comp.id,
            post_id=post.id
        ).first()
        if existing:
            continue

        beer_count = post.beer_count or 1
        comp_beer = CompetitionBeer(
            competition_id=comp.id,
            post_id=post.id,
            user_id=post.user_id,
            beer_count=beer_count,
        )
        db.session.add(comp_beer)

        participant.beer_count = (participant.beer_count or 0) + beer_count

        # Winner detection
        if participant.beer_count >= comp.target_beers and comp.status == 'active':
            comp.status = 'completed'
            comp.winner_id = post.user_id
            comp.completed_at = datetime.utcnow()


def check_achievements(user):
    """Check and award any newly earned tiered achievements. Returns list of newly unlocked."""
    newly_unlocked = []

    def _award(slug):
        if not UserAchievement.query.filter_by(user_id=user.id, achievement_slug=slug).first():
            db.session.add(UserAchievement(user_id=user.id, achievement_slug=slug))
            ach = Achievement.query.filter_by(slug=slug).first()
            if ach:
                newly_unlocked.append(ach)

    # ── Bier tiers (total beers posted) ──
    total_beers = db.session.query(db.func.sum(BeerPost.beer_count)).filter(
        BeerPost.user_id == user.id
    ).scalar() or 0
    for threshold in [1, 10, 100, 500, 1000, 2000]:
        if total_beers >= threshold:
            _award(f'bier_{threshold}')

    # ── Speed tiers (fastest single time) ──
    fastest = db.session.query(db.func.min(SessionBeer.drink_time_seconds)).join(
        DrinkingSession
    ).filter(
        DrinkingSession.user_id == user.id,
        SessionBeer.drink_time_seconds.isnot(None)
    ).scalar()
    if fastest is not None:
        for threshold in [5, 3, 2, 1.5]:
            if fastest < threshold:
                _award(f'speed_{threshold}')

    # ── Social tiers (accepted connections) ──
    conn_count = Connection.query.filter(
        db.or_(Connection.follower_id == user.id, Connection.followed_id == user.id),
        Connection.status == 'accepted'
    ).count()
    for threshold in [1, 5, 10, 25]:
        if conn_count >= threshold:
            _award(f'social_{threshold}')

    # ── Streak tiers (max consecutive days posting) ──
    recent_dates = db.session.query(
        db.func.date(BeerPost.created_at)
    ).filter(BeerPost.user_id == user.id).distinct().order_by(
        db.func.date(BeerPost.created_at).desc()
    ).limit(60).all()
    dates = []
    for r in recent_dates:
        d = r[0] if isinstance(r[0], str) else str(r[0])
        try:
            from datetime import date as dt_date
            dates.append(dt_date.fromisoformat(d))
        except (ValueError, TypeError):
            pass
    max_streak = 0
    if dates:
        streak = 1
        for i in range(1, len(dates)):
            if (dates[i - 1] - dates[i]).days == 1:
                streak += 1
            else:
                streak = 1
            if streak > max_streak:
                max_streak = streak
        max_streak = max(max_streak, 1)
    for threshold in [3, 7, 14, 30]:
        if max_streak >= threshold:
            _award(f'streak_{threshold}')

    # ── PB tiers (personal bests beaten) ──
    pb_count = db.session.query(db.func.count(SessionBeer.id)).join(
        DrinkingSession
    ).filter(
        DrinkingSession.user_id == user.id,
        SessionBeer.is_pb == True
    ).scalar() or 0
    for threshold in [1, 5, 10, 25]:
        if pb_count >= threshold:
            _award(f'pb_{threshold}')

    # ── Challenge tiers (Kan/Spies/Golden Triangle/etc completed) ──
    challenge_labels = ['Kan', 'Spies', 'Golden Triangle', 'Platinum Triangle', '1/2 Krat', 'Krat']
    challenge_count = db.session.query(db.func.count(SessionBeer.id)).join(
        DrinkingSession
    ).filter(
        DrinkingSession.user_id == user.id,
        SessionBeer.label.in_(challenge_labels),
        SessionBeer.drink_time_seconds.isnot(None)
    ).scalar() or 0
    for threshold in [1, 5, 10, 25]:
        if challenge_count >= threshold:
            _award(f'challenge_{threshold}')

    # ── Weekly tiers (most posts in last 7 days) ──
    week_ago = datetime.utcnow() - timedelta(days=7)
    week_posts = BeerPost.query.filter(
        BeerPost.user_id == user.id,
        BeerPost.created_at >= week_ago
    ).count()
    for threshold in [5, 10, 20]:
        if week_posts >= threshold:
            _award(f'weekly_{threshold}')

    # ── Competition win tiers ──
    comp_wins = Competition.query.filter_by(winner_id=user.id, status='completed').count()
    for threshold in [1, 3, 10]:
        if comp_wins >= threshold:
            _award(f'comp_win_{threshold}')

    if newly_unlocked:
        db.session.commit()

    return newly_unlocked


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
            flash('Time je bier of markeer het als VDL.', 'error')
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
        update_competition_counts(post)
        db.session.commit()

        # Check for competition wins
        for cb in post.competition_beers:
            if cb.competition.winner_id == current_user.id:
                flash(f'🏆 Je hebt de competitie "{cb.competition.title}" gewonnen!', 'success')

        flash('Bier gepost!', 'success')
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
            flash('Ongeldige sessiedata.', 'error')
            return redirect(url_for('posts.create'))

        if not beers_data or len(beers_data) < 1:
            flash('Een sessie heeft minstens 1 bier nodig.', 'error')
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
        update_competition_counts(post)
        db.session.commit()

        # Check for competition wins
        for cb in post.competition_beers:
            if cb.competition.winner_id == current_user.id:
                flash(f'🏆 Je hebt de competitie "{cb.competition.title}" gewonnen!', 'success')

        # PB celebration flash messages
        has_pb = False
        for sb in session_obj.beers:
            label_name = sb.label or 'Bier'
            if sb.pb_rank == 1 and sb.drink_time_seconds is not None:
                flash(f'NIEUW PR! Je {label_name} tijd van {sb.drink_time_seconds:.3f}s is je snelste ooit!', 'success')
                has_pb = True
            elif sb.pb_rank == 2 and sb.drink_time_seconds is not None:
                flash(f'2e snelste {label_name} ooit! {sb.drink_time_seconds:.3f}s', 'success')
                has_pb = True
            elif sb.pb_rank == 3 and sb.drink_time_seconds is not None:
                flash(f'3e snelste {label_name} ooit! {sb.drink_time_seconds:.3f}s', 'success')
                has_pb = True

        if not has_pb:
            flash('Sessie gepost!', 'success')

        # Check achievements
        new_achievements = check_achievements(current_user)
        for ach in new_achievements:
            flash(f'{ach.icon} Prestatie ontgrendeld: {ach.name}!', 'success')

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
        flash('Reactie geplaatst!', 'success')

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
        flash('Bericht bijgewerkt!', 'success')
        return redirect(url_for('posts.detail', id=post.id))

    # Pre-select current groups on GET
    if request.method == 'GET':
        form.groups.data = list(current_group_ids)

    return render_template('posts/edit.html', form=form, post=post,
                           current_group_ids=current_group_ids)


def recalculate_pb_ranks(user_id, label):
    """Recalculate pb_rank for ALL SessionBeers of a user in a given category."""
    if label is None:
        label_filter = SessionBeer.label.is_(None)
    else:
        label_filter = (SessionBeer.label == label)

    # Get all timed (non-VDL) session beers for this user+category, fastest first
    all_beers = SessionBeer.query.join(
        DrinkingSession, DrinkingSession.id == SessionBeer.session_id
    ).filter(
        DrinkingSession.user_id == user_id,
        label_filter,
        SessionBeer.drink_time_seconds.isnot(None),
        SessionBeer.is_vdl == False
    ).order_by(SessionBeer.drink_time_seconds.asc()).all()

    # Reset all ranks first
    for sb in all_beers:
        sb.pb_rank = None
        sb.is_pb = False

    # Assign ranks 1-3
    for i, sb in enumerate(all_beers[:3]):
        sb.pb_rank = i + 1
        if i == 0:
            sb.is_pb = True


@bp.route('/<int:id>/edit-time', methods=['POST'])
@login_required
def edit_time(id):
    post = BeerPost.query.get_or_404(id)
    if post.user_id != current_user.id:
        abort(403)

    data = request.get_json() if request.is_json else {}
    new_time_str = data.get('new_time') or request.form.get('new_time')
    session_beer_id = data.get('session_beer_id') or request.form.get('session_beer_id')

    try:
        new_time = float(new_time_str)
        if new_time < 0.1:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'error': 'Ongeldige tijd (min 0.1s)'}), 400

    if session_beer_id:
        # Edit a specific session beer time
        session_beer = SessionBeer.query.get_or_404(int(session_beer_id))
        if session_beer.session_id != post.session_id:
            abort(403)

        old_label = session_beer.label
        session_beer.drink_time_seconds = new_time
        session_beer.is_vdl = False

        # Recalculate auto-VDL for entire session
        session_obj = db.session.get(DrinkingSession, post.session_id)
        fastest = session_obj.fastest_time()
        for sb in session_obj.beers:
            if (sb.drink_time_seconds is not None
                    and fastest is not None
                    and sb.drink_time_seconds > fastest
                    and (sb.beer_count or 1) == 1):
                sb.is_vdl = True
            elif sb.drink_time_seconds is not None and (sb.beer_count or 1) == 1:
                sb.is_vdl = False

        # Update post's fastest time
        post.drink_time_seconds = session_obj.fastest_time()
        post.is_vdl = (post.drink_time_seconds is None)

        # Recalculate PB ranks for this category
        recalculate_pb_ranks(current_user.id, old_label)
    else:
        # Simple (non-session) post
        post.drink_time_seconds = new_time
        post.is_vdl = False

    db.session.commit()
    return jsonify({'success': True, 'new_time': f'{new_time:.3f}s'})


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
    flash('Bericht verwijderd.', 'success')
    return redirect(url_for('main.feed'))

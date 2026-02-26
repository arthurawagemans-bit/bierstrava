from flask import render_template, redirect, url_for, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload, subqueryload
from . import bp
from ..models import (BeerPost, BeerPostGroup, Connection, GroupMember,
                      Like, Comment, DrinkingSession, SessionBeer, User)
from ..extensions import db


@bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.feed'))
    return render_template('main/landing.html')


@bp.route('/feed')
@login_required
def feed():
    page = request.args.get('page', 1, type=int)
    posts = get_feed_posts(current_user, page=page)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = ''
        for post in posts.items:
            html += render_template('components/_post_card_item.html', post=post)
        return jsonify(html=html, has_more=posts.has_next)

    # Check if feed is empty — show suggestions for new/lonely users
    suggested_users = []
    if not posts.items and page == 1:
        suggested_users = User.query.filter(
            User.id != current_user.id
        ).order_by(User.created_at.desc()).limit(8).all()

    return render_template('main/feed.html', posts=posts,
                           suggested_users=suggested_users, active_nav='feed')


def get_feed_posts(user, page=1, per_page=20):
    connected_ids = db.session.query(Connection.followed_id).filter(
        Connection.follower_id == user.id,
        Connection.status == 'accepted'
    )

    my_group_ids = db.session.query(GroupMember.group_id).filter(
        GroupMember.user_id == user.id
    )

    # Collect deduplicated post IDs first (avoids UNION + joinedload duplication)
    conn_post_ids = db.session.query(BeerPost.id).filter(
        BeerPost.user_id.in_(connected_ids),
        BeerPost.user_id != user.id,
    )

    group_post_ids = db.session.query(BeerPost.id).join(BeerPostGroup).filter(
        BeerPostGroup.group_id.in_(my_group_ids),
        BeerPost.user_id != user.id,
    )

    all_ids = conn_post_ids.union(group_post_ids)

    # Fetch posts cleanly with eager loading — no UNION in the ORM query
    combined = BeerPost.query.filter(
        BeerPost.id.in_(all_ids)
    ).options(
        joinedload(BeerPost.author),
        joinedload(BeerPost.session).subqueryload(DrinkingSession.beers),
        subqueryload(BeerPost.group_links),
    ).order_by(
        BeerPost.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    # Batch load like/comment counts + user liked status to avoid N+1
    _annotate_posts(combined.items, user)

    # If no posts from connections/groups, show recent public posts instead
    if not combined.items and page == 1:
        public_posts = BeerPost.query.filter(
            BeerPost.user_id != user.id,
            BeerPost.is_public == True,
        ).options(
            joinedload(BeerPost.author),
            joinedload(BeerPost.session).subqueryload(DrinkingSession.beers),
            subqueryload(BeerPost.group_links),
        ).order_by(
            BeerPost.created_at.desc()
        ).paginate(page=1, per_page=10, error_out=False)

        _annotate_posts(public_posts.items, user)
        return public_posts

    return combined


def _annotate_posts(posts, user):
    """Batch-load like counts, comment counts, and user-liked status for a list of posts."""
    if not posts:
        return

    post_ids = [p.id for p in posts]

    # Like counts per post
    like_counts = dict(
        db.session.query(Like.post_id, db.func.count(Like.id))
        .filter(Like.post_id.in_(post_ids))
        .group_by(Like.post_id).all()
    )

    # Comment counts per post
    comment_counts = dict(
        db.session.query(Comment.post_id, db.func.count(Comment.id))
        .filter(Comment.post_id.in_(post_ids))
        .group_by(Comment.post_id).all()
    )

    # Which posts the current user liked
    user_liked = set(
        row[0] for row in
        db.session.query(Like.post_id)
        .filter(Like.post_id.in_(post_ids), Like.user_id == user.id).all()
    )

    for post in posts:
        post._like_count = like_counts.get(post.id, 0)
        post._comment_count = comment_counts.get(post.id, 0)
        post._user_liked = post.id in user_liked

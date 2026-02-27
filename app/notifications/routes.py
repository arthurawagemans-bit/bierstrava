from flask import render_template
from flask_login import login_required, current_user
from . import bp
from ..extensions import db, cache
from ..models import Notification


@bp.route('/')
@login_required
def index():
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).limit(50).all()

    # Mark all as read
    Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).update({'is_read': True})
    db.session.commit()
    cache.delete(f'notif_count:{current_user.id}')

    return render_template('notifications/index.html',
                           notifications=notifications,
                           active_nav='')

from ..extensions import db, cache
from ..models import Notification


def notify(user_id, actor_id, notif_type, post_id=None):
    """Create a notification. Skips if actor == user (no self-notifications)."""
    if user_id == actor_id:
        return
    n = Notification(user_id=user_id, actor_id=actor_id, type=notif_type, post_id=post_id)
    db.session.add(n)
    cache.delete(f'notif_count:{user_id}')


def get_unread_count(user_id):
    """Get unread notification count (cached 60s)."""
    key = f'notif_count:{user_id}'
    count = cache.get(key)
    if count is None:
        count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
        cache.set(key, count, timeout=60)
    return count

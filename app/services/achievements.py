"""Achievement checking — extracted from posts/routes.py."""

from ..extensions import db
from ..models import Achievement, UserAchievement
from .stats import get_user_achievement_stats


def check_achievements(user):
    """Check and award any newly earned tiered achievements.
    Returns list of newly unlocked Achievement objects."""
    newly_unlocked = []

    def _award(slug):
        if not UserAchievement.query.filter_by(
            user_id=user.id, achievement_slug=slug
        ).first():
            db.session.add(UserAchievement(
                user_id=user.id, achievement_slug=slug
            ))
            ach = Achievement.query.filter_by(slug=slug).first()
            if ach:
                newly_unlocked.append(ach)

    stats = get_user_achievement_stats(user.id)

    # Bier tiers
    for threshold in [1, 10, 100, 500, 1000, 2000]:
        if stats['total_beers'] >= threshold:
            _award(f'bier_{threshold}')

    # Speed tiers
    if stats['fastest'] is not None:
        for threshold in [5, 3, 2, 1.5]:
            if stats['fastest'] < threshold:
                _award(f'speed_{threshold}')

    # Social tiers
    for threshold in [1, 5, 10, 25]:
        if stats['conn_count'] >= threshold:
            _award(f'social_{threshold}')

    # Streak tiers
    for threshold in [3, 7, 14, 30]:
        if stats['max_streak'] >= threshold:
            _award(f'streak_{threshold}')

    # PB tiers
    for threshold in [1, 5, 10, 25]:
        if stats['pb_count'] >= threshold:
            _award(f'pb_{threshold}')

    # Challenge tiers
    for threshold in [1, 5, 10, 25]:
        if stats['challenge_count'] >= threshold:
            _award(f'challenge_{threshold}')

    # Weekly tiers
    for threshold in [5, 10, 20]:
        if stats['week_posts'] >= threshold:
            _award(f'weekly_{threshold}')

    # Competition win tiers
    for threshold in [1, 3, 10]:
        if stats['comp_wins'] >= threshold:
            _award(f'comp_win_{threshold}')

    if newly_unlocked:
        db.session.commit()

    return newly_unlocked

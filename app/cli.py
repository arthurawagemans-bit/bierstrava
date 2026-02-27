import click
from flask.cli import with_appcontext
from .extensions import db


ACHIEVEMENTS = [
    # Bier tiers (total beers posted)
    ('bier_1', 'Eerste Bier', '🍺', 'Post je eerste bier'),
    ('bier_10', '10 Bieren', '🍺', 'Post 10 bieren'),
    ('bier_100', 'Centurion', '🍺', 'Post 100 bieren'),
    ('bier_500', 'Legende', '🍺', 'Post 500 bieren'),
    ('bier_1000', 'Machine', '🍺', 'Post 1000 bieren'),
    ('bier_2000', 'GOAT', '🍺', 'Post 2000 bieren'),
    # Speed tiers (fastest single time)
    ('speed_5', 'Vlugge Slok', '🏃', 'Onder 5 seconden'),
    ('speed_3', 'Snelheidsduivel', '🏃', 'Onder 3 seconden'),
    ('speed_2', 'Bliksem', '🏃', 'Onder 2 seconden'),
    ('speed_1.5', 'Onmenselijk', '🏃', 'Onder 1.5 seconden'),
    # Social tiers (connections)
    ('social_1', 'Eerste Maat', '🫂', 'Verbind met 1 persoon'),
    ('social_5', 'Sociaal', '🫂', 'Verbind met 5 mensen'),
    ('social_10', 'Populair', '🫂', 'Verbind met 10 mensen'),
    ('social_25', 'Influencer', '🫂', 'Verbind met 25 mensen'),
    # Streak tiers (consecutive days posting)
    ('streak_3', 'Hat Trick', '🎯', '3 dagen op rij'),
    ('streak_7', 'Volle Week', '🎯', '7 dagen op rij'),
    ('streak_14', 'Twee Weken', '🎯', '14 dagen op rij'),
    ('streak_30', 'IJzeren Wil', '🎯', '30 dagen op rij'),
    # PB tiers (personal bests beaten)
    ('pb_1', 'Recordbreker', '🥇', 'Versla je PR'),
    ('pb_5', 'PR Jager', '🥇', 'Versla je PR 5 keer'),
    ('pb_10', 'PR Machine', '🥇', 'Versla je PR 10 keer'),
    ('pb_25', 'PR Legende', '🥇', 'Versla je PR 25 keer'),
    # Challenge tiers (Kan/Spies/etc completed)
    ('challenge_1', 'Uitdager', '🏆', 'Voltooi een challenge'),
    ('challenge_5', 'Veteraan', '🏆', 'Voltooi 5 challenges'),
    ('challenge_10', 'Kampioen', '🏆', 'Voltooi 10 challenges'),
    ('challenge_25', 'Meester', '🏆', 'Voltooi 25 challenges'),
    # Weekly tiers (posts in one week)
    ('weekly_5', 'On Fire', '🔥', '5 posts in één week'),
    ('weekly_10', 'Vlammend', '🔥', '10 posts in één week'),
    ('weekly_20', 'Inferno', '🔥', '20 posts in één week'),
    # Competition winner tiers
    ('comp_win_1', 'Eerste Overwinning', '🏆', 'Win je eerste competitie'),
    ('comp_win_3', 'Competitiebeest', '🏆', 'Win 3 competities'),
    ('comp_win_10', 'Onverslaanbaar', '🏆', 'Win 10 competities'),
]


def seed_achievements_data():
    """Upsert all achievements. Safe to run multiple times."""
    from .models import Achievement, UserAchievement

    new_slugs = {slug for slug, _, _, _ in ACHIEVEMENTS}

    # Remove old non-tiered achievements
    old_achs = Achievement.query.filter(~Achievement.slug.in_(new_slugs)).all()
    for old in old_achs:
        UserAchievement.query.filter_by(achievement_slug=old.slug).delete()
        db.session.delete(old)

    # Upsert current achievements
    for slug, name, icon, desc in ACHIEVEMENTS:
        existing = Achievement.query.filter_by(slug=slug).first()
        if existing:
            existing.name = name
            existing.icon = icon
            existing.description = desc
        else:
            db.session.add(Achievement(slug=slug, name=name, icon=icon, description=desc))

    db.session.commit()


@click.command('seed-achievements')
@with_appcontext
def seed_achievements():
    """Seed or update all achievements."""
    seed_achievements_data()
    click.echo('Achievements seeded successfully.')

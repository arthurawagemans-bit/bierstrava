"""Competition count updates — extracted from posts/routes.py."""

from datetime import datetime
from ..extensions import db
from ..models import (Competition, CompetitionParticipant, CompetitionBeer)


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

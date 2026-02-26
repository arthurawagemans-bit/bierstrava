from datetime import datetime
from flask import render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from . import bp
from ..extensions import db
from ..models import (Group, GroupMember, Competition, CompetitionParticipant,
                      CompetitionBeer, BeerPost, User)
from .forms import CreateCompetitionForm


@bp.route('/groep/<int:group_id>')
@login_required
def list_for_group(group_id):
    group = Group.query.get_or_404(group_id)
    if not group.is_member(current_user):
        abort(403)

    active = Competition.query.filter_by(
        group_id=group_id, status='active'
    ).order_by(Competition.created_at.desc()).all()

    completed = Competition.query.filter_by(
        group_id=group_id, status='completed'
    ).order_by(Competition.completed_at.desc()).all()

    return render_template('competitions/list.html',
                           group=group,
                           active_competitions=active,
                           completed_competitions=completed)


@bp.route('/groep/<int:group_id>/nieuw', methods=['GET', 'POST'])
@login_required
def create(group_id):
    group = Group.query.get_or_404(group_id)
    if not group.is_member(current_user):
        abort(403)

    form = CreateCompetitionForm()
    if form.validate_on_submit():
        comp = Competition(
            group_id=group.id,
            created_by_id=current_user.id,
            title=form.title.data,
            description=form.description.data or '',
            target_beers=form.target_beers.data,
        )
        db.session.add(comp)
        db.session.flush()

        # Auto-join creator
        participant = CompetitionParticipant(
            competition_id=comp.id,
            user_id=current_user.id,
        )
        db.session.add(participant)
        db.session.commit()

        flash(f'Competitie "{comp.title}" gestart!', 'success')
        return redirect(url_for('competitions.detail', id=comp.id))

    return render_template('competitions/create.html', form=form, group=group)


@bp.route('/<int:id>')
@login_required
def detail(id):
    comp = Competition.query.get_or_404(id)
    group = comp.group
    if not group.is_member(current_user):
        abort(403)

    # Participants sorted by beer_count desc
    participants = CompetitionParticipant.query.filter_by(
        competition_id=comp.id
    ).order_by(CompetitionParticipant.beer_count.desc()).all()

    # Eager-load user info
    for p in participants:
        _ = p.user  # trigger lazy load

    is_participant = comp.is_participant(current_user)
    is_admin = group.is_admin(current_user)

    # Recent beers in this competition with post info
    recent_beers = CompetitionBeer.query.filter_by(
        competition_id=comp.id
    ).order_by(CompetitionBeer.created_at.desc()).limit(30).all()

    return render_template('competitions/detail.html',
                           comp=comp, group=group,
                           participants=participants,
                           is_participant=is_participant,
                           is_admin=is_admin,
                           recent_beers=recent_beers)


@bp.route('/<int:id>/deelnemen', methods=['POST'])
@login_required
def join(id):
    comp = Competition.query.get_or_404(id)
    if not comp.group.is_member(current_user):
        abort(403)
    if comp.status != 'active':
        flash('Deze competitie is al afgelopen.', 'info')
        return redirect(url_for('competitions.detail', id=comp.id))
    if comp.is_participant(current_user):
        flash('Je doet al mee aan deze competitie.', 'info')
        return redirect(url_for('competitions.detail', id=comp.id))

    participant = CompetitionParticipant(
        competition_id=comp.id,
        user_id=current_user.id,
    )
    db.session.add(participant)
    db.session.commit()

    flash('Je doet mee aan de competitie!', 'success')
    return redirect(url_for('competitions.detail', id=comp.id))


@bp.route('/<int:id>/verlaten', methods=['POST'])
@login_required
def leave(id):
    comp = Competition.query.get_or_404(id)
    if comp.status != 'active':
        flash('Deze competitie is al afgelopen.', 'info')
        return redirect(url_for('competitions.detail', id=comp.id))

    participant = CompetitionParticipant.query.filter_by(
        competition_id=comp.id, user_id=current_user.id
    ).first()
    if not participant:
        abort(400)

    # Remove participant and their competition beers
    CompetitionBeer.query.filter_by(
        competition_id=comp.id, user_id=current_user.id
    ).delete()
    db.session.delete(participant)
    db.session.commit()

    flash('Je hebt de competitie verlaten.', 'success')
    return redirect(url_for('competitions.list_for_group', group_id=comp.group_id))


@bp.route('/<int:id>/verwijderen', methods=['POST'])
@login_required
def delete(id):
    comp = Competition.query.get_or_404(id)
    group = comp.group
    if not group.is_admin(current_user):
        abort(403)

    group_id = comp.group_id
    db.session.delete(comp)
    db.session.commit()

    flash('Competitie verwijderd.', 'success')
    return redirect(url_for('competitions.list_for_group', group_id=group_id))

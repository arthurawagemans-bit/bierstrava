from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from . import bp
from ..extensions import db
from .forms import SettingsForm, ChangePasswordForm


@bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    settings_form = SettingsForm(obj=current_user)
    password_form = ChangePasswordForm()

    pending_connections = current_user.pending_request_count()

    return render_template('settings/index.html',
                           settings_form=settings_form,
                           password_form=password_form,
                           pending_connections=pending_connections)


@bp.route('/privacy', methods=['POST'])
@login_required
def update_privacy():
    form = SettingsForm()
    if form.validate_on_submit():
        current_user.is_private = form.is_private.data
        current_user.countdown_enabled = form.countdown_enabled.data
        db.session.commit()
        flash('Instellingen opgeslagen!', 'success')
    return redirect(url_for('settings.index'))


@bp.route('/password', methods=['POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash('Huidig wachtwoord is onjuist.', 'error')
            return redirect(url_for('settings.index'))

        current_user.set_password(form.new_password.data)
        db.session.commit()
        flash('Wachtwoord gewijzigd!', 'success')
    return redirect(url_for('settings.index'))

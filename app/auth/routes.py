import logging
from urllib.parse import urlparse
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from . import bp
from ..extensions import db, limiter
from ..models import User
from .forms import LoginForm, RegisterForm

logger = logging.getLogger(__name__)


@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.feed'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.lower()).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            logger.info('User logged in: %s', user.username)
            next_page = request.args.get('next')
            # Prevent open redirect — only allow relative URLs
            if next_page and urlparse(next_page).netloc:
                next_page = None
            return redirect(next_page or url_for('main.feed'))
        logger.warning('Failed login attempt for: %s', form.username.data.lower())
        flash('Ongeldige gebruikersnaam of wachtwoord.', 'error')

    return render_template('auth/login.html', form=form)


@bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.feed'))

    form = RegisterForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data.lower(),
            display_name=form.username.data,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        logger.info('New user registered: %s', user.username)
        return redirect(url_for('auth.onboarding'))

    return render_template('auth/register.html', form=form)


@bp.route('/welcome')
@login_required
def onboarding():
    return render_template('auth/onboarding.html')


@bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('Je bent uitgelogd.', 'info')
    return redirect(url_for('auth.login'))

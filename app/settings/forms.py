from flask_wtf import FlaskForm
from wtforms import PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, Optional


class SettingsForm(FlaskForm):
    is_private = BooleanField('Private Account')
    countdown_enabled = BooleanField('Timer Countdown')
    hide_own_posts = BooleanField('Hide Own Posts')
    submit = SubmitField('Save Settings')


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm New Password', validators=[
        DataRequired(), EqualTo('new_password', message='Passwords must match.')
    ])
    submit = SubmitField('Change Password')

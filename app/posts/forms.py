from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (FloatField, TextAreaField, BooleanField, SelectMultipleField,
                     SubmitField, HiddenField, IntegerField)
from wtforms.validators import DataRequired, Length, NumberRange, Optional
from wtforms.widgets import CheckboxInput, ListWidget


class BeerPostForm(FlaskForm):
    drink_time_seconds = FloatField('Time (seconds)', validators=[
        Optional(),
        NumberRange(min=0.1, max=3600, message='Time must be between 0.1 and 3600 seconds.')
    ])
    is_vdl = HiddenField('VDL', default='')
    beer_count = IntegerField('Beer Count', validators=[Optional(), NumberRange(min=1, max=24)], default=1)
    caption = TextAreaField('Caption', validators=[Optional(), Length(max=500)])
    photo = FileField('Photo', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Images only!')
    ])
    is_public = BooleanField('Make this post public')
    groups = SelectMultipleField('Share with groups', coerce=int,
                                 widget=ListWidget(prefix_label=False),
                                 option_widget=CheckboxInput())
    submit = SubmitField('Post Beer')


class SessionPostForm(FlaskForm):
    session_beers_json = HiddenField('Session Beers')
    caption = TextAreaField('Caption', validators=[Optional(), Length(max=500)])
    photo = FileField('Photo', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Images only!')
    ])
    is_public = BooleanField('Make this post public')
    groups = SelectMultipleField('Share with groups', coerce=int,
                                 widget=ListWidget(prefix_label=False),
                                 option_widget=CheckboxInput())
    submit = SubmitField('Post Session')


class CommentForm(FlaskForm):
    body = TextAreaField('Comment', validators=[DataRequired(), Length(min=1, max=500)])
    submit = SubmitField('Post')

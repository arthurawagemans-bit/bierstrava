from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class CreateCompetitionForm(FlaskForm):
    title = StringField('Titel', validators=[DataRequired(), Length(min=2, max=100)])
    description = TextAreaField('Beschrijving', validators=[Optional(), Length(max=500)])
    target_beers = IntegerField('Doel (aantal bieren)', validators=[
        DataRequired(), NumberRange(min=1, max=10000, message='Doel moet tussen 1 en 10000 zijn.')
    ])
    submit = SubmitField('Competitie Starten')

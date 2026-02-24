from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length, Optional


class EditProfileForm(FlaskForm):
    display_name = StringField('Display Name', validators=[DataRequired(), Length(min=1, max=50)])
    bio = TextAreaField('Bio', validators=[Optional(), Length(max=300)])
    avatar = FileField('Profile Photo', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Images only!')
    ])
    submit = SubmitField('Save Changes')

from flask import Blueprint

bp = Blueprint('profiles', __name__, template_folder='../templates/profiles')
from . import routes  # noqa: E402, F401

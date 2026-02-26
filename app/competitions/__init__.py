from flask import Blueprint

bp = Blueprint('competitions', __name__, template_folder='../templates/competitions')
from . import routes  # noqa: E402, F401

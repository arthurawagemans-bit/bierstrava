from flask import Blueprint

bp = Blueprint('settings', __name__, template_folder='../templates/settings')
from . import routes  # noqa: E402, F401

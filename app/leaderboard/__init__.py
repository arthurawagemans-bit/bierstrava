from flask import Blueprint

bp = Blueprint('leaderboard', __name__, template_folder='../templates/leaderboard')
from . import routes  # noqa: E402, F401

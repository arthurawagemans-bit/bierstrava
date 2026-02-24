from flask import Blueprint

bp = Blueprint('groups', __name__, template_folder='../templates/groups')
from . import routes  # noqa: E402, F401

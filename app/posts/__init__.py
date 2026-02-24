from flask import Blueprint

bp = Blueprint('posts', __name__, template_folder='../templates/posts')
from . import routes  # noqa: E402, F401

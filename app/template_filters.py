import re
from datetime import datetime
from markupsafe import Markup, escape


def timeago(dt):
    now = datetime.utcnow()
    diff = now - dt
    seconds = diff.total_seconds()

    if seconds < 60:
        return 'just now'
    elif seconds < 3600:
        mins = int(seconds // 60)
        return f'{mins}m ago'
    elif seconds < 86400:
        hours = int(seconds // 3600)
        return f'{hours}h ago'
    elif seconds < 604800:
        days = int(seconds // 86400)
        return f'{days}d ago'
    else:
        return dt.strftime('%b %d')


def format_time(seconds):
    if seconds is None:
        return '--'
    if seconds >= 3600:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f'{h}:{m:02d}:{s:06.3f}'
    elif seconds >= 60:
        m = int(seconds // 60)
        s = seconds % 60
        return f'{m}:{s:06.3f}'
    return f'{seconds:.3f}s'


def render_mentions(text):
    """Convert @mentions into styled maroon text."""
    if not text:
        return ''
    escaped = escape(text)
    result = re.sub(r'@(\w+)', r'<span class="text-maroon font-semibold">@\1</span>', str(escaped))
    return Markup(result)

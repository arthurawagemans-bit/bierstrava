import click
from app import create_app

app = create_app()


@app.cli.command('change-password')
@click.argument('username')
@click.argument('new_password')
def change_password(username, new_password):
    """Change a user's password. Usage: flask change-password <username> <new_password>"""
    from app.extensions import db
    from app.models import User
    user = User.query.filter_by(username=username).first()
    if not user:
        click.echo(f'User "{username}" not found.')
        return
    user.set_password(new_password)
    db.session.commit()
    click.echo(f'Password changed for {user.username} ({user.display_name})')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)

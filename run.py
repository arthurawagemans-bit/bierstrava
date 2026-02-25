import os
import shutil
import tarfile
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


@app.cli.command('restore')
@click.argument('backup_file')
def restore(backup_file):
    """Restore database and uploads from a backup .tar.gz file.

    Usage: flask restore backups/bierstrava-2026-02-25-120000.tar.gz
    """
    if not os.path.isfile(backup_file):
        click.echo(f'File not found: {backup_file}')
        return

    if not tarfile.is_tarfile(backup_file):
        click.echo(f'Not a valid tar.gz file: {backup_file}')
        return

    db_uri = app.config['SQLALCHEMY_DATABASE_URI']
    db_path = db_uri.replace('sqlite:///', '')
    upload_folder = app.config['UPLOAD_FOLDER']

    click.echo(f'Restoring from: {backup_file}')
    click.echo(f'  Database → {db_path}')
    click.echo(f'  Uploads  → {upload_folder}')

    if not click.confirm('This will overwrite existing data. Continue?'):
        click.echo('Aborted.')
        return

    with tarfile.open(backup_file, 'r:gz') as tar:
        members = tar.getnames()
        click.echo(f'  Archive contains {len(members)} file(s)')

        # Extract database
        if 'bierstrava.db' in members:
            os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
            with tar.extractfile('bierstrava.db') as src:
                with open(db_path, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
            click.echo(f'  Restored database ({os.path.getsize(db_path)} bytes)')
        else:
            click.echo('  WARNING: No bierstrava.db found in archive')

        # Extract uploads
        upload_files = [m for m in members if m.startswith('uploads/')]
        if upload_files:
            os.makedirs(upload_folder, exist_ok=True)
            for member_name in upload_files:
                fname = os.path.basename(member_name)
                if not fname:
                    continue
                with tar.extractfile(member_name) as src:
                    dest_path = os.path.join(upload_folder, fname)
                    with open(dest_path, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
            click.echo(f'  Restored {len(upload_files)} upload(s)')
        else:
            click.echo('  No uploads in archive')

    click.echo('Restore complete!')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)

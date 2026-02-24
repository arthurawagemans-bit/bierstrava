import os
import uuid
from PIL import Image


ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def process_upload(file_storage, upload_folder, max_size=(1080, 1080), quality=85):
    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = os.path.join(upload_folder, filename)

    img = Image.open(file_storage)

    # Fix EXIF orientation
    try:
        from PIL import ImageOps
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    img.thumbnail(max_size, Image.LANCZOS)

    if img.mode in ('RGBA', 'P', 'LA'):
        img = img.convert('RGB')

    img.save(filepath, 'JPEG', quality=quality, optimize=True)
    return filename

import os
import uuid
from PIL import Image, ImageOps


ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def process_upload(file_storage, upload_folder, max_size=(800, 800), quality=70):
    filename = f"{uuid.uuid4().hex}.webp"
    filepath = os.path.join(upload_folder, filename)

    img = Image.open(file_storage)

    # Fix EXIF orientation
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    # Strip all metadata (EXIF, ICC profiles, etc.)
    img.thumbnail(max_size, Image.LANCZOS)

    if img.mode in ('RGBA', 'P', 'LA'):
        img = img.convert('RGB')

    img.save(filepath, 'WEBP', quality=quality, method=4)
    return filename

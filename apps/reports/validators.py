import os
from django.core.exceptions import ValidationError
from PIL import Image

def validate_image_content(file):
    """
    Validates that the uploaded file is a valid image (JPG or PNG)
    and does not exceed the size limit (5MB).
    """
    # 1. Check file size (5MB limit)
    max_size = 5 * 1024 * 1024
    if file.size > max_size:
        raise ValidationError("Сликата не смее да биде поголема од 5MB.")

    # 2. Check MIME type (content_type is set by Django's UploadedFile)
    content_type = getattr(file, "content_type", "")
    if content_type and content_type not in {"image/jpeg", "image/png"}:
        raise ValidationError("Дозволени се само JPG или PNG слики.")

    # 3. Deep validation using Pillow
    try:
        # Seek to beginning just in case
        file.seek(0)
        img = Image.open(file)
        img.verify()
        
        # Some formats might pass verify but we only want JPEG/PNG
        if img.format not in {"JPEG", "PNG"}:
            raise ValidationError(f"Датотеката е во {img.format} формат, а дозволени се само JPG и PNG.")
        
        # Seek back to 0 so other processes can read it
        file.seek(0)
    except Exception:
        raise ValidationError("Датотеката не е валидна слика.")

    return file

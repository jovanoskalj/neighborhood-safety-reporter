import io
import pytest
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from apps.reports.validators import validate_image_content
from apps.reports.forms import ReportSubmissionForm, ReportCreateForm
from apps.reports.models import Report

def generate_image(format='JPEG', size=(100, 100), color='red'):
    file = io.BytesIO()
    image = Image.new('RGB', size, color=color)
    image.save(file, format=format)
    file.seek(0)
    return file

@pytest.mark.parametrize("format,content_type", [
    ("JPEG", "image/jpeg"),
    ("PNG", "image/png"),
])
def test_valid_images_pass(format, content_type):
    img_data = generate_image(format=format)
    uploaded_file = SimpleUploadedFile(f"test.{format.lower()}", img_data.read(), content_type=content_type)
    
    # Should not raise any error
    validate_image_content(uploaded_file)

def test_oversized_file_rejected():
    # Create a 6MB file
    size = 6 * 1024 * 1024
    large_data = b"0" * size
    uploaded_file = SimpleUploadedFile("large.jpg", large_data, content_type="image/jpeg")
    
    with pytest.raises(ValidationError) as excinfo:
        validate_image_content(uploaded_file)
    assert "поголема од 5MB" in str(excinfo.value)

def test_invalid_mime_type_rejected():
    img_data = generate_image(format='JPEG')
    uploaded_file = SimpleUploadedFile("test.jpg", img_data.read(), content_type="application/pdf")
    
    with pytest.raises(ValidationError) as excinfo:
        validate_image_content(uploaded_file)
    assert "JPG или PNG" in str(excinfo.value)

def test_corrupt_image_rejected():
    # File with jpg extension but random junk content
    uploaded_file = SimpleUploadedFile("fake.jpg", b"not an image data", content_type="image/jpeg")
    
    with pytest.raises(ValidationError) as excinfo:
        validate_image_content(uploaded_file)
    assert "не е валидна слика" in str(excinfo.value)

def test_unsupported_format_rejected():
    # GIF is an image but we only want JPG/PNG
    img_data = generate_image(format='GIF')
    uploaded_file = SimpleUploadedFile("test.gif", img_data.read(), content_type="image/gif")
    
    with pytest.raises(ValidationError):
        validate_image_content(uploaded_file)

@pytest.mark.django_db
def test_form_validation_integration():
    # Test that ReportSubmissionForm uses the validator
    img_data = generate_image(format='JPEG')
    uploaded_file = SimpleUploadedFile("test.jpg", img_data.read(), content_type="image/jpeg")
    
    form = ReportSubmissionForm(data={
        'description': 'Test report',
        'latitude': 41.9,
        'longitude': 21.4,
        'category': 'other',
        'priority': 'normal',
        'municipality': 'centar'
    }, files={'image': uploaded_file})
    
    # We need to mock the user for the form if it requires it, 
    # but ReportSubmissionForm doesn't seem to require user in __init__ or clean
    assert form.is_valid(), form.errors

@pytest.mark.django_db
def test_api_form_validation_integration():
    # Test that ReportCreateForm also uses the validator
    img_data = b"random junk"
    uploaded_file = SimpleUploadedFile("fake.jpg", img_data, content_type="image/jpeg")
    
    form = ReportCreateForm(data={
        'description': 'Test report',
        'latitude': 41.9,
        'longitude': 21.4
    }, files={'image': uploaded_file})
    
    assert not form.is_valid()
    assert 'image' in form.errors
    error_msg = str(form.errors['image'])
    assert "не е валидна слика" in error_msg or "Upload a valid image" in error_msg

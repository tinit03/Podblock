import os
import re


def allowed_file(filename, allowed_extensions):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


def save_file(filename, upload_folder):
    """Save the uploaded file to the specified folder."""
    file_path = os.path.join(upload_folder, filename)
    return file_path


def add_intro(audiosegment):
    """Add an intro to an audio segment."""
    intro = AudioSegment.from_file('resources/intro.mp3')
    return intro + audiosegment

def sanitize_filename(filename):
    """Removes or replaces illegal characters from filenames."""
    return re.sub(r'[<>:"/\\|?*]', '_', filename)  # Replace invalid characters with "_"

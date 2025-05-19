import os
import pytest
from server.helpers.file_helpers import allowed_file, save_file, sanitize_filename  # Bytt ut "your_module" med riktig filnavn


def test_allowed_file():
    """Test allowed_file function with valid and invalid file extensions."""
    allowed_extensions = {"wav", "flacc", "mp3"}

    #  Valid file-types
    assert allowed_file("image.wav", allowed_extensions) is True
    assert allowed_file("audio.mp3", allowed_extensions) is True

    # invalid file-types
    assert allowed_file("document.pdf", allowed_extensions) is False
    assert allowed_file("script.exe", allowed_extensions) is False

    # files with no extension
    assert allowed_file("nofileextension", allowed_extensions) is False


def test_save_file():
    """Test that save_file returns the correct file path."""
    upload_folder = "/uploads"

    expected_path = os.path.abspath(os.path.normpath("/uploads/testfile.txt"))
    result_path = os.path.abspath(save_file("testfile.txt", upload_folder))
    assert result_path == expected_path

    expected_path = os.path.abspath(os.path.normpath("/uploads/audio.mp3"))
    result_path = os.path.abspath(save_file("audio.mp3", upload_folder))
    assert result_path == expected_path
def test_sanitize_filename():
    """Test sanitize_filename function to ensure invalid characters are removed."""

    # Remove invalid char in files
    assert sanitize_filename('test<>file.txt') == 'test__file.txt'
    assert sanitize_filename('my|file?.mp3') == 'my_file_.mp3'

    # Not change anything if file name is normal
    assert sanitize_filename('normal_file.txt') == 'normal_file.txt'
    assert sanitize_filename('audio.mp3') == 'audio.mp3'
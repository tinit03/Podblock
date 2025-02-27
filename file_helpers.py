import os


def allowed_file(filename, allowed_extensions):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


def save_file(filename, upload_folder):
    """Save the uploaded file to the specified folder."""
    file_path = os.path.join(upload_folder, filename)
    #file.save(file_path)
    return file_path

# def download_file(url, upload_folder):
#     """Download a file from a URL and save it to the specified folder."""
#     response = requests.get(url, stream=True)
#     filename = url.split("/")[-1].split('?')[0]
#     file_path = os.path.join(upload_folder, filename)
#     with open(file_path, 'wb') as f:
#         for chunk in response.iter_content(chunk_size=8192):
#             f.write(chunk)
#     return file_path

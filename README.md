# Podcasts for comostravolta

A simple project for uploading audio tracks and serving subtitle JSON files generated directly from audio.

### Requirements
- `python 3.11+`
- `ffmpeg` available in PATH (or installed via `imageio-ffmpeg`)

Install dependencies:
`pip install -r requirements.txt`

Run the server:
`python manage.py runserver`

Workflow:
- Open `/podcast/manage` as a staff user.
- Upload an audio file.
- The app generates subtitle JSON with Whisper `large` and saves it in `media/subtitles/`.

Add and manage tracks via the Admin site at `/admin` (user: `admin`, password: `admin`) 

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from subtitles import get_subtitles, save_segments_json
from podcast_management.services import SUPPORTED_AUDIO_EXTENSIONS


class Command(BaseCommand):
    help = 'Generate JSON subtitle segments for audio files in media/audio'

    def add_arguments(self, parser):
        parser.add_argument('--model', default='small', help='Whisper model name')
        parser.add_argument('--force', action='store_true', help='Regenerate files even if JSON already exists')

    def handle(self, *args, **options):
        audio_dir = Path(settings.MEDIA_ROOT) / 'audio'
        subtitles_dir = Path(settings.MEDIA_ROOT) / 'subtitles'
        subtitles_dir.mkdir(parents=True, exist_ok=True)

        if not audio_dir.exists():
            self.stdout.write(self.style.WARNING(f'Audio directory not found: {audio_dir}'))
            self.stdout.write('Create it and place audio files inside, then run this command again.')
            return

        model_name = options['model']
        force = options['force']

        processed = 0
        skipped = 0
        for audio_file in sorted(audio_dir.iterdir()):
            if not audio_file.is_file() or audio_file.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
                continue

            output_file = subtitles_dir / f'{audio_file.stem}.json'
            if output_file.exists() and not force:
                skipped += 1
                self.stdout.write(f'Skipping existing: {output_file.name}')
                continue

            self.stdout.write(f'Transcribing: {audio_file.name}')
            segments = get_subtitles(str(audio_file), model_name=model_name)
            save_segments_json(segments, output_file)
            self.stdout.write(self.style.SUCCESS(f'Saved: {output_file.name} ({len(segments)} segments)'))
            processed += 1

        self.stdout.write(self.style.SUCCESS(f'Done. Processed={processed}, Skipped={skipped}'))

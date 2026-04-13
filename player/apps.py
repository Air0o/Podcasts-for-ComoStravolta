import os
import sys

from django.conf import settings
from django.apps import AppConfig

from subtitles import preload_model_in_background


class PlayerConfig(AppConfig):
    name = 'player'

    def ready(self):
        if not getattr(settings, 'WHISPER_PRELOAD_ON_STARTUP', True):
            return

        # Django's autoreloader spawns a parent process; only preload in the serving child.
        if 'runserver' in sys.argv and os.environ.get('RUN_MAIN') != 'true':
            return

        blocked_commands = {'migrate', 'makemigrations', 'collectstatic', 'test', 'shell'}
        if any(command in sys.argv for command in blocked_commands):
            return

        model_name = getattr(settings, 'WHISPER_MODEL_NAME', 'medium')
        preload_model_in_background(model_name)

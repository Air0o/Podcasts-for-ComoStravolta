import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings


class PlayerViewsTests(TestCase):
	def setUp(self):
		super().setUp()
		self.temp_media_dir = tempfile.mkdtemp(prefix="vr_media_")
		self.settings_override = override_settings(MEDIA_ROOT=self.temp_media_dir)
		self.settings_override.enable()
		User = get_user_model()
		self.staff_user = User.objects.create_user(
			username="staff",
			email="staff@example.com",
			password="password123",
			is_staff=True,
			is_superuser=True,
		)
		self.client.force_login(self.staff_user)

	def tearDown(self):
		self.settings_override.disable()
		shutil.rmtree(self.temp_media_dir, ignore_errors=True)
		super().tearDown()

	def test_index_renders(self):
		response = self.client.get("/")
		self.assertEqual(response.status_code, 200)

	def test_subtitle_endpoint_returns_404_without_tracks(self):
		response = self.client.get("/api/subtitles/")
		self.assertEqual(response.status_code, 404)

	def test_admin_tracks_can_remove_existing_track(self):
		audio_dir = Path(self.temp_media_dir) / "audio"
		subtitle_dir = Path(self.temp_media_dir) / "subtitles"
		audio_dir.mkdir(parents=True, exist_ok=True)
		subtitle_dir.mkdir(parents=True, exist_ok=True)
		(audio_dir / "test.mp3").write_bytes(b"dummy")
		(subtitle_dir / "test.json").write_text("[]", encoding="utf-8")

		response = self.client.post(
			"/manage/tracks/",
			{"action": "delete", "track_slug": "test"},
		)

		self.assertEqual(response.status_code, 302)
		self.assertFalse((audio_dir / "test.mp3").exists())
		self.assertFalse((subtitle_dir / "test.json").exists())

	@patch("player.views.get_subtitles")
	def test_subtitle_endpoint_auto_generates_when_missing(self, mock_get_subtitles):
		audio_dir = Path(self.temp_media_dir) / "audio"
		audio_dir.mkdir(parents=True, exist_ok=True)
		(audio_dir / "test.mp3").write_bytes(b"dummy")

		mock_get_subtitles.return_value = [
			{"start": 0.0, "end": 1.2, "text": "Hello world"},
		]

		response = self.client.get("/api/subtitles/?track=test")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["segments"][0]["text"], "Hello world")

		subtitle_file = Path(self.temp_media_dir) / "subtitles" / "test.json"
		self.assertTrue(subtitle_file.exists())

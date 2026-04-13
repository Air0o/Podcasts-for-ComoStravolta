import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from player import views as player_views


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

	def test_track_eta_includes_waiting_jobs(self):
		with player_views._GENERATING_TRACKS_LOCK:
			original_timings = dict(player_views._GENERATION_TIMINGS)
			player_views._GENERATION_TIMINGS.clear()
			player_views._GENERATION_TIMINGS.update(
				{
					"alpha": {
						"started_at": 90.0,
						"estimated_total_seconds": 30.0,
						"audio_duration_seconds": 40.0,
					},
					"beta": {
						"started_at": 95.0,
						"estimated_total_seconds": 20.0,
						"audio_duration_seconds": 30.0,
					},
				}
			)

		try:
			with patch("player.views.monotonic", return_value=100.0):
				alpha_eta = player_views._get_track_eta_seconds("alpha")
				beta_eta = player_views._get_track_eta_seconds("beta")

			self.assertIsNotNone(alpha_eta)
			self.assertIsNotNone(beta_eta)
			self.assertGreater(beta_eta, alpha_eta)
			self.assertAlmostEqual(alpha_eta, 16.25, places=2)
			self.assertAlmostEqual(beta_eta, 30.0, places=2)
		finally:
			with player_views._GENERATING_TRACKS_LOCK:
				player_views._GENERATION_TIMINGS.clear()
				player_views._GENERATION_TIMINGS.update(original_timings)

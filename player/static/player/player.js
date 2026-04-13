(() => {
  const audio = document.getElementById("audio-player");
  const subtitleBox = document.getElementById("subtitle-box");
  const meta = document.getElementById("meta");
  const trackSelect = document.getElementById("track-select");

  if (!audio || !subtitleBox || !trackSelect) {
    return;
  }

  // Browser support varies, so apply restrictions at runtime too.
  audio.setAttribute("controlslist", "nodownload noremoteplayback");
  audio.setAttribute("disablepictureinpicture", "");
  audio.setAttribute("disableremoteplayback", "");
  audio.addEventListener("contextmenu", (event) => {
    event.preventDefault();
  });
  [subtitleBox, meta].forEach((element) => {
    if (!element) {
      return;
    }
    element.addEventListener("contextmenu", (event) => {
      event.preventDefault();
    });
  });

  const tracks = JSON.parse(document.getElementById("tracks-data")?.textContent || "[]");
  const currentTrackId = JSON.parse(document.getElementById("current-track")?.textContent || '""');

  let activeTrack = tracks.find((t) => t.slug === currentTrackId) || tracks[0];
  let segments = [];
  let activeIndex = -1;
  let isSubtitleLoading = false;
  let subtitleRequestId = 0;

  function setSubtitle(text, isActive) {
    subtitleBox.textContent = text || "...";
    subtitleBox.classList.toggle("active", Boolean(isActive));
  }

  function findSegmentIndex(currentTime) {
    for (let i = 0; i < segments.length; i += 1) {
      const segment = segments[i];
      if (currentTime >= segment.start && currentTime <= segment.end) {
        return i;
      }
    }
    return -1;
  }

  function syncSubtitle() {
    if (isSubtitleLoading) {
      return;
    }

    if (!segments.length) {
      setSubtitle("No subtitles available", false);
      return;
    }

    const index = findSegmentIndex(audio.currentTime);
    if (index === activeIndex) {
      return;
    }

    activeIndex = index;
    if (index === -1) {
      setSubtitle("", false);
      return;
    }

    const segment = segments[index];
    setSubtitle(segment.text, true);
  }

  function resetSubtitleState(message) {
    segments = [];
    activeIndex = -1;
    setSubtitle(message || "...", false);
    meta.textContent = "";
  }

  async function loadSubtitles(slug) {
    const requestId = ++subtitleRequestId;
    isSubtitleLoading = true;
    resetSubtitleState("Loading subtitles...");

    const response = await fetch(`/api/subtitles/?track=${encodeURIComponent(slug)}`);
    if (requestId !== subtitleRequestId) {
      return;
    }

    if (!response.ok) {
      setSubtitle("Could not load subtitles", false);
      meta.textContent = "";
      isSubtitleLoading = false;
      return;
    }

    const payload = await response.json();
    if (requestId !== subtitleRequestId) {
      return;
    }

    segments = payload.segments || [];
    activeIndex = -1;
    isSubtitleLoading = false;
    meta.textContent = `${payload.track.title} - ${segments.length} segments`;
    syncSubtitle();
  }

  async function switchTrack(slug) {
    const nextTrack = tracks.find((t) => t.slug === slug);
    if (!nextTrack) {
      return;
    }

    const wasPlaying = !audio.paused;
    resetSubtitleState("Loading subtitles...");
    audio.pause();
    activeTrack = nextTrack;
    audio.src = nextTrack.audio_url;
    audio.load();

    try {
      await loadSubtitles(nextTrack.slug);
      audio.currentTime = 0;
      syncSubtitle();
    } finally {
      if (wasPlaying) {
        try {
          await audio.play();
        } catch (error) {
          // Ignore autoplay rejections when the browser blocks playback.
        }
      }
    }
  }

  trackSelect.addEventListener("change", (event) => {
    const { value } = event.target;
    const url = new URL(window.location.href);
    url.searchParams.set("track", value);
    history.replaceState({}, "", url.toString());
    switchTrack(value);
  });

  ["timeupdate", "seeked", "play", "pause", "loadedmetadata"].forEach((eventName) => {
    audio.addEventListener(eventName, syncSubtitle);
  });

  loadSubtitles(activeTrack.slug);
})();

(() => {
  const audio = document.getElementById("audio-player");
  const subtitleBox = document.getElementById("subtitle-box");
  const meta = document.getElementById("meta");

  if (!audio || !subtitleBox) {
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
    subtitleBox.textContent = text ?? "";
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

  function findPreviousSegmentIndex(currentTime) {
    for (let i = segments.length - 1; i >= 0; i -= 1) {
      if (currentTime > segments[i].end) {
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

    if (index === -1) {
      const previousIndex = findPreviousSegmentIndex(audio.currentTime);
      activeIndex = -1;
      if (previousIndex !== -1) {
        // Preserve visual continuity during gaps by keeping active styling.
        setSubtitle(segments[previousIndex].text, true);
        return;
      }
      setSubtitle("", false);
      return;
    }

    activeIndex = index;
    const segment = segments[index];
    setSubtitle(segment.text, true);
  }

  function resetSubtitleState(message) {
    segments = [];
    activeIndex = -1;
    setSubtitle(message ?? "", false);
    meta.textContent = "";
  }

  async function loadSubtitles(slug) {
    const requestId = ++subtitleRequestId;
    isSubtitleLoading = true;
    resetSubtitleState("Loading subtitles...");
    try {
      const response = await fetch(`/podcasts/api/subtitles/?track=${encodeURIComponent(slug)}`);
      if (requestId !== subtitleRequestId) {
        return;
      }

      if (!response.ok) {
        if (response.status === 404) {
          setSubtitle("Subtitles not available yet", false);
        } else {
          setSubtitle("Could not load subtitles", false);
        }
        meta.textContent = "";
        return;
      }

      const payload = await response.json();
      if (requestId !== subtitleRequestId) {
        return;
      }

      segments = payload.segments || [];
      activeIndex = -1;
      meta.textContent = `${payload.track.title} - ${segments.length} segments`;
      // Unblock subtitle sync immediately after data is ready.
      isSubtitleLoading = false;
      syncSubtitle();
    } catch (error) {
      if (requestId !== subtitleRequestId) {
        return;
      }
      setSubtitle("Connection error while loading subtitles", false);
      meta.textContent = "";
    } finally {
      if (requestId === subtitleRequestId) {
        isSubtitleLoading = false;
      }
    }
  }

  // Initialize with current track
  if (activeTrack && activeTrack.slug) {
    loadSubtitles(activeTrack.slug);
  } else {
    resetSubtitleState("No track selected");
  }

  ["timeupdate", "seeked", "play", "pause", "loadedmetadata"].forEach((eventName) => {
    audio.addEventListener(eventName, syncSubtitle);
  });

})();

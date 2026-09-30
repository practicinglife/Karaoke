const token = window.KT_PLAYER?.token || "";
const activeSong = window.KT_PLAYER?.song ?? null;
const fullscreenBtn = document.getElementById("fullscreen-btn");
const playBtn = document.getElementById("play-btn");
const pauseBtn = document.getElementById("pause-btn");
const stopBtn = document.getElementById("stop-btn");
const audioPlayer = document.getElementById("audio-player");
const videoPlayer = document.getElementById("video-player");
const playerStatus = document.getElementById("player-status");
const canvas = document.getElementById("karaoke-canvas");
const context = canvas.getContext("2d");
const cdgPlayer = new window.CDGPlayer(canvas);
cdgPlayer.bindAudio(audioPlayer);

let suppressPauseStatus = false;
let trackNeedsReload = !!activeSong;

function setStatus(message) {
  playerStatus.textContent = message;
}

function isVideoSong(song) {
  return song?.media_kind === "video";
}

function updateMediaMode(song) {
  const useVideo = isVideoSong(song);
  canvas.hidden = useVideo;
  audioPlayer.hidden = useVideo;
  if (videoPlayer) {
    videoPlayer.hidden = !useVideo;
  }
}

function drawIdleScreen(title, artist, detail) {
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#000";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#f5f5f5";
  context.textAlign = "center";
  context.font = "bold 48px Arial, sans-serif";
  context.fillText(title || "Web Player", canvas.width / 2, canvas.height / 2 - 40);
  context.font = "28px Arial, sans-serif";
  context.fillText(artist || "Select a karaoke track", canvas.width / 2, canvas.height / 2 + 10);
  context.font = "22px Arial, sans-serif";
  context.fillStyle = "#7ec8ff";
  context.fillText(detail || "Ready for karaoke playback", canvas.width / 2, canvas.height / 2 + 60);
}

function getSongLabel(song) {
  return song?.display_name || song?.title || "";
}

function showReadySongState(song) {
  if (!song) {
    drawIdleScreen("Web Player", "Open a song from Admin.", "Waiting for track");
    setStatus("Open a song from Admin.");
    return;
  }
  if (!isVideoSong(song)) {
    drawIdleScreen(getSongLabel(song), song.artist || "", "Song loaded. Press Play to start.");
  }
  setStatus("Song loaded. Press Play to start.");
}

async function renderSelection(song) {
  if (!song) {
    cdgPlayer.stop();
    if (videoPlayer) {
      videoPlayer.pause();
      videoPlayer.removeAttribute("src");
      videoPlayer.load();
    }
    trackNeedsReload = true;
    showReadySongState(null);
    return;
  }

  updateMediaMode(song);

  if (isVideoSong(song)) {
    cdgPlayer.stop();
    audioPlayer.pause();
    audioPlayer.removeAttribute("src");
    audioPlayer.load();
    if (videoPlayer && song.video_url) {
      if (videoPlayer.src !== song.video_url) {
        videoPlayer.src = song.video_url;
      }
      videoPlayer.load();
    }
    trackNeedsReload = false;
    showReadySongState(song);
    return;
  }

  if (song.audio_url) {
    audioPlayer.preload = "auto";
    if (audioPlayer.src !== song.audio_url) {
      audioPlayer.src = song.audio_url;
    }
    audioPlayer.load();
  }
  drawIdleScreen(getSongLabel(song), song.artist || "", "Loading lyrics...");
  await cdgPlayer.load(song.cdg_url, getSongLabel(song), song.artist || "");
  trackNeedsReload = false;
  showReadySongState(song);
}

async function startPlayback() {
  if (!activeSong) {
    setStatus("Open a song from Admin.");
    return;
  }

  if (isVideoSong(activeSong)) {
    if (!activeSong.video_url) {
      setStatus("This video entry is missing its media file.");
      return;
    }
    if (trackNeedsReload || (videoPlayer && videoPlayer.src !== activeSong.video_url)) {
      await renderSelection(activeSong);
      if (videoPlayer) {
        videoPlayer.currentTime = 0;
      }
    }
    if (!videoPlayer) {
      setStatus("Video playback is unavailable in this browser view.");
      return;
    }
    try {
      await videoPlayer.play();
      setStatus(`Playing: ${activeSong.display_name || activeSong.title}`);
    } catch (_error) {
      setStatus("Unable to start playback in this browser.");
    }
    return;
  }

  if (!activeSong.audio_url) {
    setStatus("This entry has no audio file.");
    return;
  }
  if (trackNeedsReload || !cdgPlayer.loaded) {
    await renderSelection(activeSong);
    audioPlayer.currentTime = 0;
  }
  if (audioPlayer.src !== activeSong.audio_url) {
    audioPlayer.src = activeSong.audio_url;
  }
  try {
    await audioPlayer.play();
    setStatus(`Playing: ${activeSong.display_name || activeSong.title}`);
  } catch (_error) {
    setStatus("Unable to start playback in this browser.");
  }
}

function pausePlayback() {
  if (isVideoSong(activeSong)) {
    if (videoPlayer && !videoPlayer.paused) {
      videoPlayer.pause();
      setStatus("Playback paused.");
    }
    return;
  }

  if (!audioPlayer.paused) {
    audioPlayer.pause();
    setStatus("Playback paused.");
  }
}

function stopPlayback() {
  suppressPauseStatus = true;
  trackNeedsReload = false;

  if (isVideoSong(activeSong)) {
    if (videoPlayer) {
      videoPlayer.pause();
      videoPlayer.currentTime = 0;
    }
  } else {
    audioPlayer.pause();
    audioPlayer.currentTime = 0;
    cdgPlayer.stop();
  }

  showReadySongState(activeSong);
  window.setTimeout(() => {
    suppressPauseStatus = false;
  }, 0);
}

fullscreenBtn.addEventListener("click", async () => {
  const target = isVideoSong(activeSong)
    ? (videoPlayer || document.documentElement)
    : (canvas || document.documentElement);
  if (document.fullscreenElement) {
    await document.exitFullscreen();
    return;
  }
  if (target.requestFullscreen) {
    await target.requestFullscreen();
  }
});
audioPlayer.addEventListener("play", () => {
  if (activeSong && !isVideoSong(activeSong)) {
    cdgPlayer.startSync();
    setStatus(`Playing: ${activeSong.display_name || activeSong.title}`);
  }
});
audioPlayer.addEventListener("pause", () => {
  if (!suppressPauseStatus && !audioPlayer.ended && audioPlayer.currentTime > 0) {
    setStatus("Playback paused.");
  }
});
audioPlayer.addEventListener("ended", () => {
  cdgPlayer.stopSync();
  setStatus("Track finished.");
});
if (videoPlayer) {
  videoPlayer.addEventListener("ended", () => {
    setStatus("Track finished.");
  });
}
playBtn.addEventListener("click", () => void startPlayback());
pauseBtn.addEventListener("click", () => pausePlayback());
stopBtn.addEventListener("click", () => stopPlayback());

updateMediaMode(activeSong);
drawIdleScreen("Web Player", "Open a song from Admin.", activeSong ? "Loading lyrics..." : "Waiting for track");
if (activeSong) {
  renderSelection(activeSong).catch(() => setStatus("Unable to load the selected song."));
} else {
  trackNeedsReload = true;
  showReadySongState(null);
}

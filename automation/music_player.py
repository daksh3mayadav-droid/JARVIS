"""
automation/music_player.py — Streaming music player for JARVIS

Streams audio directly from YouTube via yt-dlp + mpv.
No files are downloaded to disk; playback runs in a background thread
so JARVIS remains fully responsive while music plays.
"""

from __future__ import annotations

import threading
from typing import Optional

from utils.logger import get_logger

log = get_logger("music_player")


class MusicPlayer:
    """
    Streams audio from YouTube using yt-dlp (URL extraction) and mpv (playback).

    Requirements:
        pip: yt-dlp, python-mpv
        system: mpv media player must be installed and on PATH
                  Windows: winget install mpv  OR  https://mpv.io/installation/

    All playback happens in a background thread — JARVIS stays responsive.
    Nothing is written to disk; audio is streamed directly.
    """

    def __init__(self) -> None:
        self._player = None          # mpv.MPV instance (created lazily)
        self._current_title: Optional[str] = None
        self._lock = threading.Lock()
        self._mpv_available = False
        self._ytdlp_available = False
        self._stream_thread: Optional[threading.Thread] = None  # current streaming thread
        self._init_player()

    # ─── Initialisation ──────────────────────────────────────────────────────

    def _init_player(self) -> None:
        """Try to initialise mpv and check yt-dlp availability."""
        try:
            import yt_dlp  # noqa: F401
            self._ytdlp_available = True
        except ImportError:
            log.warning(
                "yt-dlp not installed. Run: pip install yt-dlp"
            )

        try:
            import mpv
            # ytdl=False: we resolve the stream URL ourselves via yt-dlp and pass
            # it directly to mpv.play(), so we don't need mpv's built-in ytdl hook.
            self._player = mpv.MPV(video=False, ytdl=False)
            self._mpv_available = True
            log.info("MusicPlayer initialized (mpv + yt-dlp).")
        except ImportError:
            log.warning(
                "python-mpv not installed. Run: pip install python-mpv"
            )
        except Exception as exc:
            log.warning(
                "mpv could not be initialised (%s). "
                "Make sure mpv is installed on your system: "
                "winget install mpv  OR  https://mpv.io/installation/",
                exc,
            )

    def _ensure_available(self) -> Optional[str]:
        """Return an error string if mpv/yt-dlp are unavailable, else None."""
        if not self._ytdlp_available:
            return (
                "yt-dlp is not installed. Run: pip install yt-dlp"
            )
        if not self._mpv_available or self._player is None:
            return (
                "mpv is not available. Install it with: "
                "winget install mpv  OR  https://mpv.io/installation/  "
                "then add mpv.exe to your system PATH."
            )
        return None

    # ─── Search ──────────────────────────────────────────────────────────────

    def _search(self, query: str) -> tuple[Optional[str], str]:
        """
        Use yt-dlp to extract a direct audio stream URL for *query*.

        Returns:
            (stream_url, title) — url is None if nothing found.
        """
        import yt_dlp

        opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "default_search": "ytsearch1",
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(query, download=False)
                if info and "entries" in info:
                    info = info["entries"][0] if info["entries"] else None
                if not info:
                    return None, query
                return info.get("url"), info.get("title", query)
        except Exception as exc:
            log.error("yt-dlp search failed for '%s': %s", query, exc)
            return None, query

    # ─── Public API ──────────────────────────────────────────────────────────

    def play(self, query: str) -> str:
        """
        Search YouTube for *query* and stream the audio.

        The search and URL extraction run in a background thread so JARVIS
        is not blocked while yt-dlp fetches metadata.

        Args:
            query: Song name / artist / any search term.

        Returns:
            Immediate status message.
        """
        err = self._ensure_available()
        if err:
            return err

        def _stream():
            url, title = self._search(query)
            if not url:
                log.warning("Could not find audio stream for '%s'.", query)
                return
            with self._lock:
                self._current_title = title
            log.info("Streaming: %s", title)
            try:
                self._player.play(url)
            except Exception as exc:
                log.error("mpv playback error: %s", exc)

        self._stream_thread = threading.Thread(
            target=_stream, daemon=True, name="music-stream"
        )
        self._stream_thread.start()
        return f"Searching and streaming '{query}'…"

    def pause(self) -> str:
        """Pause playback."""
        err = self._ensure_available()
        if err:
            return err
        try:
            self._player.pause = True
            return "Music paused."
        except Exception as exc:
            log.error("Pause failed: %s", exc)
            return "Could not pause."

    def resume(self) -> str:
        """Resume paused playback."""
        err = self._ensure_available()
        if err:
            return err
        try:
            self._player.pause = False
            return "Resuming music."
        except Exception as exc:
            log.error("Resume failed: %s", exc)
            return "Could not resume."

    def stop(self) -> str:
        """Stop playback and clear the current title."""
        err = self._ensure_available()
        if err:
            return err
        try:
            self._player.stop()
            with self._lock:
                self._current_title = None
            return "Music stopped."
        except Exception as exc:
            log.error("Stop failed: %s", exc)
            return "Could not stop."

    def skip(self) -> str:
        """Stop current track (user can request the next song explicitly)."""
        return self.stop()

    def set_volume(self, level: int) -> str:
        """
        Set playback volume.

        Args:
            level: Integer 0–100.

        Returns:
            Status message.
        """
        err = self._ensure_available()
        if err:
            return err
        level = max(0, min(100, int(level)))
        try:
            self._player.volume = level
            return f"Music volume set to {level}%."
        except Exception as exc:
            log.error("set_volume failed: %s", exc)
            return "Could not set volume."

    @property
    def now_playing(self) -> Optional[str]:
        """Return the title of the currently playing track, or None."""
        with self._lock:
            return self._current_title

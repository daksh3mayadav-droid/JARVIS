"""
automation/youtube_control.py — Full YouTube navigation and control for JARVIS

Controls YouTube via keyboard shortcuts (when the video player is focused)
and URL navigation via BrowserControl.
"""

from __future__ import annotations

from utils.logger import get_logger

log = get_logger("automation.youtube")


class YouTubeController:
    """
    Full YouTube navigation and control via keyboard shortcuts and browser automation.

    YouTube keyboard shortcuts work when the video player is focused.
    URL-based navigation methods open/change the browser tab regardless of focus.
    """

    def __init__(self, controller, browser) -> None:
        """
        Initialize the YouTube controller.

        Args:
            controller: SystemController instance (for keyboard/mouse input).
            browser: BrowserControl instance (for URL navigation).
        """
        self.controller = controller
        self.browser = browser

    # ─── Playback Control ────────────────────────────────────────────────────

    def play_pause(self) -> str:
        """Toggle play/pause. YouTube shortcut: K"""
        self.controller.press_key("k")
        return "Toggled play/pause."

    def play(self) -> str:
        """Resume playback. Presses K to toggle; safe to call when paused."""
        self.controller.press_key("k")
        return "Resuming playback."

    def pause(self) -> str:
        """Pause playback. Presses K to toggle; safe to call when playing."""
        self.controller.press_key("k")
        return "Pausing playback."

    def stop(self) -> str:
        """Stop — equivalent to pause on YouTube."""
        self.controller.press_key("k")
        return "Stopped playback."

    def skip_forward(self, seconds: int = 5) -> str:
        """
        Skip forward by *seconds*.

        L = +10 s, Right arrow = +5 s.
        """
        if seconds >= 10:
            for _ in range(max(1, seconds // 10)):
                self.controller.press_key("l")
        else:
            self.controller.press_key("right")
        return f"Skipped forward ~{seconds}s."

    def skip_backward(self, seconds: int = 5) -> str:
        """
        Skip backward by *seconds*.

        J = −10 s, Left arrow = −5 s.
        """
        if seconds >= 10:
            for _ in range(max(1, seconds // 10)):
                self.controller.press_key("j")
        else:
            self.controller.press_key("left")
        return f"Skipped back ~{seconds}s."

    def next_video(self) -> str:
        """Play next video. Shift+N"""
        self.controller.hotkey("shift", "n")
        return "Playing next video."

    def previous_video(self) -> str:
        """Play previous video. Shift+P"""
        self.controller.hotkey("shift", "p")
        return "Playing previous video."

    def restart_video(self) -> str:
        """Go to the beginning of the video. Home key"""
        self.controller.press_key("home")
        return "Restarted video from the beginning."

    def go_to_end(self) -> str:
        """Jump to the end of the video. End key"""
        self.controller.press_key("end")
        return "Jumped to end of video."

    # ─── Volume Control ──────────────────────────────────────────────────────

    def volume_up(self) -> str:
        """Increase volume. Up arrow"""
        self.controller.press_key("up")
        return "Volume up."

    def volume_down(self) -> str:
        """Decrease volume. Down arrow"""
        self.controller.press_key("down")
        return "Volume down."

    def mute_unmute(self) -> str:
        """Toggle mute. M key"""
        self.controller.press_key("m")
        return "Toggled mute."

    # ─── Display Control ─────────────────────────────────────────────────────

    def fullscreen(self) -> str:
        """Toggle fullscreen. F key"""
        self.controller.press_key("f")
        return "Toggled fullscreen."

    def exit_fullscreen(self) -> str:
        """Exit fullscreen. Escape"""
        self.controller.press_key("escape")
        return "Exited fullscreen."

    def theater_mode(self) -> str:
        """Toggle theater mode. T key"""
        self.controller.press_key("t")
        return "Toggled theater mode."

    def miniplayer(self) -> str:
        """Toggle miniplayer / picture-in-picture. I key"""
        self.controller.press_key("i")
        return "Toggled miniplayer."

    # ─── Captions & Speed ────────────────────────────────────────────────────

    def toggle_captions(self) -> str:
        """Toggle captions/subtitles. C key"""
        self.controller.press_key("c")
        return "Toggled captions."

    def speed_up(self) -> str:
        """Increase playback speed. Shift+>"""
        self.controller.hotkey("shift", ".")
        return "Increased playback speed."

    def slow_down(self) -> str:
        """Decrease playback speed. Shift+<"""
        self.controller.hotkey("shift", ",")
        return "Decreased playback speed."

    def normal_speed(self) -> str:
        """Reset to normal speed — press Shift+< several times to reach 1×."""
        for _ in range(5):
            self.controller.hotkey("shift", ",")
        return "Reset playback speed to normal."

    # ─── Navigation ──────────────────────────────────────────────────────────

    def search(self, query: str) -> str:
        """Search YouTube for *query* by opening the results URL."""
        url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
        self.browser.open_url(url)
        return f"Searching YouTube for '{query}'."

    def open_youtube(self) -> str:
        """Open the YouTube homepage."""
        self.browser.open_url("https://www.youtube.com")
        return "Opening YouTube."

    def open_trending(self) -> str:
        """Open YouTube Trending."""
        self.browser.open_url("https://www.youtube.com/feed/trending")
        return "Opening YouTube Trending."

    def open_subscriptions(self) -> str:
        """Open YouTube Subscriptions feed."""
        self.browser.open_url("https://www.youtube.com/feed/subscriptions")
        return "Opening YouTube Subscriptions."

    def open_history(self) -> str:
        """Open YouTube watch history."""
        self.browser.open_url("https://www.youtube.com/feed/history")
        return "Opening YouTube History."

    def open_liked_videos(self) -> str:
        """Open Liked Videos playlist."""
        self.browser.open_url("https://www.youtube.com/playlist?list=LL")
        return "Opening Liked Videos."

    def open_watch_later(self) -> str:
        """Open Watch Later playlist."""
        self.browser.open_url("https://www.youtube.com/playlist?list=WL")
        return "Opening Watch Later."

    def open_shorts(self) -> str:
        """Open YouTube Shorts."""
        self.browser.open_url("https://www.youtube.com/shorts")
        return "Opening YouTube Shorts."

    def open_music(self) -> str:
        """Open YouTube Music."""
        self.browser.open_url("https://music.youtube.com")
        return "Opening YouTube Music."

    # ─── Video Interaction ───────────────────────────────────────────────────

    def go_to_timestamp(self, position: int = 5) -> str:
        """
        Jump to a percentage position in the video.

        YouTube maps keys 1–9 to 10 %–90 % of video length.

        Args:
            position: Percentage (1–90). Values 1–9 map directly; 10–90
                      are divided by 10 to find the nearest key.
        """
        if 1 <= position <= 9:
            self.controller.press_key(str(position))
            return f"Jumped to {position * 10}% of video."
        elif 10 <= position <= 90:
            key = str(position // 10)
            self.controller.press_key(key)
            return f"Jumped to ~{(position // 10) * 10}% of video."
        return "Position must be between 1 and 90."

    def frame_forward(self) -> str:
        """Advance one frame while paused. Period key"""
        self.controller.press_key(".")
        return "Advanced one frame."

    def frame_backward(self) -> str:
        """Go back one frame while paused. Comma key"""
        self.controller.press_key(",")
        return "Went back one frame."

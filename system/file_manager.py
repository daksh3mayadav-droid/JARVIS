"""
system/file_manager.py — Full filesystem operations for JARVIS

Browse, search, create, copy, move, rename, delete files and folders.
SQLite-backed file index for fast search. Watchdog folder monitoring.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Callable, Optional

try:
    import send2trash
    SEND2TRASH_AVAILABLE = True
except ImportError:
    SEND2TRASH_AVAILABLE = False

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

from core.memory import Memory
from utils.helpers import get_config, format_file_size, get_common_paths
from utils.logger import get_logger

log = get_logger("system.file_manager")

FILE_TYPE_MAP = {
    ".pdf": "document",
    ".doc": "document", ".docx": "document",
    ".xls": "spreadsheet", ".xlsx": "spreadsheet",
    ".ppt": "presentation", ".pptx": "presentation",
    ".txt": "text", ".md": "text", ".log": "text",
    ".jpg": "image", ".jpeg": "image", ".png": "image",
    ".gif": "image", ".bmp": "image", ".svg": "image",
    ".mp3": "audio", ".wav": "audio", ".flac": "audio", ".aac": "audio",
    ".mp4": "video", ".mkv": "video", ".avi": "video", ".mov": "video",
    ".py": "code", ".js": "code", ".ts": "code", ".java": "code",
    ".cpp": "code", ".c": "code", ".h": "code", ".cs": "code",
    ".zip": "archive", ".rar": "archive", ".7z": "archive", ".tar": "archive",
    ".exe": "executable", ".msi": "executable", ".bat": "executable",
}


class FileManager:
    """
    Full-featured filesystem manager for JARVIS.

    Supports browsing, searching, creating, moving, copying,
    renaming and (safely) deleting files. Uses SQLite-based
    indexing for fast search across the entire drive.
    """

    def __init__(self, memory: Optional[Memory] = None) -> None:
        """
        Initialize the file manager.

        Args:
            memory: Memory instance for file index (created if None).
        """
        self.memory = memory or Memory()
        self._common_paths = get_common_paths()
        self._observer: Optional[Observer] = None
        log.info("FileManager initialized.")

    # ─── Directory Listing ────────────────────────────────────────────────

    def list_dir(self, path: str | Path = ".") -> list[dict]:
        """
        List files and directories at *path*.

        Args:
            path: Directory path.

        Returns:
            List of dicts with: name, path, type, size, modified.
        """
        p = Path(path).expanduser().resolve()
        if not p.exists():
            log.warning("Directory not found: %s", p)
            return []

        entries = []
        try:
            for item in sorted(p.iterdir()):
                stat = item.stat()
                entries.append({
                    "name": item.name,
                    "path": str(item),
                    "type": "directory" if item.is_dir() else "file",
                    "extension": item.suffix.lower() if item.is_file() else "",
                    "category": FILE_TYPE_MAP.get(item.suffix.lower(), "other"),
                    "size": stat.st_size,
                    "size_human": format_file_size(stat.st_size),
                    "modified": stat.st_mtime,
                })
        except PermissionError as exc:
            log.warning("Permission denied: %s — %s", p, exc)
        return entries

    # ─── Search ───────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        root: Optional[str] = None,
        extension: Optional[str] = None,
        max_results: int = 50,
        use_index: bool = True,
    ) -> list[dict]:
        """
        Search for files matching *query*.

        Searches the in-memory SQLite index first, then falls back
        to a live filesystem walk if needed.

        Args:
            query: Name substring to search for.
            root: Root directory to search (home dir if None).
            extension: Optional extension filter (e.g. '.pdf').
            max_results: Maximum results to return.
            use_index: Whether to use the SQLite index.

        Returns:
            List of file dicts.
        """
        # Try index first
        if use_index:
            results = self.memory.search_files(query, extension, limit=max_results)
            if results:
                return results

        # Live filesystem walk
        search_root = Path(root) if root else Path.home()
        return self._walk_search(search_root, query, extension, max_results)

    def _walk_search(
        self,
        root: Path,
        query: str,
        extension: Optional[str],
        max_results: int,
    ) -> list[dict]:
        """Walk the filesystem looking for matching files."""
        results = []
        query_lower = query.lower()
        try:
            for dirpath, _dirnames, filenames in os.walk(root):
                for fname in filenames:
                    if query_lower in fname.lower():
                        fpath = Path(dirpath) / fname
                        if extension and fpath.suffix.lower() != extension:
                            continue
                        try:
                            stat = fpath.stat()
                            results.append({
                                "name": fname,
                                "path": str(fpath),
                                "extension": fpath.suffix.lower(),
                                "size": stat.st_size,
                                "size_human": format_file_size(stat.st_size),
                                "modified": stat.st_mtime,
                            })
                        except Exception:  # noqa: BLE001
                            pass
                    if len(results) >= max_results:
                        return results
        except PermissionError:
            pass
        return results

    # ─── File Operations ──────────────────────────────────────────────────

    def create_file(self, path: str | Path, content: str = "") -> bool:
        """
        Create a new file with optional content.

        Args:
            path: File path.
            content: Initial content.

        Returns:
            True on success.
        """
        p = Path(path).expanduser().resolve()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            log.info("Created file: %s", p)
            self._index_file(p)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Create file failed: %s", exc)
            return False

    def create_folder(self, path: str | Path) -> bool:
        """
        Create a folder (and parents).

        Args:
            path: Folder path.

        Returns:
            True on success.
        """
        p = Path(path).expanduser().resolve()
        try:
            p.mkdir(parents=True, exist_ok=True)
            log.info("Created folder: %s", p)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Create folder failed: %s", exc)
            return False

    def copy(self, src: str | Path, dst: str | Path) -> bool:
        """
        Copy a file or directory.

        Args:
            src: Source path.
            dst: Destination path.

        Returns:
            True on success.
        """
        s, d = Path(src).expanduser(), Path(dst).expanduser()
        try:
            if s.is_dir():
                shutil.copytree(str(s), str(d))
            else:
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(s), str(d))
            log.info("Copied %s → %s", s, d)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Copy failed: %s", exc)
            return False

    def move(self, src: str | Path, dst: str | Path) -> bool:
        """
        Move a file or directory.

        Args:
            src: Source path.
            dst: Destination path.

        Returns:
            True on success.
        """
        s, d = Path(src).expanduser(), Path(dst).expanduser()
        try:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(s), str(d))
            log.info("Moved %s → %s", s, d)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Move failed: %s", exc)
            return False

    def rename(self, path: str | Path, new_name: str) -> Optional[Path]:
        """
        Rename a file or directory.

        Args:
            path: Current path.
            new_name: New file name (not full path).

        Returns:
            New Path or None on failure.
        """
        p = Path(path).expanduser().resolve()
        new_path = p.parent / new_name
        try:
            p.rename(new_path)
            log.info("Renamed %s → %s", p.name, new_name)
            return new_path
        except Exception as exc:  # noqa: BLE001
            log.error("Rename failed: %s", exc)
            return None

    def delete(self, path: str | Path, use_recycle: bool = True) -> bool:
        """
        Delete a file or directory.

        Sends to Recycle Bin if *use_recycle* is True (and send2trash is
        available). Otherwise permanently deletes.

        Args:
            path: Path to delete.
            use_recycle: If True, prefer Recycle Bin.

        Returns:
            True on success.
        """
        p = Path(path).expanduser().resolve()
        if not p.exists():
            log.warning("Delete: path not found: %s", p)
            return False

        if use_recycle and SEND2TRASH_AVAILABLE:
            try:
                send2trash.send2trash(str(p))
                log.info("Sent to Recycle Bin: %s", p)
                return True
            except Exception as exc:  # noqa: BLE001
                log.warning("Recycle bin send failed: %s. Trying permanent delete.", exc)

        try:
            if p.is_dir():
                shutil.rmtree(str(p))
            else:
                p.unlink()
            log.info("Permanently deleted: %s", p)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Delete failed: %s", exc)
            return False

    def read_file(self, path: str | Path, max_chars: int = 10000) -> Optional[str]:
        """
        Read a text file.

        Args:
            path: File path.
            max_chars: Maximum characters to read.

        Returns:
            File content string or None.
        """
        p = Path(path).expanduser().resolve()
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            return content[:max_chars]
        except Exception as exc:  # noqa: BLE001
            log.error("Read failed: %s", exc)
            return None

    def disk_usage(self, path: str = "C:\\") -> dict:
        """
        Get disk usage for a drive/path.

        Args:
            path: Drive letter or path.

        Returns:
            Dict with total, used, free, percent_used.
        """
        try:
            usage = shutil.disk_usage(path)
            return {
                "path": path,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "total_human": format_file_size(usage.total),
                "used_human": format_file_size(usage.used),
                "free_human": format_file_size(usage.free),
                "percent_used": round(usage.used / usage.total * 100, 1),
            }
        except Exception as exc:  # noqa: BLE001
            log.error("Disk usage failed: %s", exc)
            return {}

    # ─── File Indexing ────────────────────────────────────────────────────

    def index_directory(
        self,
        root: str | Path = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> int:
        """
        Index all files under *root* into the SQLite file cache.

        Args:
            root: Root directory (home dir if None).
            progress_callback: Optional callback called with indexed count.

        Returns:
            Number of files indexed.
        """
        root_path = Path(root).expanduser() if root else Path.home()
        count = 0
        skip_dirs = {".git", "__pycache__", "node_modules", "venv", ".venv"}

        for dirpath, dirnames, filenames in os.walk(root_path):
            # Skip common noise directories
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]

            for fname in filenames:
                fpath = Path(dirpath) / fname
                try:
                    self._index_file(fpath)
                    count += 1
                    if progress_callback and count % 100 == 0:
                        progress_callback(count)
                except Exception:  # noqa: BLE001
                    pass

        log.info("Indexed %d files under %s", count, root_path)
        return count

    def _index_file(self, path: Path) -> None:
        """Add a single file to the SQLite index."""
        try:
            stat = path.stat()
            self.memory.index_file(
                path=str(path),
                name=path.name,
                extension=path.suffix.lower(),
                size_bytes=stat.st_size,
                modified_at=stat.st_mtime,
            )
        except Exception:  # noqa: BLE001
            pass

    # ─── Folder Watcher ───────────────────────────────────────────────────

    def watch_folder(
        self,
        path: str | Path,
        callback: Callable[[str, str], None],
    ) -> bool:
        """
        Watch a folder for changes and call *callback* on events.

        Args:
            path: Folder to watch.
            callback: Called with (event_type, file_path).
                      event_type: 'created', 'modified', 'deleted', 'moved'.

        Returns:
            True if watcher started, False if watchdog unavailable.
        """
        if not WATCHDOG_AVAILABLE:
            log.warning("watchdog not available. Folder watching disabled.")
            return False

        class _Handler(FileSystemEventHandler):
            def on_created(self, event: FileSystemEvent):
                callback("created", event.src_path)

            def on_modified(self, event: FileSystemEvent):
                callback("modified", event.src_path)

            def on_deleted(self, event: FileSystemEvent):
                callback("deleted", event.src_path)

            def on_moved(self, event: FileSystemEvent):
                callback("moved", event.dest_path)

        if self._observer:
            self._observer.stop()

        self._observer = Observer()
        self._observer.schedule(_Handler(), str(path), recursive=True)
        self._observer.start()
        log.info("Watching folder: %s", path)
        return True

    def stop_watching(self) -> None:
        """Stop the folder watcher."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None

    # ─── Common Paths ─────────────────────────────────────────────────────

    def get_path(self, name: str) -> Optional[Path]:
        """
        Return a common path by name.

        Args:
            name: One of: desktop, downloads, documents, music, pictures,
                  videos, appdata, temp, etc.

        Returns:
            Path or None if unknown name.
        """
        return self._common_paths.get(name.lower())

    def categorize_file(self, path: str | Path) -> str:
        """
        Return the category for a file based on its extension.

        Returns:
            Category string (e.g. 'document', 'image', 'code', 'other').
        """
        ext = Path(path).suffix.lower()
        return FILE_TYPE_MAP.get(ext, "other")

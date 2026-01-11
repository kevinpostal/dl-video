"""Thumbnail caching for video metadata."""

import hashlib
from pathlib import Path

from PIL import Image


class ThumbnailCache:
    """Caches downloaded thumbnails locally."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        """Initialize the thumbnail cache.
        
        Args:
            cache_dir: Directory for cached thumbnails. 
                      Defaults to ~/.config/dl-video/thumbnails
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".config" / "dl-video" / "thumbnails"
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _url_to_filename(self, url: str) -> str:
        """Convert URL to a cache filename."""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return f"{url_hash}.png"

    def get_path(self, url: str) -> Path:
        """Get the cache path for a URL."""
        return self._cache_dir / self._url_to_filename(url)

    def has(self, url: str) -> bool:
        """Check if a thumbnail is cached."""
        return self.get_path(url).exists()

    def get(self, url: str) -> Image.Image | None:
        """Get a cached thumbnail image.
        
        Returns:
            PIL Image if cached, None otherwise.
        """
        cache_path = self.get_path(url)
        if not cache_path.exists():
            return None
        try:
            return Image.open(cache_path)
        except Exception:
            # Corrupted cache file, remove it
            cache_path.unlink(missing_ok=True)
            return None

    def save(self, url: str, image: Image.Image) -> Path:
        """Save a thumbnail to cache.
        
        Args:
            url: Original thumbnail URL
            image: PIL Image to cache
            
        Returns:
            Path to cached file
        """
        cache_path = self.get_path(url)
        # Save as PNG for lossless quality
        image.save(cache_path, "PNG")
        return cache_path

    def clear(self) -> int:
        """Clear all cached thumbnails.
        
        Returns:
            Number of files removed.
        """
        count = 0
        for f in self._cache_dir.glob("*.png"):
            f.unlink()
            count += 1
        return count

    @property
    def size(self) -> int:
        """Get total cache size in bytes."""
        return sum(f.stat().st_size for f in self._cache_dir.glob("*.png"))

    @property
    def count(self) -> int:
        """Get number of cached thumbnails."""
        return len(list(self._cache_dir.glob("*.png")))

"""Thumbnail caching for video metadata."""

import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image


def get_best_thumbnail_url(url: str) -> str:
    """Try to get highest quality thumbnail URL.
    
    YouTube thumbnails come in various sizes:
    - default.jpg (120x90)
    - mqdefault.jpg (320x180)
    - hqdefault.jpg (480x360)
    - sddefault.jpg (640x480)
    - maxresdefault.jpg (1280x720)
    """
    if "ytimg.com" in url or "youtube.com" in url:
        for quality in ["default", "mqdefault", "hqdefault", "sddefault"]:
            if quality in url:
                return url.replace(quality, "maxresdefault")
    return url


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
            image = Image.open(cache_path)
            image.load()  # Force load image data into memory
            return image
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

    def process_and_save(self, url: str, data: bytes) -> Image.Image:
        """Process image data and save to cache.
        
        Converts to RGB and scales to fit container width.
        
        Args:
            url: Thumbnail URL (for cache key)
            data: Raw image bytes
            
        Returns:
            Processed PIL Image
        """
        image = Image.open(BytesIO(data))
        
        # Convert to RGB if needed
        if image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        
        # Scale to fit container width (approx 85 chars * 2 pixels = 170px effective)
        # But for Kitty protocol, we want actual pixels - target ~680px width
        target_width = 680
        if image.width != target_width:
            scale = target_width / image.width
            new_width = target_width
            new_height = int(image.height * scale)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        self.save(url, image)
        return image

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

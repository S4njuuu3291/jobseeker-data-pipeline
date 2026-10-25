def normalize_url(url: str) -> str:
    """Buang parameter tracking dari URL job agar hash konsisten."""
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))

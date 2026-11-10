ASSET_SUFFIXES = (
    ".js", ".mjs", ".css", ".map", ".json", ".txt", ".html", ".xml",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".avif",
    ".mp4", ".webm", ".m4a", ".mp3", ".ogg",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".wasm", ".webmanifest",
)

LOGIN_PATH = "/login"
PUBLIC_PATHS = frozenset({LOGIN_PATH})


def is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


def is_asset_path(path: str) -> bool:
    return path.lower().endswith(ASSET_SUFFIXES)

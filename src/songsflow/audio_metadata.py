"""Bounded metadata-only validation worker. No transcription, tags, images or disk files."""

import io
import json
import sys

from tinytag import TinyTag


def main():
    try:
        data = sys.stdin.buffer.read(20 * 1024 * 1024 + 1)
        if not data or len(data) > 20 * 1024 * 1024:
            raise ValueError("Invalid size")
        parsed = TinyTag.get(file_obj=io.BytesIO(data), tags=False, image=False)
        media = (parsed.mime_type or "").split(";", 1)[0]
        if media not in ("audio/mpeg", "audio/mp4", "audio/wav") or not parsed.duration:
            raise ValueError("Invalid format")
        print(json.dumps({"media": media, "duration": parsed.duration}))
    except Exception:
        # Do not include parser errors or submitted data in logs.
        sys.exit(2)


if __name__ == "__main__":
    main()

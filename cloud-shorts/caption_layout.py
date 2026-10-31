"""Measured, fail-closed caption layout for 720-pixel portrait Shorts.

FFmpeg centers drawtext using text_w, which becomes NEGATIVE x when a long
Russian title is wider than the frame. Measure using the same DejaVu font,
fit into a 615-pixel safe zone, and never silently trim the user's title.
"""
import re
from pathlib import Path

FONT_PATH = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
SAFE_WIDTH = 615


def readable_caption_text(value):
    """Hide unsupported emoji codepoints in drawn titles, not public metadata."""
    def is_emoji(code):
        return (0x1F000 <= code <= 0x1FAFF or 0x2600 <= code <= 0x27BF
                or code in (0xFE0E, 0xFE0F, 0x200D, 0x20E3))
    safe = ''.join(ch for ch in str(value) if not is_emoji(ord(ch)))
    return re.sub(r'\\s+', ' ', safe).strip()


def layout_caption(value, font_path=FONT_PATH):
    from PIL import ImageFont
    words = readable_caption_text(value).split(' ')
    if not words or not any(words):
        raise ValueError('CAPTION_EMPTY')
    title = ' '.join(words)

    def result(lines, size):
        font = ImageFont.truetype(str(font_path), size)
        widths = [float(font.getlength(line)) for line in lines]
        if max(widths) > SAFE_WIDTH:
            return None
        return {'text': '\n'.join(lines), 'font_size': size,
                'line_count': len(lines), 'max_line_width_px': round(max(widths), 1),
                'safe_width_px': SAFE_WIDTH,
                'box_y': 123 if len(lines) == 2 else 126,
                'box_height': 110 if len(lines) == 2 else 92,
                'text_y': 137 if len(lines) == 2 else 154}

    for size in (36, 34, 32, 30):
        candidate = result([title], size)
        if candidate:
            return candidate
    if len(words) >= 2:
        for size in (36, 34, 32, 30, 28, 26):
            candidates = []
            for index in range(1, len(words)):
                one = ' '.join(words[:index])
                two = ' '.join(words[index:])
                candidate = result([one, two], size)
                if candidate:
                    f = ImageFont.truetype(str(font_path), size)
                    balance = abs(float(f.getlength(one)) - float(f.getlength(two)))
                    candidates.append((balance, candidate))
            if candidates:
                return min(candidates, key=lambda x: x[0])[1]
    for size in (28, 26, 24, 22, 20):
        candidate = result([title], size)
        if candidate:
            return candidate
    raise ValueError('CAPTION_OVERFLOW: title cannot fit in one or two lines')

"""Generate align_terminals.ico from geometry, using only the standard library.

The icon shows four cascaded terminal windows: each one keeps a readable
left-edge band and the rightmost sits in front, which is what the tool does to
the real Windows Terminal windows.

Every ICO size is drawn natively at integer pixel coordinates so that 1px
details stay crisp instead of being smeared by downsampling. Sizes below 32px
drop the text lines, which at that scale collapse into indistinguishable noise.

Usage:
    py -3 tools/make_icon.py [--out PATH] [--png-dir DIR]

--png-dir also writes one PNG per size, which is only useful for inspecting the
artwork; the shortcut consumes the .ico alone.
"""

import argparse
import struct
import zlib
from pathlib import Path

SIZES = (16, 24, 32, 48, 64, 128, 256)

# Palette: dark terminal. The background tile is light enough to stay visible
# against a dark taskbar, the window bodies dark enough to read as terminals.
BG = (0x18, 0x26, 0x34, 0xFF)
WIN_OUTLINE = (0x05, 0x09, 0x0D, 0xFF)
WIN_TITLE = (0x4E, 0xA8, 0xDE, 0xFF)
WIN_BODY = (0x0B, 0x10, 0x17, 0xFF)
TEXT_BRIGHT = (0xD3, 0xE1, 0xEC, 0xFF)
TEXT_DIM = (0x93, 0xA9, 0xBC, 0xFF)

WINDOW_COUNT = 4

# Geometry as fractions of the content box, which is the canvas minus the outer
# margin. Three steps plus one window width span the box exactly, so a step is
# the visible band of the window behind it.
WIN_W = 0.512
WIN_H = 0.612
STEP_X = (1.0 - WIN_W) / (WINDOW_COUNT - 1)
STEP_Y = (1.0 - WIN_H) / (WINDOW_COUNT - 1)
MARGIN = 0.05
CORNER_RADIUS = 0.18
LINE_WIDTHS = (0.86, 0.55, 0.72, 0.44)


class Canvas:
    """RGBA pixel buffer with opaque axis-aligned rectangle fills."""

    def __init__(self, size):
        self.size = size
        self.px = bytearray(size * size * 4)

    def fill(self, x0, y0, x1, y1, color):
        s = self.size
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(s, x1), min(s, y1)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(color) * (x1 - x0)
        for y in range(y0, y1):
            off = (y * s + x0) * 4
            self.px[off:off + len(row)] = row

    def apply_alpha_mask(self, mask):
        for i, coverage in enumerate(mask):
            if coverage != 255:
                self.px[i * 4 + 3] = self.px[i * 4 + 3] * coverage // 255


def _inside_rounded(px, py, size, radius):
    cx = min(max(px, radius), size - radius)
    cy = min(max(py, radius), size - radius)
    dx, dy = px - cx, py - cy
    return dx * dx + dy * dy <= radius * radius


def rounded_rect_mask(size, radius, samples=4):
    """Antialiased coverage mask, sampled only where the corners can cut in."""
    mask = bytearray(size * size)
    step = 1.0 / samples
    base = step / 2.0
    total = samples * samples
    for y in range(size):
        for x in range(size):
            if radius <= x <= size - radius - 1 or radius <= y <= size - radius - 1:
                mask[y * size + x] = 255
                continue
            hits = 0
            for sy in range(samples):
                py = y + base + sy * step
                for sx in range(samples):
                    if _inside_rounded(x + base + sx * step, py, size, radius):
                        hits += 1
            mask[y * size + x] = round(255 * hits / total)
    return mask


def draw_text_lines(canvas, x0, y0, x1, y1, size):
    """Suggest a few lines of terminal output inside one window body."""
    margin = max(1, round(size * 0.022))
    thickness = max(1, round(size * 0.018))
    gap = max(1, round(size * 0.030))
    count = 3 if size < 64 else 4
    inner_w = x1 - x0 - 2 * margin
    y = y0 + gap
    for index in range(count):
        if y + thickness > y1 - margin:
            break
        width = max(1, round(inner_w * LINE_WIDTHS[index % len(LINE_WIDTHS)]))
        color = TEXT_BRIGHT if index == 0 else TEXT_DIM
        canvas.fill(x0 + margin, y, x0 + margin + width, y + thickness, color)
        y += thickness + gap


def draw(size):
    canvas = Canvas(size)
    canvas.fill(0, 0, size, size, BG)

    border = max(1, round(size / 64))
    # The outlines grow outward, so the content box has to leave room for them
    # or the corner mask clips the first and last window.
    origin = border + max(1, round(size * MARGIN))
    span = size - 2 * origin

    # One integer step for the whole cascade. Rounding each window position on
    # its own gives uneven steps, and at 16px the short step swallows a title
    # bar whole. The window size is what absorbs the rounding instead.
    step_x = max(2, round(STEP_X * span))
    step_y = max(2, round(STEP_Y * span))
    win_w = span - (WINDOW_COUNT - 1) * step_x
    win_h = span - (WINDOW_COUNT - 1) * step_y
    title_h = max(1, round(win_h * 0.17))

    # Back to front order matters: each window's outline overwrites the body of
    # the one behind it, which is what keeps the overlap readable.
    for i in range(WINDOW_COUNT):
        x0, y0 = origin + i * step_x, origin + i * step_y
        x1, y1 = x0 + win_w, y0 + win_h
        canvas.fill(x0 - border, y0 - border, x1 + border, y1 + border, WIN_OUTLINE)
        canvas.fill(x0, y0, x1, y0 + title_h, WIN_TITLE)
        canvas.fill(x0, y0 + title_h, x1, y1, WIN_BODY)
        if size >= 32:
            draw_text_lines(canvas, x0, y0 + title_h, x1, y1, size)

    canvas.apply_alpha_mask(rounded_rect_mask(size, size * CORNER_RADIUS))
    return canvas


def png_bytes(canvas):
    stride = canvas.size * 4
    raw = bytearray()
    for y in range(canvas.size):
        raw.append(0)  # filter type 0 (None)
        raw += canvas.px[y * stride:(y + 1) * stride]

    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", canvas.size, canvas.size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def bmp_bytes(canvas):
    """Encode a canvas as an ICO-flavoured DIB.

    Two details are easy to get wrong and render as garbage: biHeight is twice
    the real height because the AND mask counts as a second bitmap, and that
    1bpp mask has to be present with rows padded to 4 bytes even though a 32bpp
    image carries its own alpha.
    """
    size = canvas.size
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)

    xor = bytearray()
    for y in range(size - 1, -1, -1):  # DIB rows run bottom-up
        row = canvas.px[y * size * 4:(y + 1) * size * 4]
        for x in range(size):
            r, g, b, a = row[x * 4:x * 4 + 4]
            xor += bytes((b, g, r, a))

    mask_stride = ((size + 31) // 32) * 4
    and_mask = bytearray()
    for y in range(size - 1, -1, -1):
        row = bytearray(mask_stride)
        for x in range(size):
            if canvas.px[(y * size + x) * 4 + 3] < 128:
                row[x // 8] |= 0x80 >> (x % 8)  # set bit means transparent
        and_mask += row

    return header + bytes(xor) + bytes(and_mask)


def ico_bytes(images):
    """Pack (size, encoded bytes) pairs into an ICO. 256 is encoded as 0."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = b""
    for size, data in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return header + entries + b"".join(data for _, data in images)


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=root / "align_terminals.ico")
    parser.add_argument("--png-dir", type=Path, default=None,
                        help="also dump one PNG per size, for inspection")
    args = parser.parse_args()

    images = []
    for size in SIZES:
        canvas = draw(size)
        # PNG frames keep the 256px entry small, but GDI+ refuses to decode them
        # at the sizes Explorer and the taskbar actually ask for, so everything
        # below 256 goes in as an uncompressed DIB.
        images.append((size, png_bytes(canvas) if size >= 256 else bmp_bytes(canvas)))
        if args.png_dir:
            args.png_dir.mkdir(parents=True, exist_ok=True)
            (args.png_dir / f"icon_{size}.png").write_bytes(png_bytes(canvas))

    args.out.write_bytes(ico_bytes(images))
    print(f"wrote {args.out} ({args.out.stat().st_size} bytes, "
          f"{len(images)} sizes: {', '.join(str(s) for s, _ in images)})")


if __name__ == "__main__":
    main()

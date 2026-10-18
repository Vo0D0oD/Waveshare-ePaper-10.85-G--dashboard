"""
Adapter for the Waveshare 10.85" e-Paper HAT+ (G): 1360x480, four colours
(black / white / yellow / red), 2 bits per pixel, no partial refresh.

The dashboard draws into a normal PIL RGB image; this module snaps it to the
four panel colours and hands it to Waveshare's own `epd10in85g` driver, so the
panel init sequence always comes from the vendor, never from this project.

Required file (NOT shipped with this repo): lib/waveshare_epd/epd10in85g.py
Copy it from the Waveshare demo package that already works on your Pi.
"""
import logging
import os
import time

from PIL import Image

logger = logging.getLogger(__name__)

# Panel colours. The order matters: palette index == the panel's 2-bit code
# (black 00, white 01, yellow 10, red 11).
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
YELLOW = (255, 255, 0)
RED = (255, 0, 0)
PALETTE = (BLACK, WHITE, YELLOW, RED)

_DITHER_NONE = getattr(getattr(Image, "Dither", Image), "NONE")


def _palette_image():
    pal = Image.new("P", (1, 1))
    flat = [c for rgb in PALETTE for c in rgb]
    pal.putpalette(flat + [0] * (768 - len(flat)))
    return pal


def quantize(image):
    """Return a 'P' image whose pixel values are the panel codes 0..3."""
    return image.convert("RGB").quantize(palette=_palette_image(), dither=_DITHER_NONE)


def snap_to_palette(image):
    """RGB image in which every pixel is exactly one of the four panel colours."""
    return quantize(image).convert("RGB")


def pack_fast(image):
    """
    Pack an image into the panel's 2-bit format (4 pixels per byte, first
    pixel in the high bits) using numpy. Returns bytearray, or None if numpy
    is unavailable. Orders of magnitude faster than a per-pixel Python loop,
    which is far too slow on a Pi Zero 1.
    """
    try:
        import numpy as np
    except ImportError:
        return None
    idx = np.asarray(quantize(image), dtype=np.uint8)
    h, w = idx.shape
    if w % 4:
        raise ValueError("width must be a multiple of 4")
    q = idx.reshape(h, w // 4, 4)
    packed = (q[..., 0] << 6) | (q[..., 1] << 4) | (q[..., 2] << 2) | q[..., 3]
    return bytearray(packed.astype(np.uint8).tobytes())


def test_pattern(width, height):
    """Image that exercises every colour, every pixel phase and both halves."""
    img = Image.new("RGB", (width, height), WHITE)
    px = img.load()
    for y in range(height):
        for x in range(width):
            px[x, y] = PALETTE[((x // 3) + (y // 5) + (x // 340)) % 4]
    return img


class ColorEPD:
    """Drop-in for the old monochrome `epd10in85.EPD` as used by main.py."""

    def __init__(self):
        try:
            from waveshare_epd import epd10in85g
        except ImportError as e:
            raise RuntimeError(
                "Cannot import waveshare_epd.epd10in85g (%s). Copy epd10in85g.py "
                "from the Waveshare 10.85inch e-Paper HAT+ (G) demo package into "
                "lib/waveshare_epd/." % e
            )
        self._drv = epd10in85g
        self._epd = epd10in85g.EPD()
        if not hasattr(self._epd, "init") and hasattr(self._epd, "Init"):
            self._epd.init = self._epd.Init  # this vendor driver spells it Init
        self.width = getattr(self._epd, "width", 680) * 2  # driver reports one half (680); the panel is 1360 wide
        self.height = getattr(self._epd, "height", 480)
        self._fast = None  # decided by verify_fast_path()

    # ---- packing ---------------------------------------------------------
    def verify_fast_path(self):
        """
        Compare the fast packer with the vendor's getbuffer() once. The fast
        path is only used if the bytes are identical; otherwise every frame
        goes through the vendor routine. Slow once on a Pi Zero 1, then free.
        """
        if os.environ.get("EPD_FORCE_VENDOR_PACK"):
            self._fast = False
            return False
        try:
            img = test_pattern(self.width, self.height)
            t0 = time.time()
            fast = pack_fast(img)
            t_fast = time.time() - t0
            if fast is None:
                logger.warning("numpy not available; using the vendor getbuffer (slow)")
                self._fast = False
                return False
            t0 = time.time()
            vendor = self._epd.getbuffer(img)
            t_vendor = time.time() - t0
            self._fast = bytes(fast) == bytes(vendor)
            logger.info("Fast 2-bit packer %s vendor getbuffer (fast %.2fs, vendor %.2fs)",
                        "MATCHES" if self._fast else "DIFFERS FROM", t_fast, t_vendor)
        except Exception as e:
            logger.warning("Fast-path check failed (%s); using vendor getbuffer", e)
            self._fast = False
        return self._fast

    def getbuffer(self, image):
        if image.size != (self.width, self.height):
            frame = Image.new("RGB", (self.width, self.height), WHITE)
            frame.paste(image, (0, 0))
            image = frame
        image = snap_to_palette(image)
        if self._fast is None:
            self.verify_fast_path()
        if self._fast:
            return pack_fast(image)
        return self._epd.getbuffer(image)

    # ---- hardware --------------------------------------------------------
    def init(self):
        return self._epd.init()

    def Clear(self):
        return self._epd.Clear()

    def display(self, buf):
        return self._epd.display(buf)

    def sleep(self):
        return self._epd.sleep()

    def refresh(self, buf):
        """One complete, safe update: reset+init, send frame (~21 s), deep sleep."""
        self._epd.init()
        self._epd.display(buf)
        self._epd.sleep()

    def module_exit(self):
        cfg = self._drv.epdconfig
        try:
            cfg.module_exit(cleanup=True)
        except TypeError:  # newer Waveshare epdconfig takes no argument
            cfg.module_exit()

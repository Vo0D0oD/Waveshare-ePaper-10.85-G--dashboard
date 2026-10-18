#!/usr/bin/python3
"""
Smoke test for the 10.85" e-Paper HAT+ (G) using this project's lib/.

  python3 test_color_panel.py --no-display   # only check the 2-bit packer, panel untouched
  python3 test_color_panel.py                # packer check + one real ~21 s refresh

Run this BEFORE main.py. It draws colour bars, a left/right seam marker (the
panel has two driver ICs, one per half) and a text sample.
"""
import logging
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, "lib"))

from PIL import Image, ImageDraw, ImageFont

import epd_color
from epd_color import BLACK, WHITE, YELLOW, RED

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def build_image(w, h):
    img = Image.new("RGB", (w, h), WHITE)
    d = ImageDraw.Draw(img)
    bar_w = w // 4
    for i, c in enumerate((BLACK, WHITE, YELLOW, RED)):
        d.rectangle((i * bar_w, 0, (i + 1) * bar_w - 1, h // 3), fill=c, outline=BLACK)
    d.line((w // 2, 0, w // 2, h), fill=BLACK, width=3)          # seam between the two ICs
    d.rectangle((w // 2 - 40, h // 2, w // 2 + 40, h // 2 + 40), fill=RED)  # must be unbroken
    try:
        font = ImageFont.truetype(os.path.join(BASE_DIR, "fnt", "Aldrich-Regular.ttc"), 40)
    except Exception:
        font = ImageFont.load_default()
    d.text((20, h // 3 + 20), "10.85\" (G) test  black / white / yellow / red", font=font, fill=BLACK)
    d.text((20, h // 3 + 80), "Yellow text", font=font, fill=YELLOW)
    d.text((300, h // 3 + 80), "Red text", font=font, fill=RED)
    d.text((20, h - 70), "Seam marker is the red square: it must not be offset or split",
           font=font, fill=BLACK)
    return img


def main():
    display = "--no-display" not in sys.argv
    epd = epd_color.ColorEPD()
    print("panel size: %dx%d" % (epd.width, epd.height))
    ok = epd.verify_fast_path()
    print("fast packer matches vendor getbuffer:", ok)
    img = build_image(epd.width, epd.height)
    img.save(os.path.join(BASE_DIR, "test_color_panel_preview.png"))
    if not display:
        return
    t0 = time.time()
    buf = epd.getbuffer(img)
    print("packed in %.2fs" % (time.time() - t0))
    t0 = time.time()
    epd.refresh(buf)
    print("refresh took %.1fs" % (time.time() - t0))
    epd.module_exit()


if __name__ == "__main__":
    main()

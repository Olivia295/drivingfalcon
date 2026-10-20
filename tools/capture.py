#!/usr/bin/env python3
"""Render real drivingfalcon frames to PNG screenshots and a demo GIF for the README.

Runs the game headless (no terminal needed), drives it with a scripted scenario,
and paints each frame cell-by-cell with Pillow. Requires: Pillow, ffmpeg (for the GIF).

    python3 tools/capture.py            # writes docs/assets/*.png and docs/assets/demo.gif
"""
import os
import pty
import random
import shutil
import subprocess
import sys
import tempfile
import types

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "assets")
sys.path.insert(0, ROOT)
FONT_PATH = "/System/Library/Fonts/Menlo.ttc"
CW, CH = 8, 16                      # cell size in pixels


def make_game(cols, rows, seed, zen=False):
    os.environ["COLUMNS"], os.environ["LINES"] = str(cols), str(rows)
    random.seed(seed)
    import drivingfalcon as df
    master, _ = pty.openpty()
    g = df.Game(master, types.SimpleNamespace(zen=zen, no_cockpit=False, stats=False))
    return df, g


class Painter:
    def __init__(self):
        self.font = ImageFont.truetype(FONT_PATH, 13)
        self.cache = {}

    def glyph(self, ch, fg):
        key = (ch, fg)
        if key not in self.cache:
            im = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((0, 1), ch, font=self.font, fill=fg)
            self.cache[key] = im
        return self.cache[key]

    def paint(self, cv, fg_default):
        im = Image.new("RGB", (cv.w * CW, cv.h * CH))
        d = ImageDraw.Draw(im)
        for y in range(cv.h):
            for x in range(cv.w):
                bg, ch, fg = cv.bg[y][x], cv.ch[y][x], cv.fg[y][x] or fg_default
                x0, y0 = x * CW, y * CH
                d.rectangle([x0, y0, x0 + CW - 1, y0 + CH - 1], fill=bg)
                if ch == "▀":
                    d.rectangle([x0, y0, x0 + CW - 1, y0 + CH // 2 - 1], fill=fg)
                elif ch == "▄":
                    d.rectangle([x0, y0 + CH // 2, x0 + CW - 1, y0 + CH - 1], fill=fg)
                elif ch != " ":
                    im.paste(self.glyph(ch, fg), (x0, y0), self.glyph(ch, fg))
        return im


def step(g, sec, every=None, sink=None):
    n = int(round(sec * 30))
    for i in range(n):
        g.update(1 / 30)
        cv = g.draw()
        if sink is not None and i % every == 0:
            sink(cv)


def aim_at(g, c):
    x0, y0, x1, y1 = c.bbox
    g.aim_x, g.aim_y, g.mouse_t = (x0 + x1) // 2, (y0 + y1) // 2, g.t


def screenshot(name, cols, rows, seed, system, setup):
    df, g = make_game(cols, rows, seed)
    g.close_help()
    g.enter_system(system)
    g.sys_t = 18.0
    setup(df, g)
    Painter().paint(g.draw(), df.FG).save(os.path.join(OUT, name), optimize=True)
    print("wrote", name)


def shots():
    def cruise(df, g):
        step(g, 6)
    def traffic(df, g):
        step(g, 9)
        c = g.nearest_craft()
        if c:
            aim_at(g, c)
            g.hail(c)
        step(g, 1.2)
        if c and c.bbox:
            aim_at(g, c)
    def hyper(df, g):
        g.punch_it()
        step(g, 3.6)
    def zen(df, g):
        g.zen = g.autopilot = True
        step(g, 4)
        g.boost = 6.0
        step(g, 2.5)
    def log(df, g):
        for k in ("tie", "xwing", "stard", "transport", "purrgil", "cloudcar", "corvette"):
            g.log["ships"][k] = random.randint(1, 9)
        for n in ("TATOOINE", "HOTH", "LOTHAL"):
            g.log["systems"][n] = random.randint(1, 2)
        g.log.update(jumps=6, parsecs=41, hails=7, shots=23, rocks=4)
        g.log["start"] -= 1234
        step(g, 2)
        g.show_log = True
    def helpcard(df, g):
        step(g, 2)
        g.show_help = True
        g.help_t = g.t

    screenshot("bespin.png", 140, 40, 4, 2, cruise)
    screenshot("coruscant.png", 140, 40, 7, 7, cruise)
    screenshot("endor-traffic.png", 140, 40, 11, 3, traffic)
    screenshot("lothal-whales.png", 140, 40, 3, 8, cruise)
    screenshot("hyperspace.png", 140, 40, 5, 1, hyper)
    screenshot("zen-burn.png", 140, 40, 9, 9, zen)
    screenshot("flight-log.png", 140, 40, 2, 0, log)
    screenshot("help.png", 140, 40, 2, 5, helpcard)


def gif():
    df, g = make_game(100, 30, 21)
    g.close_help()
    g.enter_system(3)                    # Endor: the rebel fleet
    g.sys_t, g.crafts = 18.0, []
    p = Painter()
    tmp = tempfile.mkdtemp()
    frames = []

    def sink(cv):
        frames.append(os.path.join(tmp, "f%04d.png" % len(frames)))
        p.paint(cv, df.FG).save(frames[-1])

    random.seed(5)
    g.spawn_traffic(prewarm=True, kind="stard", mode="cross")
    g.spawn_traffic(kind="tie", mode="oncoming")
    for c in g.crafts:
        if c.kind == "tie":
            c.z = 0.9
    g.spawn_traffic(kind="xwing", mode="overtake")
    step(g, 2.2, 3, sink)
    wing = min((c for c in g.crafts if c.kind == "xwing" and c.bbox), key=lambda c: c.z, default=None)
    if wing:
        for _ in range(6):               # glide the reticle onto the X-wing, then hail it
            aim_at(g, wing)
            step(g, 0.1, 3, sink)
        g.hail(wing)
        if wing.mode != "escort":
            g.join(wing)
    step(g, 3.2, 3, sink)
    tie = next((c for c in g.crafts if c.kind == "tie" and c.bbox), None)
    if tie:
        aim_at(g, tie)
        step(g, 0.4, 3, sink)
        x0, y0, x1, y1 = tie.bbox
        g.fire((x0 + x1) // 2, (y0 + y1) // 2)
    step(g, 2.2, 3, sink)
    g.barrel_roll()
    step(g, 1.8, 3, sink)
    g.mouse_t = -99
    g.dest = 8                           # Lothal: space whales
    g.state, g.state_t = "spool", 0.0
    g.say("HAN: Plotting a course for Lothal...", urgent=True)
    while g.state != "hyper":
        step(g, 1 / 30, 3, sink)
    g.hyper_len = 2.6
    while g.state != "exit":
        step(g, 1 / 30, 3, sink)
    g.body_g0 = 0.4
    g.crafts = [c for c in g.crafts if c.kind != "purrgil"]
    g.spawn_traffic(prewarm=True, kind="purrgil")
    step(g, 4.5, 3, sink)
    out = os.path.join(OUT, "demo.gif")
    pal = os.path.join(tmp, "pal.png")
    src = os.path.join(tmp, "f%04d.png")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", "10", "-i", src,
                    "-vf", "palettegen=max_colors=128:stats_mode=diff", pal], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", "10", "-i", src, "-i", pal,
                    "-lavfi", "paletteuse=dither=none:diff_mode=rectangle", "-loop", "0", out],
                   check=True)
    shutil.rmtree(tmp)
    print("wrote demo.gif", len(frames), "frames", os.path.getsize(out) // 1024, "KB")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    if "--gif-only" not in sys.argv:
        shots()
    gif()

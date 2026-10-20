#!/usr/bin/env python3
"""
drivingfalcon — 千年隼 · 银河禅意巡航（非商业同人作品 · non-commercial fan project）

你是 Han Solo，Chewie 坐在副驾驶。没有分数，没有 Game Over。
想玩就点点、开炮、跟路过的飞船打招呼、跳光速；不想动，就看着她自己遨游。

  鼠标   环顾四周（推到边缘可转向）    左键  飞船上=呼叫 / 空处=开炮    右键  开炮
  滚轮 + -  油门    方向键  转向    空格  跳光速
  b 翻滚  c 和 Chewie 聊天  h 呼叫最近的飞船  a 自动驾驶
  z 禅模式（隐藏 HUD，她会自己加速巡航、时不时跳光速）  v 驾驶舱  j 航行日志  ? 帮助  q 退出

运行:  drivingfalcon   |   drivingfalcon --zen   |   drivingfalcon --version      需要 24-bit 真彩色终端
"""
import argparse
import math
import os
import random
import re
import select
import shutil
import signal
import sys
import termios
import time
import tty

__version__ = "1.0.0"
FPS = 30
BG, HUD_BG, FG, WHITE = (4, 6, 13), (9, 11, 19), (171, 178, 191), (255, 255, 255)
GREEN, CYAN, PURPLE, AMBER = (152, 195, 121), (86, 182, 194), (198, 120, 221), (229, 192, 123)
RED, BLUE, GRAY = (224, 108, 117), (97, 175, 239), (92, 99, 112)
NEB_MX, NEB_MY = 40, 14            # 星云贴图比屏幕多出的边距（视角平移用）


# ------------------------------------------------------------- 小工具
def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def mix(a, b, t):
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def scale(c, k):
    return (min(255, int(c[0] * k)), min(255, int(c[1] * k)), min(255, int(c[2] * k)))


def ease(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def approach(cur, target, rate, dt):
    return cur + (target - cur) * min(1.0, dt * rate)


def line_char(dx, dy):
    """按视觉方向挑线段字符（字符格约 1:2）。"""
    ax, ay = abs(dx), abs(dy) * 2
    return "─" if ax > ay * 2.2 else "│" if ay > ax * 2.2 else "╲" if dx * dy > 0 else "╱"


_MIRROR = str.maketrans("/\\()<>[]{}", "\\/)(><][}{")
_mirrored = {}


def mirrored(art):
    if id(art) not in _mirrored:
        w = max(map(len, art))
        _mirrored[id(art)] = [l.ljust(w)[::-1].translate(_MIRROR) for l in art]
    return _mirrored[id(art)]


def talk(s):
    """'WHO: text | WHO: text' → [(who, text), ...]"""
    return [tuple(p.strip().split(": ", 1)) for p in s.split(" | ")]


# ------------------------------------------------------------- 飞船图鉴
def ship(name, faction, color, accent, acc, modes, group, callsigns, small, large, **kw):
    return dict(name=name, faction=faction, color=color, accent=accent, acc=acc, modes=modes.split(),
                group=group, callsigns=callsigns.split(","), small=small, large=large, **kw)


SHIPS = {
    "xwing": ship("X-wing", "rebel", (226, 228, 236), (235, 110, 100), "=", "oncoming overtake", (1, 3),
                  "RED TWO,RED FIVE,ROGUE THREE,BLUE SIX,RED LEADER", escort=True,
                  small=[" \\ / ", "=-o-=", " / \\ "],
                  large=["=\\         /=", "  \\   _   /  ", "   >-(o)-<   ", "  /   '   \\  ", "=/         \\="]),
    "tie": ship("TIE fighter", "imperial", (160, 166, 182), (120, 190, 255), "O", "oncoming overtake", (1, 3),
                "TIE PILOT,BLACK FOUR,OBSIDIAN TWO",
                small=["|-o-|"],
                large=["|\\       /|", "| \\     / |", "|--( O )--|", "| /     \\ |", "|/       \\|"]),
    "awing": ship("A-wing", "rebel", (232, 112, 104), (240, 240, 240), "<>", "oncoming overtake", (1, 3),
                  "GREEN TWO,PHOENIX THREE,GREEN LEADER", escort=True,
                  small=["/^\\"], large=["    /\\    ", "   /  \\   ", "  /_/\\_\\  ", " <======> "]),
    "slave1": ship("Slave I", "bounty", (124, 162, 122), (230, 150, 90), "o", "oncoming overtake", (1, 1),
                   "SLAVE I", size=1.15, small=["[o]"],
                   large=["  .-'''-.  ", " /  (o)  \\ ", "|  _____  |", "| /     \\ |", " \\/     \\/ "]),
    "shuttle": ship("Lambda shuttle", "imperial", (220, 222, 228), (110, 170, 255), "o", "oncoming overtake",
                    (1, 1), "SHUTTLE TYDIRIUM,IMPERIAL SHUTTLE", size=1.2, small=[" | ", "/o\\"],
                    large=["     |     ", "     |     ", "   _/o\\_   ", "  / /|\\ \\  ", " / / | \\ \\ ",
                           "/_/  |  \\_\\"]),
    "cloudcar": ship("Cloud car", "civil", (230, 150, 80), (255, 224, 150), "o", "oncoming overtake", (1, 2),
                     "CLOUD CITY PATROL,BESPIN WING TWO", escort=True,
                     small=["o=o"], large=[" ___     ___ ", "(_o_)===(_o_)", "  V       V  "]),
    "ywing": ship("Y-wing", "rebel", (230, 214, 170), (255, 140, 90), "@", "cross", (1, 3),
                  "GOLD THREE,GOLD FIVE,GRAY TWO", speed=(9, 15), near=0.5, small=["[@]=o>"],
                  large=[" [@]==========.        ", "     ||   ____\\_____   ", "     ||==[__________o>=",
                         " [@]=========='        "]),
    "stard": ship("Star Destroyer", "imperial", (172, 178, 192), (255, 196, 130), "=", "cross", (1, 1),
                  "STAR DESTROYER,ISD AVENGER,ISD DEVASTATOR", speed=(2.2, 4.0), near=0.6, capital=True,
                  small=[" _|_      ", "|___''-._ ", "'------==>"],
                  large=["      _|=|_                         ", "  ___|_____|____                    ",
                         " |              ''--..__            ", " |___                   ''--..__    ",
                         "     ''''-------....______======>   "]),
    "moncal": ship("Mon Calamari cruiser", "rebel", (120, 168, 205), (255, 220, 150), "o", "cross", (1, 1),
                   "HOME ONE,LIBERTY,INDEPENDENCE", speed=(2.2, 4.0), near=0.6, capital=True,
                   small=[" .-~~~-.  ", "(_______> "],
                   large=["      _.--~~~~~~~~~~--.._        ", "  .-~'  o  o  o  o  o  o '~-.__  ",
                          " (_____________________________> ", "   `~-.._________________..-~'   "]),
    "corvette": ship("CR90 corvette", "rebel", (222, 222, 230), (255, 110, 90), "@", "cross", (1, 1),
                     "TANTIVE IV,CR90 'LUCKY'", speed=(5, 8), near=0.5, capital=True, small=["[@]=[#]===>"],
                     large=["[@]\\                         ", "[@]|==[_]==========.______   ",
                            "[@]|====[###]===============>", "[@]|==[_]=========='------   ",
                            "[@]/                         "]),
    "transport": ship("GR-75 transport", "civil", (190, 182, 160), (255, 200, 120), "o", "cross", (1, 2),
                      "GR-75 'BRIGHT HOPE',FREIGHTER 'DUSTY',HAULER 'MOLLY'", speed=(3.5, 6), near=0.5,
                      capital=True, small=["=[][][]o>"],
                      large=["  .-========================-.  ", "=[][][][][][][][][][][][][][] o>",
                             "  '-========================-'  "]),
    "purrgil": ship("Purrgil (space whale)", "creature", (140, 176, 226), (235, 245, 255), "o", "cross", (2, 4),
                    "~", speed=(1.6, 3.0), near=0.5, pod=True, small=["<=(~~o)~"],
                    large=["            _.--''''''--._          ", "   __..--'''              `-._      ",
                           "<='__    ~   ~   ~         o  )~~~  ", "     '''--..___________..--'~~~~    "]),
    "asteroid": ship("Asteroid", "rock", (176, 154, 130), (130, 112, 96), ".`'", "oncoming", (1, 1), "",
                     dot=".", frames=True, small=[[".-.", "'-'"], [",-.", "`-'"]],
                     large=[["  .--.  ", " /    \\ ", "(  .   )", " `-.__.'"],
                            ["  _.-._ ", " (   . )", "(_     )", "  `--'  "]]),
}
FACTION_COL = {"rebel": (240, 150, 130), "imperial": (176, 186, 206), "civil": (150, 205, 150),
               "bounty": (160, 200, 130), "creature": (150, 180, 230), "rock": (150, 130, 110)}
SPK = {"HAN": AMBER, "CHEWIE": (196, 146, 96), "C-3PO": (230, 200, 90), "LOG": (120, 200, 160),
       "RADIO": (110, 190, 200), "~": (150, 180, 230)}

# ------------------------------------------------------------- 对白（没有任务，只有路上的闲聊）
HAILS = {
    "xwing": ["{cs}: Falcon! Good to see you out here.",
              "{cs}: Nice ship. Did you win her in a card game? | HAN: ...Something like that.",
              "{cs}: Waggling wings, Solo. Clear skies.",
              "{cs}: R2 says hello. At least, I think that was hello."],
    "awing": ["{cs}: Race you to the next nav buoy? | HAN: Kid, she'd lap you twice.",
              "{cs}: Just stretching our wings. Fly safe, Falcon."],
    "ywing": ["{cs}: Old Y-wings like slow days too. Steady as she goes.",
              "{cs}: Heading home for a cup of caf. Want anything?"],
    "tie": ["{cs}: Unidentified freighter, state your business. | HAN: Uh... sightseeing. | {cs}: ...Carry on.",
            "{cs}: Everything's under control. Situation normal. | HAN: Yeah. Same here, pal.",
            "CHEWIE: Hrrrnnn. | C-3PO: Chewbacca suggests we wave politely and not mention the cargo."],
    "shuttle": ["{cs}: Requesting deactivation of the— oh. Wrong channel. | HAN: Happens to the best of us.",
                "{cs}: Carrying a very important person. Please don't wave."],
    "stard": ["{cs}: Freighter, maintain your heading. | HAN: Wasn't planning on changing it.",
              "{cs}: ... | HAN: Big ship. Doesn't say much."],
    "slave1": ["{cs}: Just passing through, Solo. This time. | HAN: Chewie, keep one eye on that guy."],
    "cloudcar": ["{cs}: Lando says hi. Also, you still owe him. | HAN: Tell him the check's in the hyperspace mail.",
                 "{cs}: Beautiful evening for a patrol, Captain Solo."],
    "moncal": ["{cs}: Falcon, the admiral sends his regards. All quiet today.",
               "{cs}: It's soup night on deck four. You're welcome to dock."],
    "corvette": ["{cs}: Consular ship on a diplomatic mission. Honest. | HAN: Sure. Me too."],
    "transport": ["{cs}: Hauling medical supplies and one very grumpy tauntaun. Fly safe!",
                  "{cs}: Nice day for hauling, Solo!", "{cs}: Anyone seen my power converters? ...Never mind."],
    "purrgil": ["~: the purrgil answer with a deep, slow song you feel in your chest",
                "~: one of them turns an enormous, ancient eye toward you, then drifts on",
                "CHEWIE: Hwaaoooooo... | C-3PO: Chewbacca says they're singing about the space between stars."],
}
JOIN = ["Forming up on your wing, Falcon.", "Mind if we fly with you a while?", "On your wing. Nice and easy."]
BYE = ["Peeling off. Fly casual, Falcon.", "That's our turn. Clear skies, Solo!",
       "Breaking formation. May the Force be with you."]
SHOT = {"rebel": ["Hey! Friendly! FRIENDLY!", "Solo, was that a warning shot or a hello?", "Watch your fire, Falcon!"],
        "civil": ["Watch it! I just had her painted!", "Easy! We're just haulers out here!",
                  "Hey! I've got a family of mynocks on board!"],
        "imperial": ["That freighter's shooting at us. ...Let's patrol somewhere else.",
                     "Er— we'll just pretend we didn't see that."],
        "bounty": ["Careful, Solo. I bill extra for that."]}
WHALE_SHOT = ["HAN: Chewie. We do not shoot the whales.", "C-3PO: Sir! They're a protected species!",
              "~: the bolts fizzle harmlessly off its hide"]
HAN_IDLE = ["Easy, girl. Nice and easy.", "Quiet out here. I could get used to quiet.",
            "Chewie, remind me to fix the hyperdrive motivator. Again.",
            "She may not look like much, but she's got it where it counts.",
            "Twelve parsecs. Don't let anybody tell you different.", "Stars look different every time. Or maybe I do.",
            "No bounty hunters, no Imperials, no Jabba. Just space.",
            "Wonder what Leia's doing right now. ...Not that I care.",
            "Hear that hum? That's the sound of a well-tuned ship. Mostly.",
            "Fastest hunk of junk in the galaxy. Taking it slow today."]
CHEWIE = [p.split(" | ") for p in [
    "Rrrraaaaghhh! | He says the coolant's fine. Mostly.",
    "Hwaaurrgh. | He's asking if we can stop on Kashyyyk for snacks.",
    "Rrrrwaaugh grrr. | He's humming. Apparently it's a Wookiee lullaby.",
    "Grrrrrr... hwaa. | He says he likes the quiet days best.",
    "Wrraaaugh! | He thinks he should get to fly for once.",
    "Hrrrnnngh. | He misses his family. He'll be fine.",
    "Rrr-ah-ah-ah! | That's a Wookiee laugh. At the piloting, I'm afraid.",
    "Hrrwaaa? | He wants to know who left porg feathers in the cockpit."]]
THREEPIO = ["Sir, the odds of a peaceful trip are 3,720 to 1. In our favour, for once!",
            "I do believe this is the most relaxing flight I've had in years.",
            "R2 says the navicomputer is very happy today. I wasn't aware computers could be happy.",
            "Captain Solo, may I say how pleasant it is when nothing is exploding?"]
RADIO = ["RADIO: ...cantina band on channel seven. Yes, the same song. It's always the same song.",
         "RADIO: Anyone got a spare power converter? Tosche Station's closed again.",
         "RADIO: Weather: solar wind light, asteroid chance low, Imperial chance moderate.",
         "RADIO: Lost: one astromech, blue and white, answers to R2. Reward offered.",
         "RADIO: ...and that's the news from the Outer Rim. Fly safe out there."]
AUTO_ON = ["Chewie, take her for a while. I'm gonna rest my eyes.",
           "Autopilot's on. Wake me if anything interesting happens.", "Alright, old girl. You fly for a bit."]
PUNCH = ["Punch it, Chewie!", "Here we go. Hold on to something.", "Chewie, punch it!",
         "Alright, old girl. Show 'em what you've got."]
BOOST = ["HAN: Let's open her up a little.", "HAN: Feel that? That's the good stuff.",
         "CHEWIE: Hwaaargh! | C-3PO: Chewbacca says she likes to stretch her legs."]
ROCK_LINES = ["Never tell me the odds!", "Whoa— that one was close.", "Chewie, eyes up. Rocks.",
              "I've got a bad feeling about this..."]
ROLL_LINES = ["HAN: Woo-hoo!", "CHEWIE: Rrraaaaawgh!", "C-3PO: Oh! Must you do that, sir?", "HAN: Just keeping her limber."]
HYPER_LINES = ["C-3PO: Hyperspace is so peaceful, isn't it? Nobody shooting at us at all.",
               "HAN: Nothing to do but watch the tunnel. Best part of the job.", "CHEWIE: Hrrrmmmm."]


# ------------------------------------------------------------- 星系
def body(kind, pu, pv, r, base, acc, **kw):
    return dict(kind=kind, pu=pu, pv=pv, r=r, base=base, acc=acc, **kw)


def system(name, sub, neb, neb2, bodies, ships, traffic, arrive, chatter, asteroids=False, light=(-0.55, -0.45, 0.7)):
    n = math.sqrt(sum(v * v for v in light))
    return dict(name=name, sub=sub, neb=neb, neb2=neb2, bodies=bodies, mix=ships, traffic=traffic,
                arrive=talk(arrive), chatter=talk(chatter), asteroids=asteroids, light=tuple(v / n for v in light))


SYSTEMS = [
    system("TATOOINE", "Arkanis sector · a desert under two suns", (34, 20, 6), (20, 12, 4),
           [body("sun", 0.50, -0.55, 0.075, (255, 150, 70), (255, 246, 225), glow=(120, 60, 20)),
            body("sun", 0.70, -0.40, 0.055, (255, 120, 60), (255, 236, 205), glow=(110, 45, 15)),
            body("desert", -0.48, 0.42, 0.33, (226, 180, 112), (176, 124, 74), atmo=(255, 214, 160), spin=0.025)],
           {"transport": 3, "slave1": 1, "xwing": 1, "tie": 1, "corvette": 1, "ywing": 1}, 0.9,
           "MOS EISLEY CONTROL: Welcome back, Solo. Try not to shoot first this time.",
           "MOS EISLEY CONTROL: Reminder: no droids in the cantina. Still. | "
           "RADIO: Jawa salvage auction at noon. Slightly used droids, very cheap.", light=(0.55, -0.5, 0.67)),
    system("HOTH", "Anoat sector · ice, snow, and more ice", (8, 16, 34), (16, 22, 40),
           [body("ice", 0.46, 0.42, 0.32, (232, 240, 248), (160, 190, 222), atmo=(190, 220, 255), spin=0.02),
            body("moon", -0.62, -0.5, 0.06, (150, 150, 156), (100, 100, 108))],
           {"tie": 3, "stard": 1, "xwing": 1, "transport": 2}, 0.8,
           "ECHO BASE: Falcon, the asteroid field's lively today. Mind the big ones.",
           "ECHO BASE: Tauntauns are restless. Somebody check the shield generator. | "
           "HAN: Hoth. I can feel my eyebrows freezing from up here.", asteroids=True),
    system("BESPIN", "Anoat sector · Cloud City floats below", (36, 16, 18), (20, 10, 26),
           [body("gas", -0.4, 0.38, 0.4, (238, 176, 130), (206, 118, 112), atmo=(255, 200, 170), spin=0.02)],
           {"cloudcar": 4, "transport": 1, "slave1": 1, "tie": 1}, 1.0,
           "CLOUD CITY CONTROL: Falcon, you're cleared for the scenic route. Lando says hi.",
           "CLOUD CITY CONTROL: Tibanna gas prices are steady. Sunsets are free. | "
           "C-3PO: What a lovely city. I have a strange feeling I'd fall to pieces here."),
    system("ENDOR", "Moddell sector · the forest moon", (8, 22, 16), (14, 14, 30),
           [body("gas", -0.62, -0.48, 0.12, (150, 172, 190), (118, 138, 168), spin=0.01),
            body("deathstar2", -0.12, -0.55, 0.075, (158, 162, 168), (112, 116, 124)),
            body("forest", 0.42, 0.42, 0.30, (52, 112, 58), (96, 148, 74), atmo=(150, 205, 255), spin=0.02)],
           {"moncal": 2, "xwing": 3, "awing": 2, "ywing": 2, "corvette": 1, "tie": 1, "shuttle": 1}, 1.3,
           "REBEL FLEET: Falcon, you're in formation. Enjoy the quiet, General.",
           "REBEL FLEET: All quiet on the fleet channel. ...Suspiciously quiet. | "
           "RADIO: Ewok drum circle tonight. Bring earplugs."),
    system("DAGOBAH", "Sluis sector · swamp, mist, and something old", (12, 26, 14), (22, 30, 20),
           [body("swamp", -0.38, 0.4, 0.31, (58, 86, 52), (96, 112, 74), atmo=(170, 190, 160), spin=0.015)],
           {"xwing": 1}, 0.25,
           "RADIO: ...static. Nobody broadcasts from Dagobah. The swamp just hums.",
           "~: somewhere down there, a small green someone is probably making soup | "
           "HAN: Weird place. Feels like it's watching us."),
    system("KESSEL", "the Maelstrom · twelve parsecs, give or take", (46, 12, 36), (60, 20, 20),
           [body("moon", 0.45, 0.36, 0.26, (118, 96, 92), (74, 60, 64), atmo=(200, 120, 160), spin=0.02)],
           {"transport": 3, "slave1": 1, "tie": 2}, 0.9,
           "KESSEL TRAFFIC: Spice convoy coming through. Don't ask what's in it.",
           "HAN: Twelve parsecs, right through the Maelstrom. Good times. | "
           "KESSEL TRAFFIC: Reminder: the black hole cluster is not a shortcut.", asteroids=True),
    system("YAVIN", "Gordian Reach · a gas giant and its jungle moon", (34, 18, 8), (12, 20, 10),
           [body("gas", 0.48, 0.34, 0.42, (232, 146, 66), (176, 86, 46), atmo=(255, 190, 120), spin=0.018),
            body("forest", -0.4, -0.36, 0.09, (64, 120, 60), (100, 150, 80), atmo=(150, 205, 255), spin=0.03)],
           {"xwing": 3, "ywing": 3, "awing": 1, "moncal": 1, "corvette": 1}, 1.0,
           "MASSASSI BASE: Welcome home, Falcon. Medal ceremony's on Tuesday.",
           "HAN: Still don't know where I put that medal. | MASSASSI BASE: Temple roof is open for stargazing tonight."),
    system("CORUSCANT", "Core Worlds · one city, a whole planet wide", (20, 20, 34), (30, 24, 14),
           [body("city", 0.44, 0.4, 0.34, (78, 80, 92), (120, 122, 136), emis=(255, 196, 110),
                 atmo=(170, 180, 220), spin=0.02)],
           {"transport": 3, "shuttle": 2, "tie": 2, "stard": 1, "corvette": 2, "cloudcar": 1}, 1.7,
           "CORUSCANT TRAFFIC: Lane seven is backed up again. Expect delays of six standard hours.",
           "CORUSCANT TRAFFIC: Air taxi strike continues. Please walk. It's only nine hundred floors. | "
           "C-3PO: Home of the finest protocol academies. I do feel rather nostalgic."),
    system("LOTHAL", "Outer Rim · where the purrgil migrate", (12, 22, 40), (30, 18, 40),
           [body("grass", -0.44, 0.42, 0.3, (118, 164, 92), (52, 110, 150), atmo=(170, 210, 255), spin=0.02),
            body("moon", 0.55, -0.45, 0.06, (170, 166, 160), (120, 116, 112))],
           {"purrgil": 5, "transport": 1, "tie": 1}, 0.9,
           "LOTHAL APPROACH: Purrgil migration in progress. Please give the whales right of way.",
           "C-3PO: Oh my. They're... singing? How extraordinarily soothing. | HAN: Never get tired of these big guys."),
    system("NABOO", "Chommell sector · lakes, meadows, quiet seas", (14, 24, 44), (30, 30, 50),
           [body("ocean", 0.45, 0.38, 0.31, (38, 90, 172), (86, 150, 84), atmo=(170, 215, 255), spin=0.02)],
           {"corvette": 2, "transport": 2, "xwing": 1, "shuttle": 1}, 0.8,
           "THEED CONTROL: Welcome to Naboo. Lake country is lovely this time of year.",
           "RADIO: Gungan city reports: all bubbly. Literally. | "
           "THEED CONTROL: Reminder: no podracing in the palace district."),
]


# ------------------------------------------------------------- 行星表面（经纬度 → 颜色，全是平滑函数，旋转不闪）
def texture(b, lon, lat):
    k, base, acc, s = b["kind"], b["base"], b["acc"], math.sin
    if k == "gas":
        c = mix(base, acc, 0.5 + 0.5 * s(lat * 12.0 + s(lon * 1.6) * 0.7 + s(lat * 29.0) * 0.3))
        d = ((lon % 6.283) - 2.0) ** 2 * 4 + (lat - 0.25) ** 2 * 60      # 一个风暴眼
        return (mix(c, acc, 0.6 * (1 - d)) if d < 1.0 else c), None
    if k == "desert":
        return mix(base, acc, 0.5 + 0.3 * s(lon * 5.0 + s(lat * 7.0) * 1.4) + 0.2 * s(lat * 11.0 + lon * 2.0)), None
    if k == "ice":
        w = s(lat * 6.0 + s(lon * 2.0) * 0.8) * 0.6 + s(lon * 3.0 + lat * 4.0) * 0.4
        c = mix(base, acc, 0.3 + 0.35 * w)
        return (mix(c, (250, 252, 255), 0.7) if abs(lat) > 0.8 else c), None
    if k in ("forest", "swamp", "ocean", "grass"):
        n = s(lon * 3.1 + 1.3) * s(lat * 4.3 + 0.7) + 0.55 * s(lon * 7.3 + lat * 5.1) + 0.25 * s(lon * 13 + lat * 11)
        cl = s(lon * 4.0 + lat * 8.0 + 2.0) * s(lat * 3.3 - lon * 1.9) + 0.3 * s(lon * 11 - lat * 7)
        if k == "ocean":
            c = mix(acc, scale(acc, 0.7), n) if n > 0.5 else mix(base, scale(base, 0.8), 0.5 + 0.3 * n)
        elif k == "grass":
            c = mix(base, scale(base, 0.75), 0.5 + 0.4 * n) if n > -0.45 else acc
        else:
            c = mix(base, acc, 0.5 + 0.4 * n)
        if k == "swamp" and cl > 0.1:
            c = mix(c, (150, 166, 150), 0.6)                               # 沼泽的雾
        elif k != "swamp" and cl > (0.65 if k == "grass" else 0.6):
            c = mix(c, (236, 240, 244), 0.85)                              # 云
        if k in ("ocean", "grass") and abs(lat) > 0.9:
            c = (240, 244, 250)                                             # 极冠
        return c, None
    if k == "moon":
        return mix(base, acc, 0.5 + 0.5 * (s(lon * 9) * s(lat * 8) + 0.5 * s(lon * 17 + lat * 13))), None
    if k == "city":
        h = (math.sin(math.floor(lon * 22.0) * 12.9898 + math.floor(lat * 26.0) * 78.233) * 43758.5453) % 1.0
        return mix(base, acc, h), (scale(b["emis"], 0.35 + 2.0 * (h - 0.7)) if h > 0.7 else None)
    if k == "deathstar2":
        # 还没造完的第二死星：右半边只有骨架
        if lon > 0.15 and lat > -0.65 and not (abs(s(lon * 22)) < 0.22 or abs(s(lat * 22)) < 0.22):
            return None, None
        c = mix(base, acc, 0.5 + 0.3 * s(lon * 40) * s(lat * 40))
        if abs(lat - 0.02) < 0.035:
            c = scale(acc, 0.6)                                             # 赤道沟
        d = math.hypot(lon + 0.55, (lat + 0.38) * 1.15)
        if d < 0.24:
            c = (150, 200, 150) if d < 0.05 else scale(acc, 0.55 + 0.6 * d)  # 超级激光碟
        return c, None
    return base, None


# ------------------------------------------------------------- 终端画布：只输出与上一帧不同的格子，不闪烁
_SGR = {}


def sgr(fg, bg):
    s = _SGR.get((fg, bg))
    if s is None:
        if len(_SGR) > 30000:
            _SGR.clear()
        s = _SGR[(fg, bg)] = "\033[38;2;%d;%d;%d;48;2;%d;%d;%dm" % (fg + bg)
    return s


class Canvas:
    __slots__ = ("w", "h", "ch", "fg", "bg")

    def __init__(self, w, h, bg_rows):
        self.w, self.h, self.bg = w, h, bg_rows
        self.ch = [[" "] * w for _ in range(h)]
        self.fg = [[None] * w for _ in range(h)]

    def put(self, x, y, c, fg):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.ch[int(y)][int(x)] = c
            self.fg[int(y)][int(x)] = fg

    def text(self, x, y, s, fg, bg=None):
        if 0 <= y < self.h:
            for i, c in enumerate(s, int(x)):
                if 0 <= i < self.w:
                    self.ch[y][i], self.fg[y][i] = c, fg
                    if bg:
                        self.bg[y][i] = bg

    def render(self, prev):
        out, cf, cb, pos = [], None, None, None
        full = prev is None or (prev.w, prev.h) != (self.w, self.h)
        for y in range(self.h):
            rc, rf, rb = self.ch[y], self.fg[y], self.bg[y]
            if not full:
                pc, pf, pb = prev.ch[y], prev.fg[y], prev.bg[y]
            for x in range(self.w):
                c, f, b = rc[x], rf[x] or FG, rb[x]
                if not full and c == pc[x] and b == pb[x] and (c == " " or rf[x] == pf[x]):
                    continue
                if pos != (x, y):
                    out.append("\033[%d;%dH" % (y + 1, x + 1))
                if c == " ":
                    f = cf or FG                                            # 空格不在乎前景色
                if f != cf or b != cb:
                    out.append(sgr(f, b))
                    cf, cb = f, b
                out.append(c)
                pos = (x + 1, y)
        return "".join(out)


# ------------------------------------------------------------- 键盘 / 鼠标（SGR 鼠标协议）
TOKEN = re.compile(r"\x1b\[<(\d+);(\d+);(\d+)([Mm])|\x1b[\[O]([ABCD])|\x1b\[[\x20-\x3f]*[\x40-\x7e]|\x1bO.|"
                   r"([^\x1b])|(\x1b)", re.S)
PARTIAL = re.compile(r"\x1b(\[[\x20-\x3f]*|O)?$")


class Input:
    def __init__(self, fd):
        self.fd, self.buf, self.held = fd, "", False

    def poll(self):
        got = False
        try:
            while select.select([self.fd], [], [], 0)[0]:
                data = os.read(self.fd, 4096)
                if not data:
                    break
                self.buf, got = self.buf + data.decode("utf-8", "ignore"), True
        except (OSError, InterruptedError):
            pass
        keep, m = "", PARTIAL.search(self.buf)
        if m and (got or not self.held):          # 不完整的转义序列留到下一帧（最多一帧）
            keep, self.buf = self.buf[m.start():], self.buf[:m.start()]
        self.held = bool(keep)
        ev = []
        for t in TOKEN.finditer(self.buf):
            if t.group(1):
                ev.append(("mouse", int(t[1]), int(t[2]) - 1, int(t[3]) - 1, t[4] == "M"))
            elif t.group(5):
                ev.append(("arrow", "ABCD".index(t[5])))
            elif t.group(6) or t.group(7):
                ev.append(("key", t[6] or t[7]))
        self.buf = keep
        return ev


# ------------------------------------------------------------- 通讯字幕（打字机效果）
class Comms:
    RATE, HOLD = 40.0, 3.2

    def __init__(self):
        self.q, self.cur, self.t = [], None, 0.0

    def say(self, items, urgent=False):
        if urgent:
            self.q, self.cur = list(items), None
        elif len(self.q) < 6:
            self.q.extend(items)

    def busy(self):
        return self.cur is not None or bool(self.q)

    def dur(self):
        return len(self.cur[1]) / self.RATE + self.HOLD

    def update(self, dt):
        if self.cur is not None:
            self.t += dt
            if self.t > self.dur():
                self.cur = None
        if self.cur is None and self.q:
            self.cur, self.t = self.q.pop(0), 0.0

    def view(self):
        if self.cur:
            who, text, col = self.cur
            return who, text[:int(self.t * self.RATE) + 1], col, clamp((self.dur() - self.t) / 0.6, 0.0, 1.0)


# ------------------------------------------------------------- 场景物体
class Star:
    __slots__ = ("x", "y", "z", "col", "tw", "ph")


class Craft:
    """飞船 / 小行星。z 是归一化深度：屏幕偏移(行) = x / z。"""
    __slots__ = ("kind", "d", "mode", "x", "y", "z", "vx", "vy", "vz", "facing", "size", "age", "flash", "wobble",
                 "bbox", "sighted", "phase", "escort_t", "slot", "ex", "ey", "ez", "tier", "cs", "spin", "missed",
                 "dead")

    def __init__(self, kind, mode, x, y, z, vx=0.0, vy=0.0, vz=0.0, facing=1, size=None, tier=None):
        self.kind, self.d, self.mode, self.tier, self.facing = kind, SHIPS[kind], mode, tier, facing
        self.x, self.y, self.z, self.vx, self.vy, self.vz = x, y, z, vx, vy, vz
        self.size = self.d.get("size", 1.0) if size is None else size
        self.age = self.flash = self.wobble = self.escort_t = self.ex = self.ey = self.ez = 0.0
        self.bbox = self.slot = None
        self.sighted, self.missed, self.dead = kind == "asteroid", False, False
        self.phase, self.spin = random.uniform(0, 6.283), random.uniform(1.2, 3.0)
        self.cs = random.choice(self.d["callsigns"])


ESCORT_SLOTS = [(-1, 0), (1, 0), (1, 1)]
STAR_COLS = [(255, 255, 255), (200, 220, 255), (255, 240, 214), (255, 214, 186), (186, 204, 255)]


# ------------------------------------------------------------- 游戏本体
class Game:
    def __init__(self, fd, args):
        self.inp, self.comms = Input(fd), Comms()
        self.W = self.H = 0
        self.t = self.state_t = self.sys_t = self.full_t = 0.0
        self.speed = self.cruise_speed = 5.0
        self.state, self.dest, self.hyper_len = "cruise", 0, 4.5
        self.crafts, self.lasers, self.sparks, self.notes = [], [], [], []
        self.pan_x = self.pan_y = self.turn_x = self.turn_y = 0.0
        self.man_x = self.man_y = self.steer_x = self.steer_y = 0.0   # 方向键 / 鼠标推边缘或自动驾驶
        self.bank = self.roll = self.rs = 0.0
        self.rc, self.roll_p, self.roll_dir = 1.0, None, 1
        self.body_off_x = self.body_off_y = self.shake = self.flash = self.boost = 0.0
        self.boost_wait = 8.0
        self.shx = self.shy = self.aim_x = self.aim_y = 0
        self.mouse_t, self.last_input, self.help_t = -99.0, 0.0, 0.0
        self.zen = self.autopilot = self.auto_locked = bool(args.zen)
        self.cockpit, self.show_help, self.show_log = not args.no_cockpit, not args.zen, False
        self.banner_t0 = self.prev = self.neb_key = None
        self.chat_t, self.spawn_t, self.rock_t = 14.0, 2.0, 0.0
        self.last_line = {}
        self.stats = [] if args.stats else None
        self.log = dict(systems={}, ships={}, jumps=0, parsecs=0, hails=0, shots=0, rocks=0, start=time.monotonic())
        self.check_size()
        self.stars = []
        for _ in range(170):
            s = Star()
            s.col, s.tw, s.ph = random.choice(STAR_COLS), random.uniform(1.0, 3.5), random.uniform(0, 6.283)
            self.reset_star(s, far=False)
            self.stars.append(s)
        self.enter_system(random.randrange(len(SYSTEMS)), first=True)

    # ---------------- 几何
    def check_size(self):
        try:
            size = tuple(os.get_terminal_size(sys.stdout.fileno()))
        except OSError:
            size = tuple(shutil.get_terminal_size((100, 32)))
        if size != (self.W, self.H):
            self.W, self.H = max(size[0], 1), max(size[1], 1)
            self.F, self.cx, self.cy = self.H * 5.0, self.W / 2.0, self.H / 2.0
            self.prev = self.neb_key = None
            self.build_frame()

    def proj(self, rx, ry):
        """归一化坐标（行单位）→ 终端格子，含翻滚、平移、震动。"""
        return (self.cx + (rx * self.rc - ry * self.rs) * 2 + self.pan_x + self.shx,
                self.cy + rx * self.rs + ry * self.rc + self.pan_y + self.shy)

    def unproj(self, sx, sy):
        X, Y = (sx - self.cx - self.pan_x) / 2.0, sy - self.cy - self.pan_y
        return X * self.rc + Y * self.rs, -X * self.rs + Y * self.rc

    def closing(self):
        return min(self.speed, 40.0) * 0.032

    def mouse_active(self):
        return self.t - self.mouse_t < 12.0

    # ---------------- 星系
    def enter_system(self, idx, first=False):
        self.sys_idx, self.sys, self.sys_t = idx, SYSTEMS[idx], 0.0
        self.bodies = [dict(b) for b in self.sys["bodies"]]
        self.body_g0 = 0.55 if first else 0.06
        self.body_off_x = self.body_off_y = 0.0
        self.crafts, self.neb_key = [], None
        self.jump_at = (random.uniform(80, 140), random.uniform(25, 50))   # 普通自动驾驶 / 禅模式
        self.spawn_t = random.uniform(1.0, 4.0)
        self.log["systems"][self.sys["name"]] = self.log["systems"].get(self.sys["name"], 0) + 1
        self.banner_t0 = None if (first and self.show_help) else 0.0
        self.say(self.sys["arrive"], urgent=not first)
        if self.sys["asteroids"]:                  # 预先放些交通/石头，免得刚到时空荡荡
            for _ in range(10):
                self.spawn_rock().z = random.uniform(0.5, 4.4)
        if random.random() < 0.8:
            self.spawn_traffic(prewarm=True)

    def reset_star(self, s, far):
        s.z = random.uniform(650, 1000) if far else random.uniform(20, 1000)
        rx, ry = self.unproj(random.uniform(-0.05, 1.05) * self.W, random.uniform(-0.05, 1.05) * self.H)
        s.x, s.y = rx * s.z / self.F, ry * s.z / self.F

    # ---------------- 驾驶舱框架（预计算）
    def build_frame(self):
        W, H, cx, cy = self.W, self.H, self.W / 2.0, self.H / 2.0
        hull = (16, 15, 15)
        cells = {}
        for y in range(H):
            for x in range(W):
                r = math.hypot((x + 0.5 - cx) / cx, (y + 0.5 - cy) / cy)
                if r > 1.16:
                    cells[(x, y)] = ("·" if (x * 7 + y * 13) % 31 == 0 else " ", (50, 47, 44), hull)
                elif r > 1.085:
                    cells[(x, y)] = (" ", None, (34, 32, 31) if r > 1.10 else (24, 23, 22))
        for deg in (32, 148, 212, 328):                     # 窗框支柱
            ca, sa = math.cos(math.radians(deg)), math.sin(math.radians(deg))
            ch, steps = line_char(ca * cx, sa * cy), int(max(abs(ca * cx), abs(sa * cy)) * 0.6) + 2
            for i in range(steps + 1):
                r = 0.62 + 0.47 * i / steps
                xy = (int(cx + ca * r * cx), int(cy + sa * r * cy))
                if 0 <= xy[0] < W and 0 <= xy[1] < H and xy not in cells:
                    cells[xy] = (ch, mix((24, 26, 34), (88, 82, 74), (r - 0.62) / 0.47), None)
        self.frame_cells = [(x, y, c, f, b) for (x, y), (c, f, b) in cells.items()]
        rnd = random.Random(W * 7 + H)
        spots = [(x, y) for x, y, c, f, b in self.frame_cells if b == hull and H - 5 <= y < H - 1]
        rnd.shuffle(spots)
        pal = [(120, 230, 140), (255, 190, 90), (255, 90, 80), (110, 180, 255)]
        self.lights = [(x, y, rnd.choice(pal), rnd.uniform(0.4, 2.5), rnd.uniform(0, 6.28)) for x, y in spots[:12]]

    # ---------------- 星云背景
    def build_nebula(self):
        W, H = self.W + 2 * NEB_MX, self.H + 2 * NEB_MY
        rnd = random.Random(self.sys_idx * 7919 + W * 31 + H)
        blobs = [(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(W * 0.12, W * 0.35), rnd.uniform(H * 0.15, H * 0.42),
                  rnd.uniform(0.5, 1.0), self.sys["neb2" if i % 2 else "neb"]) for i in range(6)]
        self.neb = []
        for y in range(H):
            row = []
            for x in range(W):
                r, g, b = BG
                wave = 0.18 * math.sin(x * 0.09 + y * 0.05) * math.sin(y * 0.13 - x * 0.03)
                for bx, by, sx, sy, a, col in blobs:
                    d = ((x - bx) / sx) ** 2 + ((y - by) / sy) ** 2
                    if d < 6:
                        v = clamp(a * math.exp(-d) + wave, 0, 1.3)
                        r, g, b = r + col[0] * v, g + col[1] * v, b + col[2] * v
                row.append((min(255, int(r)) // 3 * 3, min(255, int(g)) // 3 * 3, min(255, int(b)) // 3 * 3))
            self.neb.append(row)
        self.neb_key = (self.sys_idx, self.W, self.H)

    def make_canvas(self):
        W, H = self.W, self.H
        if self.state == "hyper" or (self.state == "jump" and self.state_t > 0.4) or self.flash > 0.04:
            c = mix((6, 10, 30) if self.state == "hyper" else BG, (232, 240, 255), self.flash)
            return Canvas(W, H, [[c] * W for _ in range(H)])
        if self.neb_key != (self.sys_idx, W, H):
            self.build_nebula()
        neb = self.neb
        ox = clamp(NEB_MX + int(-(self.pan_x + self.body_off_x) * 0.6), 0, 2 * NEB_MX)
        oy = clamp(NEB_MY + int(-(self.pan_y + self.body_off_y) * 0.6), 0, 2 * NEB_MY)
        if abs(self.roll) < 0.03:
            return Canvas(W, H, [neb[oy + y][ox:ox + W] for y in range(H)])
        rc, rs, cx, cy = self.rc, self.rs, self.cx, self.cy        # 翻滚时把星云也转起来
        mw, mh = len(neb[0]) - 1, len(neb) - 1
        rows = []
        for y in range(H):
            Y = y - cy
            rows.append([neb[clamp(int(cy - X * rs + Y * rc + oy), 0, mh)][clamp(int(cx + (X * rc + Y * rs) * 2 + ox), 0, mw)]
                         for X in ((x - cx) / 2.0 for x in range(W))])
        return Canvas(W, H, rows)

    # ---------------- 主循环
    def run(self):
        out, last = sys.stdout.buffer, time.monotonic()
        while True:
            now = time.monotonic()
            dt, last = min(now - last, 0.1), now
            self.check_size()
            for ev in self.inp.poll():
                self.on_event(ev)
            self.update(dt)
            cv = self.draw()
            self.full_t += dt
            if self.full_t > 10.0:                  # 偶尔整屏重绘，防止残影
                self.full_t, self.prev = 0.0, None
            s, self.prev = cv.render(self.prev), cv
            if s:
                out.write(s.encode("utf-8"))
                out.flush()
            spent = time.monotonic() - now
            if self.stats is not None:
                self.stats.append(spent)
            time.sleep(max(0.0, 1.0 / FPS - spent))

    # ---------------- 输入
    def touch(self):
        self.last_input = self.t
        if self.autopilot and not self.auto_locked:
            self.autopilot = False

    def on_event(self, ev):
        if ev[0] == "mouse":
            _, btn, x, y, press = ev
            if btn & 64:                              # 滚轮 = 油门
                if press:
                    self.throttle(-1 if btn & 1 else 1)
                    self.touch()
                return
            self.aim_x, self.aim_y, self.mouse_t = x, y, self.t
            self.touch()
            if btn & 32 or not press:                 # 纯移动 / 松开
                return
            if self.show_help:
                return self.close_help()
            if btn & 3 == 0:
                c = self.craft_at(x, y, pad=1, hailable=True)
                self.hail(c) if c else self.fire(x, y)
            elif btn & 3 == 2:
                self.fire(x, y)
            return
        self.touch()
        if ev[0] == "arrow":
            d = ev[1]
            if d < 2:
                self.man_y = clamp(self.man_y + (3.0 if d else -3.0), -12, 12)
            else:
                self.man_x = clamp(self.man_x + (5.0 if d == 2 else -5.0), -24, 24)
            return
        k = ev[1]
        if k in ("q", "Q", "\x03"):
            raise SystemExit(0)
        if self.show_help:
            return self.close_help()
        k = k.lower()
        if k == "\x1b":
            self.show_log = False
        elif k == " ":
            self.punch_it()
        elif k in ("+", "="):
            self.throttle(1)
        elif k in ("-", "_"):
            self.throttle(-1)
        elif k == "b":
            self.barrel_roll()
        elif k == "c":
            roar, tr = random.choice(CHEWIE)
            self.say([("CHEWIE", roar), (random.choice(("HAN", "C-3PO")), tr)], urgent=True)
        elif k == "h":
            c = self.nearest_craft()
            self.hail(c) if c else self.say("HAN: Nobody out there to talk to. Fine by me.", urgent=True)
        elif k == "f":
            self.fire(*((self.aim_x, self.aim_y) if self.mouse_active() else (int(self.cx), int(self.cy))))
        elif k == "a":
            self.autopilot = self.auto_locked = not self.autopilot
            self.say("HAN: " + (random.choice(AUTO_ON) if self.autopilot else "I've got her, Chewie."), urgent=True)
        elif k == "z":
            self.zen = not self.zen
            if self.zen:
                self.say("~: zen mode · she'll cruise, burn and jump on her own · z to come back")
        elif k == "v":
            self.cockpit = not self.cockpit
        elif k == "j":
            self.show_log = not self.show_log
        elif k == "?":
            self.show_help, self.help_t = True, self.t

    def close_help(self):
        self.show_help = False
        if self.banner_t0 is None:
            self.banner_t0 = self.sys_t

    def throttle(self, d):
        self.cruise_speed = clamp(self.cruise_speed + d, 1.0, 30.0)

    def say(self, items, urgent=False):
        """items: 'WHO: text | WHO: text' 或 [(who, text), ...]"""
        if isinstance(items, str):
            items = talk(items)
        self.comms.say([(w, t, SPK.get(w, CYAN)) for w, t in items], urgent)

    def say_rl(self, key, gap, items, urgent=True):
        """限频说话，避免刷屏。"""
        if self.t - self.last_line.get(key, -99) > gap:
            self.last_line[key] = self.t
            self.say(items, urgent)

    def punch_it(self):
        if self.state == "cruise":
            self.dest = random.choice([i for i in range(len(SYSTEMS)) if i != self.sys_idx])
            self.set_state("spool")
            self.say("HAN: Plotting a course for %s..." % SYSTEMS[self.dest]["name"].title(), urgent=True)

    def barrel_roll(self):
        if self.roll_p is None and self.state in ("cruise", "exit"):
            self.roll_p, self.roll_dir = 0.0, random.choice((-1, 1))
            if random.random() < 0.6:
                self.say(random.choice(ROLL_LINES), urgent=True)

    def fire(self, x, y):
        if self.state in ("hyper", "jump"):
            return
        self.log["shots"] += 1
        for gx in (self.W * 0.25, self.W * 0.75):
            self.lasers.append([gx, self.H - 2, float(x), float(y), 0.0])
            self.sparks.append([gx, self.H - 3, 0.0, -1.0, 0.12, 0.12, (255, 200, 150)])

    def craft_at(self, x, y, pad=0, hailable=False):
        hits = [c for c in self.crafts if c.bbox and not (hailable and c.kind == "asteroid")
                and c.bbox[0] - pad <= x <= c.bbox[2] + pad and c.bbox[1] - pad <= y <= c.bbox[3] + pad]
        return min(hits, key=lambda c: c.z) if hits else None

    def nearest_craft(self):
        tx, ty = (self.aim_x, self.aim_y) if self.mouse_active() else (self.cx, self.cy)
        seen = [c for c in self.crafts if c.bbox and c.kind != "asteroid" and c.bbox[2] >= 0 and c.bbox[0] < self.W
                and c.bbox[3] >= 0 and c.bbox[1] < self.H]
        return min(seen, key=lambda c: math.hypot(((c.bbox[0] + c.bbox[2]) / 2 - tx) / 2,
                                                  (c.bbox[1] + c.bbox[3]) / 2 - ty), default=None)

    # ---------------- 互动：呼叫 / 编队 / 被打
    def hail(self, c):
        self.log["hails"] += 1
        c.wobble = 1.0
        fc = FACTION_COL[c.d["faction"]]
        items = [(w.replace("{cs}", c.cs), t) for w, t in talk(random.choice(HAILS.get(c.kind, ["{cs}: ..."])))]
        items = [(w, t, SPK.get(w, fc)) for w, t in items]
        if c.d.get("escort") and c.mode != "escort" and random.random() < 0.7 and self.join(c):
            items.append((c.cs, random.choice(JOIN), fc))
        self.comms.say(items, urgent=True)

    def join(self, c):
        free = [s for s in ESCORT_SLOTS if s not in {e.slot for e in self.crafts if e.mode == "escort"}]
        if not free:
            return False
        side, row = c.slot = free[0]
        c.mode, c.escort_t = "escort", random.uniform(25, 45)
        c.ez = 0.28 if row == 0 else 0.45
        c.ex = side * self.W * (0.155 if row == 0 else 0.11)
        c.ey = self.H * (0.16 if row == 0 else -0.14)
        return True

    def release(self, c, quiet=False):
        c.mode, c.slot = "overtake", None
        c.vz = -(self.closing() + random.uniform(0.25, 0.4))
        c.vx = math.copysign(random.uniform(0.6, 1.2), c.x) * c.z
        if not quiet:
            self.say([(c.cs, random.choice(BYE))])

    def shot(self, c):
        f, c.flash = c.d["faction"], 0.35
        if c.kind == "asteroid":
            self.break_rock(c)
        elif f == "creature":
            self.say_rl("whale", 6, random.choice(WHALE_SHOT))
        elif c.mode == "escort":
            self.release(c, quiet=True)
            self.say_rl("shot", 3, [(c.cs, "Okay... we'll give you some space.")])
        elif c.kind in ("tie", "shuttle"):                      # 帝国的家伙会被吓跑
            c.mode, c.vz, c.vx = "overtake", -(self.closing() + 0.6), math.copysign(1.5, c.x) * c.z
            self.say_rl("shot", 3, [(c.cs, random.choice(SHOT["imperial"]))])
        elif c.d.get("capital"):
            self.say_rl("shot", 3, "~: their shields don't even flicker")
        else:
            c.wobble = 1.2
            self.say_rl("shot", 3, [(c.cs, random.choice(SHOT.get(f, ["Hey!"])))])

    def break_rock(self, c):
        if c.bbox:
            mx, my = (c.bbox[0] + c.bbox[2]) / 2, (c.bbox[1] + c.bbox[3]) / 2
            for _ in range(10):
                life = random.uniform(0.3, 0.8)
                self.sparks.append([mx, my, random.uniform(-14, 14), random.uniform(-6, 6), life, life, (170, 150, 130)])
        if c.size > 0.75 and c.tier in ("small", "large"):     # 大石头碎成两块
            for side in (-1, 1):
                self.crafts.append(Craft("asteroid", "oncoming", c.x, c.y, c.z * 1.02, vz=c.vz, size=c.size * 0.55,
                                         vx=side * random.uniform(1.5, 3.0) * c.z, vy=random.uniform(-1, 1) * c.z))
        c.dead = True
        self.log["rocks"] += 1

    # ---------------- 生成交通
    def spawn_traffic(self, prewarm=False, kind=None, mode=None):
        kind = kind or random.choices(list(self.sys["mix"]), weights=list(self.sys["mix"].values()))[0]
        d = SHIPS[kind]
        mode, n, W, H = mode or random.choice(d["modes"]), random.randint(*d["group"]), self.W, self.H
        if mode == "cross":                                     # 侧面横穿画面
            facing, spd0 = random.choice((-1, 1)), random.uniform(*d["speed"])
            sy0, big0, edge = random.uniform(0.2, 0.8) * H, random.random() < d["near"], 0.0
            for i in range(n):
                big = random.random() < 0.5 if d.get("pod") else big0
                tier = "large" if big else "small"
                aw = max(map(len, d[tier]))
                z = random.uniform(0.28, 0.4) if big else random.uniform(0.7, 0.95)
                gap = edge + aw / 2.0 + 2
                edge = gap + aw / 2.0 + random.randint(4, 14)
                sx = random.uniform(0.15, 0.85) * W if prewarm else (-gap if facing > 0 else W + gap)
                rx, ry = self.unproj(sx, sy0 + (random.uniform(-0.18, 0.18) * H if i else 0))
                c = Craft(kind, "cross", rx * z, ry * z, z, vx=facing * spd0 * (1.0 if big else 0.65) * z / 2.0,
                          facing=facing, tier=tier)
                c.age = 3.0 if prewarm else 0.0
                self.crafts.append(c)
        elif mode == "oncoming":                                # 从远处迎面掠过
            u, v = random.choice((-1, 1)) * random.uniform(0.2, 1.1), random.uniform(-0.8, 0.8)
            vz, z0 = random.uniform(0.10, 0.28), random.uniform(1.0, 3.0) if prewarm else 4.2
            for i in range(n):
                o = i - (n - 1) / 2.0
                self.crafts.append(Craft(kind, mode, u * W / 16.0 + o * 4.0, v * H / 8.0 + abs(o) * 1.5,
                                         z0 + abs(o) * 0.15, vz=vz))
        else:                                                   # 从身后超车，飞向远方
            u, v = random.choice((-1, 1)) * random.uniform(1.05, 1.3), random.uniform(-0.5, 0.7)
            vz = -(self.closing() + random.uniform(0.12, 0.3))
            for i in range(n):
                o = i - (n - 1) / 2.0
                z = 0.2 + abs(o) * 0.05
                self.crafts.append(Craft(kind, mode, u * W / 4.0 * z + o * 1.2, v * H / 2.0 * z + abs(o) * 0.4, z, vz=vz))

    def spawn_rock(self):
        c = Craft("asteroid", "oncoming", random.uniform(-1.3, 1.3) * self.W / 16.0,
                  random.uniform(-1.2, 1.2) * self.H / 8.0, random.uniform(3.6, 4.6), vz=random.uniform(0.0, 0.08),
                  vx=random.uniform(-0.3, 0.3), vy=random.uniform(-0.15, 0.15), size=random.uniform(0.55, 1.5))
        self.crafts.append(c)
        return c

    # ---------------- 更新
    def set_state(self, s):
        self.state, self.state_t = s, 0.0

    def update(self, dt):
        self.t += dt
        self.state_t += dt
        self.sys_t += dt
        self.boost = max(0.0, self.boost - dt)
        st = self.state
        if st == "cruise":
            burn = self.boost > 0 and self.autopilot
            target, k = (max(self.cruise_speed, 24.0), 0.8) if burn else (self.cruise_speed, 1.5)
        elif st == "spool":
            target, k = 1.0, 2.5
            if self.state_t > 1.8:
                self.set_state("jump")
                self.say("HAN: " + random.choice(PUNCH), urgent=True)
        elif st == "jump":
            target, k = 220.0, 3.0
            self.flash = max(self.flash, clamp((self.state_t - 0.5) / 0.25, 0, 1))
            if self.state_t > 0.75:
                self.set_state("hyper")
                self.hyper_len, self.crafts, self.lasers = random.uniform(3.5, 5.5), [], []
                self.flash, self.shake = 1.0, 0.6
                self.log["jumps"] += 1
                self.log["parsecs"] += random.randint(3, 9)
                if random.random() < 0.5:
                    self.say(random.choice(HYPER_LINES))
        elif st == "hyper":
            target, k = 170.0, 2.0
            if self.state_t > self.hyper_len:
                self.enter_system(self.dest)
                self.set_state("exit")
                self.speed, self.flash, self.shake = 40.0, 1.0, 0.5
        else:                                                   # exit：出超空间减速
            target, k = self.cruise_speed, 2.2
            if self.state_t > 1.2:
                self.set_state("cruise")
        self.speed = approach(self.speed, target, k, dt)
        self.flash = max(0.0, self.flash - dt * 1.6)
        self.shake = max(0.0, self.shake - dt)
        self.shx = random.randint(-1, 1) if self.shake > 0.05 else 0
        self.shy = random.randint(-1, 1) if self.shake > 0.3 else 0
        if self.show_help and self.t - self.help_t > 16.0:
            self.close_help()

        # 自动驾驶：不操作，她就自己飞。禅模式下接管更快、会加速巡航、时不时跳光速
        if not self.autopilot and st == "cruise" and not self.show_help \
                and self.t - self.last_input > (6.0 if self.zen else 25.0):
            self.autopilot, self.auto_locked = True, False
            self.say("HAN: " + random.choice(AUTO_ON))
        if self.autopilot and st == "cruise":
            if self.sys_t > self.jump_at[1 if self.zen else 0]:
                self.punch_it()
            elif self.zen:
                self.boost_wait -= dt
                if self.boost_wait <= 0:
                    self.boost, self.boost_wait = random.uniform(4.0, 7.0), random.uniform(12.0, 22.0)
                    self.say_rl("boost", 45, random.choice(BOOST), urgent=False)

        # 转向：方向键是冲量（会衰减），鼠标推边缘 / 自动驾驶是平滑目标
        self.man_x *= math.exp(-dt * 1.1)
        self.man_y *= math.exp(-dt * 1.1)
        tx = ty = 0.0
        if self.autopilot:
            tx = 2.6 * math.sin(self.t * 0.071) + 1.4 * math.sin(self.t * 0.13 + 1.7)
            ty = 0.9 * math.sin(self.t * 0.05 + 0.4)
        elif self.mouse_active() and st != "hyper":
            nx, ny = (self.aim_x - self.cx) / self.cx, (self.aim_y - self.cy) / self.cy
            tx = math.copysign((abs(nx) - 0.72) / 0.28 * 9.0, nx) if abs(nx) > 0.72 else 0.0
            ty = math.copysign((abs(ny) - 0.72) / 0.28 * 4.0, ny) if abs(ny) > 0.72 else 0.0
        rate = 0.5 if self.autopilot else 2.0
        self.steer_x, self.steer_y = approach(self.steer_x, tx, rate, dt), approach(self.steer_y, ty, rate, dt)
        self.turn_x, self.turn_y = self.man_x + self.steer_x, self.man_y + self.steer_y

        # 倾斜与翻滚
        extra = 0.0
        if self.roll_p is not None:
            self.roll_p += dt / 1.6
            if self.roll_p >= 1.0:
                self.roll_p = None
            else:
                extra = 2 * math.pi * ease(self.roll_p) * self.roll_dir
        self.bank = approach(self.bank, clamp(-self.turn_x * 0.012, -0.3, 0.3), 2.0, dt)
        self.roll = self.bank + extra
        self.rc, self.rs = math.cos(self.roll), math.sin(self.roll)

        # 视角平移（鼠标 = 转头看看），行星随转向漂移后慢慢回正
        look = self.mouse_active() and st != "hyper"
        self.pan_x = approach(self.pan_x, -(self.aim_x - self.cx) * 0.28 if look else 0.0, 2.5, dt)
        self.pan_y = approach(self.pan_y, -(self.aim_y - self.cy) * 0.28 if look else 0.0, 2.5, dt)
        back = math.exp(-dt * 0.12)
        self.body_off_x = clamp(self.body_off_x - self.turn_x * dt, -self.W * 0.6, self.W * 0.6) * back
        self.body_off_y = clamp(self.body_off_y - self.turn_y * dt, -self.H * 0.6, self.H * 0.6) * back

        dz = min(self.speed, 30.0) * 60 * dt
        txs, tys = self.turn_x * dt / (2 * self.F), self.turn_y * dt / self.F
        for s in self.stars:
            s.z -= dz
            if s.z < 8:
                self.reset_star(s, far=True)
            else:
                s.x -= txs * s.z
                s.y -= tys * s.z
        self.update_crafts(dt)
        self.update_fx(dt)

        if st in ("cruise", "exit"):
            self.spawn_t -= dt
            if self.spawn_t <= 0:
                if sum(c.kind != "asteroid" for c in self.crafts) < 9:
                    self.spawn_traffic()
                self.spawn_t = random.uniform(3.5, 9.0) / self.sys["traffic"]
            if self.sys["asteroids"]:
                self.rock_t -= dt
                if self.rock_t <= 0:
                    if sum(c.kind == "asteroid" for c in self.crafts) < 16:
                        self.spawn_rock()
                    self.rock_t = random.uniform(0.6, 1.6)

        self.comms.update(dt)
        if st == "cruise":
            self.chat_t -= dt
            if self.chat_t <= 0 and not self.comms.busy():
                self.chatter()

    def chatter(self):
        r = random.random()
        if r < 0.30:
            self.say("HAN: " + random.choice(HAN_IDLE))
        elif r < 0.50:
            roar, tr = random.choice(CHEWIE)
            self.say([("CHEWIE", roar), (random.choice(("HAN", "C-3PO")), tr)])
        elif r < 0.62:
            self.say("C-3PO: " + random.choice(THREEPIO))
        elif r < 0.78:
            self.say(random.choice(RADIO))
        else:
            self.say([random.choice(self.sys["chatter"])])
        self.chat_t = random.uniform(24, 48) * (1.6 if self.zen else 1.0)

    def update_crafts(self, dt):
        base, W, H = self.closing(), self.W, self.H
        tx, ty = self.turn_x * dt / 2.0, self.turn_y * dt
        for c in self.crafts:
            c.age += dt
            c.flash, c.wobble = max(0.0, c.flash - dt), max(0.0, c.wobble - dt)
            if c.mode == "escort":                                  # 僚机：弹簧跟随指定位置
                c.escort_t -= dt
                bob = math.sin(self.t * 0.9 + c.phase) * 0.6 * c.z
                c.z = approach(c.z, c.ez, 0.9, dt)
                c.x = approach(c.x, c.ex * c.z, 0.9, dt)
                c.y = approach(c.y, c.ey * c.z + bob, 0.9, dt)
                if c.escort_t <= 0:
                    self.release(c)
            elif c.mode == "cross":
                c.x += c.vx * dt
                c.y += math.sin(self.t * 0.5 + c.phase) * 0.15 * dt * c.z
            else:
                c.z -= (base + c.vz) * dt
                c.x += c.vx * dt
                c.y += c.vy * dt
            c.x -= tx * c.z
            c.y -= ty * c.z
            if not c.bbox:
                if c.z < 0.1 or c.z > 5.5 or (c.mode == "overtake" and c.z > 1.5 and c.age > 3):
                    c.dead = True
                continue
            x0, y0, x1, y1 = c.bbox
            if c.kind == "asteroid" and not c.missed and c.z < 0.3 \
                    and abs((x0 + x1) / 2 - self.cx) < W * 0.22 and abs((y0 + y1) / 2 - self.cy) < H * 0.25:
                c.missed, self.shake = True, 0.7                    # 擦肩而过
                self.say_rl("rock", 14, "HAN: " + random.choice(ROCK_LINES))
            if c.kind == "purrgil" and random.random() < dt * 0.5 and (0 <= x0 < W or 0 <= x1 < W):
                self.notes.append([random.uniform(x0, x1), y0 - 1, random.uniform(0, 6.28), 3.0])
            off = x1 < -1 or x0 > W or y1 < -1 or y0 > H
            if c.z < 0.1 or c.z > 5.5:
                c.dead = True
            elif off and c.mode == "cross":
                c.dead = c.age > 2 and ((x0 > W if c.facing > 0 else x1 < -1) or y1 < -1 or y0 > H)
            elif off and c.mode != "escort":
                c.dead = c.age > 4
        self.crafts = [c for c in self.crafts if not c.dead]

    def update_fx(self, dt):
        for L in self.lasers:
            L[4] += dt * 3.2
            if L[4] >= 1.0:
                self.impact(L[2], L[3])
        self.lasers = [L for L in self.lasers if L[4] < 1.0]
        for sp in self.sparks:
            sp[4] -= dt
            sp[0] += sp[2] * dt
            sp[1] += sp[3] * dt
        self.sparks = [sp for sp in self.sparks if sp[4] > 0]
        for n in self.notes:
            n[3] -= dt
            n[1] -= dt * 1.4
            n[0] += math.sin(self.t * 2 + n[2]) * dt * 2
        self.notes = [n for n in self.notes if n[3] > 0]

    def impact(self, x, y):
        c = self.craft_at(x, y, pad=1)
        if c:
            self.shot(c)
        for _ in range(6 if c else 4):
            life = random.uniform(0.2, 0.45)
            self.sparks.append([x, y, random.uniform(-16, 16), random.uniform(-7, 7), life, life,
                                (255, 220, 120) if c else (255, 170, 90)])

    # ---------------- 绘制
    def draw(self):
        cv = self.make_canvas()
        if self.W < 44 or self.H < 14:
            cv.text(1, 0, "make the terminal a little bigger", AMBER)
            return cv
        self.draw_stars(cv)
        if self.state != "hyper":
            self.draw_bodies(cv)
            self.draw_crafts(cv)
        self.draw_fx(cv)
        self.draw_reticle(cv)
        if self.cockpit:
            self.draw_cockpit(cv)
        self.draw_hud(cv)
        return cv

    def draw_stars(self, cv):
        W, H, F = self.W, self.H, self.F
        trail = clamp((self.speed - 14) * 5, 0, 750)           # 越快拖得越长
        hyper = self.state in ("hyper", "jump")
        for s in self.stars:
            hx, hy = self.proj(s.x * F / s.z, s.y * F / s.z)
            if not (-2 <= hx < W + 2 and -2 <= hy < H + 2):
                self.reset_star(s, far=False)
                continue
            b = clamp(1.25 - s.z / 900, 0.15, 1.0)
            if trail > 6:
                zt = s.z + trail
                qx, qy = self.proj(s.x * F / zt, s.y * F / zt)
                head = (225, 238, 255) if hyper else mix(s.col, WHITE, 0.5)
                self.streak(cv, qx, qy, hx, hy, scale(head, b + 0.3), (36, 64, 140) if hyper else scale(s.col, 0.25))
            else:
                ch = "·" if s.z > 420 else "+" if s.z > 160 else "*"
                cv.put(hx, hy, ch, scale(s.col, b * (0.78 + 0.22 * math.sin(self.t * s.tw + s.ph))))

    def streak(self, cv, x0, y0, x1, y1, head, tail):
        dx, dy = x1 - x0, y1 - y0
        n = int(max(abs(dx), abs(dy)))
        if n < 1:
            return cv.put(x1, y1, "·", head)
        if n > 46:
            x0, y0, n = x1 - dx * 46 / n, y1 - dy * 46 / n, 46
            dx, dy = x1 - x0, y1 - y0
        ch = line_char(dx, dy)
        for i in range(n + 1):
            k = i / n
            cv.put(x0 + dx * k, y0 + dy * k, ch, mix(tail, head, k * k))

    def body_cells(self, b, R):
        """行星的格子缓存：半块字符 ▀▄ 让竖向分辨率翻倍，自转时每秒刷新两次。"""
        key = (int(R * 4), int(self.t * 2) if b.get("spin") else 0)
        if b.get("ck") != key:
            t, cells = key[1] / 2.0, []
            if b["kind"] == "sun":
                gi = int(R * 2.6) + 1
                for dy in range(-gi, gi + 1):
                    for dx in range(-2 * gi - 1, 2 * gi + 2):
                        d = math.hypot(dx / 2.0, dy) / R
                        if 0.85 < d < 2.6:
                            cells.append((dx, dy, None, b["glow"], ((2.6 - d) / 1.75) ** 2 * 0.7))
            ri, rx = int(R) + 1, R * 2.0
            for dy in range(-ri, ri + 1):
                vt, vb = (dy - 0.25) / R, (dy + 0.25) / R
                for dx in range(-int(rx) - 1, int(rx) + 2):
                    top, bot = self.sample(b, dx / rx, vt, t), self.sample(b, dx / rx, vb, t)
                    if top is not None:
                        cells.append((dx, dy, "▀", top, bot))
                    elif bot is not None:
                        cells.append((dx, dy, "▄", bot, None))
            b["ck"], b["cells"] = key, cells
        return b["cells"]

    def sample(self, b, u, v, t):
        d2 = u * u + v * v
        if d2 > 1.0:
            return None
        nz = math.sqrt(1.0 - d2)
        if b["kind"] == "sun":
            return mix(b["base"], b["acc"], nz ** 0.6)
        col, emis = texture(b, math.atan2(u, nz) + t * b.get("spin", 0.0), v)
        if col is None:
            return None
        L = self.sys["light"]
        dif = u * L[0] + v * L[1] + nz * L[2]
        lit = 0.05 + 0.95 * clamp(dif * 1.15 + 0.05, 0.0, 1.0)
        c = scale(col, lit)
        if b.get("atmo"):
            c = mix(c, b["atmo"], (1.0 - nz) ** 2.5 * 0.75 * clamp(dif + 0.35, 0, 1))
        if emis and lit < 0.4:
            c = mix(c, emis, (0.4 - lit) / 0.4 * 0.85)              # 夜面的城市灯光
        return c

    def draw_bodies(self, cv):
        W, H, g = self.W, self.H, self.body_g0 + (1 - self.body_g0) * ease(self.sys_t / 16.0)   # 抵达时由远及近
        for b in self.bodies:
            R = b["r"] * H * g
            bx, by = self.proj(b["pu"] * g * W / 4.0 + self.body_off_x / 2.0, b["pv"] * g * H / 2.0 + self.body_off_y)
            if R < 0.8:
                cv.put(bx, by, "·" if R < 0.4 else "•", b["acc"] if b["kind"] == "sun" else b["base"])
                continue
            ibx, iby = int(round(bx)), int(round(by))
            for dx, dy, ch, fg, bg in self.body_cells(b, R):
                x, y = ibx + dx, iby + dy
                if 0 <= x < W and 0 <= y < H:
                    if ch is None:                                     # 光晕：与背景混合
                        cv.bg[y][x] = mix(cv.bg[y][x], fg, bg)
                    else:
                        cv.ch[y][x], cv.fg[y][x] = ch, fg
                        if bg:
                            cv.bg[y][x] = bg

    def draw_crafts(self, cv):
        W, H = self.W, self.H
        for c in sorted(self.crafts, key=lambda c: -c.z):
            d = c.d
            sx, sy = self.proj(c.x / c.z, c.y / c.z)
            if c.mode == "cross":
                s = 3.0 if c.tier == "large" else 1.6
            else:
                s = c.size / c.z
                c.tier = "large" if s >= 3.0 else "small" if s >= 1.1 else "tiny" if s >= 0.3 else None
            if c.tier is None:
                c.bbox = None
                continue
            bright = 0.45 + 0.55 * min(1.0, s / 3.0)
            col, acc = scale(d["color"], bright), scale(d["accent"], min(1.0, bright + 0.2))
            if c.flash > 0:
                col = acc = mix(col, (160, 235, 255), c.flash / 0.35)  # 护盾闪光
            if c.tier == "tiny":
                x, y = int(round(sx)), int(round(sy))
                cv.put(x, y, d.get("dot", "·"), col)
                c.bbox = (x - 1, y - 1, x + 1, y + 1)
                continue
            art = d[c.tier]
            if d.get("frames"):
                art = art[int(c.age * c.spin) % len(art)]
            if c.facing < 0:
                art = mirrored(art)
            h, w = len(art), max(map(len, art))
            x0 = int(round(sx - w / 2.0)) + (int(round(math.sin(self.t * 22))) if c.wobble > 0 else 0)
            y0 = int(round(sy - h / 2.0))
            for j, line in enumerate(art):
                if 0 <= y0 + j < H:
                    rc, rf = cv.ch[y0 + j], cv.fg[y0 + j]
                    for i, ch in enumerate(line, x0):
                        if ch != " " and 0 <= i < W:
                            rc[i], rf[i] = ch, acc if ch in d["acc"] else col
            c.bbox = (x0, y0, x0 + w - 1, y0 + h - 1)
            if not c.sighted and x0 + w > 0 and x0 < W and y0 + h > 0 and y0 < H:   # 记入航行日志
                c.sighted = True
                if c.kind not in self.log["ships"]:
                    self.say("LOG: new sighting · " + d["name"])
                self.log["ships"][c.kind] = self.log["ships"].get(c.kind, 0) + 1

    def draw_fx(self, cv):
        for sx, sy, tx, ty, p in self.lasers:
            ch = line_char(tx - sx, ty - sy)
            for back, col in ((0.07, (150, 30, 30)), (0.035, (220, 60, 55)), (0.0, (255, 150, 140))):
                if p >= back:
                    cv.put(sx + (tx - sx) * (p - back), sy + (ty - sy) * (p - back), ch, col)
        for x, y, _, _, life, full, col in self.sparks:
            cv.put(x, y, "*" if life > full / 2 else "·", scale(col, 0.4 + 0.6 * life / full))
        for x, y, _, life in self.notes:                                 # 太空鲸的歌
            cv.put(x, y, "~", scale((170, 200, 245), 0.3 + 0.7 * min(1.0, life / 1.5)))

    def draw_reticle(self, cv):
        if not self.mouse_active() or self.zen or self.state == "hyper" or self.show_help:
            return
        ax, ay = clamp(self.aim_x, 2, self.W - 3), clamp(self.aim_y, 1, self.H - 2)
        hov = self.craft_at(ax, ay, pad=1, hailable=True)
        col = GREEN if hov else BLUE
        for dx, dy, ch in ((0, 0, "+"), (-2, -1, "┌"), (2, -1, "┐"), (-2, 1, "└"), (2, 1, "┘")):
            cv.put(ax + dx, ay + dy, ch, col)
        if hov:
            label = " %s · click to hail " % hov.d["name"]
            cv.text(ax + 4 if ax + 4 + len(label) < self.W else ax - 4 - len(label), ay - 1, label,
                    FACTION_COL[hov.d["faction"]], HUD_BG)

    def draw_cockpit(self, cv):
        for x, y, ch, fg, bg in self.frame_cells:
            cv.ch[y][x], cv.fg[y][x] = ch, fg
            if bg:
                cv.bg[y][x] = bg
        for x, y, col, rate, ph in self.lights:                         # 仪表盘上闪烁的小灯
            cv.ch[y][x], cv.fg[y][x] = "•", col if math.sin(self.t * rate + ph) > 0.1 else scale(col, 0.25)

    def segs(self, cv, x, y, parts, bg=None):
        for text, col in parts:
            cv.text(x, y, text, col or FG, bg)
            x += len(text)
        return x

    def draw_hud(self, cv):
        W, H, st = self.W, self.H, self.state
        if not self.zen:
            for y in (0, H - 1):
                cv.ch[y], cv.bg[y] = [" "] * W, [HUD_BG] * W
            x = self.segs(cv, 1, 0, [(" MILLENNIUM FALCON ", GREEN), ("│ ", GRAY), (self.sys["name"], AMBER),
                                     ("  " + self.sys["sub"], GRAY)])
            if st in ("spool", "jump"):
                p = int(clamp(self.state_t / 1.8, 0, 1) * 10) if st == "spool" else 10
                mode = ("JUMP → %s [%s]" % (SYSTEMS[self.dest]["name"], "=" * p + " " * (10 - p)), AMBER)
            else:
                mode = ("LIGHTSPEED", CYAN) if st == "hyper" else ("AUTOPILOT", GREEN) if self.autopilot else ("MANUAL", FG)
            right = [("SPEED ", GRAY), (("%.0f" if self.speed >= 20 else "%.1f") % self.speed, CYAN), (" │ ", GRAY),
                     ("%d PARSECS" % self.log["parsecs"], PURPLE), (" │ ", GRAY), mode]
            rw = sum(len(t) for t, _ in right)
            if W - rw - 2 > x + 2:
                self.segs(cv, W - rw - 2, 0, right)
            keys = "click:hail/fire space:lightspeed ←↑↓→:steer +/-:throttle c:chewie b:roll h:hail j:log z:zen ?:help q:quit"
            parts = []
            for kv in keys.split():
                k, v = kv.split(":")
                parts += [(" " + k, RED if k in ("click", "q") else AMBER), (" " + v + " ", GRAY)]
            self.segs(cv, 0, H - 1, parts)

        v = self.comms.view()                                           # 通讯字幕
        if v:
            who, text, col, a = v
            parts = [("~ " + text + " ~", mix(BG, SPK["~"], a))] if who == "~" else \
                [(who, mix(BG, col, a)), ("  ", None), (text, mix(BG, (215, 220, 228), a))]
            width = sum(len(t) for t, _ in parts)
            x0 = max(2, int(self.cx - width / 2)) if self.zen else 3
            self.segs(cv, x0 - 1, H - 2 if self.zen else H - 3, [(" ", None)] + parts + [(" ", None)], HUD_BG)

        if self.banner_t0 is not None and st != "hyper":                # 抵达横幅
            bt = self.sys_t - self.banner_t0
            if 0 <= bt < 6.0:
                a = min(1.0, bt / 0.8) * clamp((6.0 - bt) / 1.5, 0, 1)
                name, sub, y = " ".join(self.sys["name"]), self.sys["sub"], int(H * 0.2)
                cv.text(int(self.cx - len(name) / 2), y, name, mix(BG, AMBER, a))
                cv.text(int(self.cx - len(sub) / 2), y + 2, sub, mix(BG, FG, a * 0.8))

        if self.show_help:
            self.draw_help(cv)
        elif self.show_log:
            self.draw_log(cv)

    def box(self, cv, title, lines):
        inner = max([sum(len(t) for t, _ in l) for l in lines] + [len(title) + 4])
        bw, bh = inner + 6, len(lines) + 4
        x0, y0 = (self.W - bw) // 2, max(0, (self.H - bh) // 2)
        for y in range(y0, min(self.H, y0 + bh)):
            edge = "┌┐" if y == y0 else "└┘" if y == y0 + bh - 1 else "││"
            fill = "─" if y in (y0, y0 + bh - 1) else " "
            cv.text(x0, y, edge[0] + fill * (bw - 2) + edge[1], (70, 76, 92), (11, 13, 24))
        cv.text(x0 + 3, y0, " %s " % title, AMBER)
        for i, l in enumerate(lines):
            self.segs(cv, x0 + 3, y0 + 2 + i, l)

    def draw_help(self, cv):
        rows = [("mouse", "look around · push to the edge to steer"),
                ("click", "on a ship: hail it   ·   on empty space: fire"), ("right-click", "fire the quad cannons"),
                ("←↑↓→", "steer"), ("wheel  + -", "throttle"), ("space", "punch it to lightspeed"),
                ("h  c  b", "hail nearest · talk to Chewie · barrel roll"),
                ("a  z  v  j", "autopilot · zen mode · cockpit frame · flight log"), ("?  q", "this help · quit")]
        lines = [[("a quiet flight through a galaxy far, far away", GRAY)], []]
        lines += [[("  " + k.ljust(13), CYAN), (v, FG)] for k, v in rows]
        lines += [[], [("no score. no game over. leave her be and she flies herself.", GRAY)],
                  [("in zen mode she burns, wanders and jumps on her own.", GRAY)], [], [("press any key", AMBER)]]
        self.box(cv, "MILLENNIUM FALCON", lines)

    def draw_log(self, cv):
        L, k, t = self.log, GRAY, FG
        secs = int(time.monotonic() - L["start"])
        lines = [[("time aloft     ", k), ("%dm %02ds" % divmod(secs, 60), t)],
                 [("jumps          ", k), (str(L["jumps"]), t)],
                 [("distance       ", k), ("%d parsecs " % L["parsecs"], t), ("(or so Han claims)", k)],
                 [("hails · shots  ", k), ("%d · %d " % (L["hails"], L["shots"]), t), ("(nobody got hurt)", k)],
                 [("rocks dusted   ", k), (str(L["rocks"]), t)], [], [("systems visited", AMBER)]]
        row = "  "
        for n, c in L["systems"].items():
            n = n.title() + (" ×%d" % c if c > 1 else "")
            if len(row) + len(n) > 54:
                lines.append([(row, t)])
                row = "  "
            row += n + "   "
        lines += [[(row, t)], [], [("ships sighted", AMBER)]]
        for kind, d in SHIPS.items():
            if kind != "asteroid":
                n = L["ships"].get(kind, 0)
                lines.append([("  " + d["name"].ljust(24, "."), k), (" %d" % n, GREEN)] if n else
                             [("  " + "?" * len(d["name"]), (55, 60, 72))])
        lines += [[], [("j / esc to close", GRAY)]]
        self.box(cv, "FLIGHT LOG", lines)


# ------------------------------------------------------------- 入口：设置终端，退出时完全复原
def main():
    ap = argparse.ArgumentParser(prog="drivingfalcon",
                                 description="Fly the Millennium Falcon through a quiet terminal galaxy. "
                                             "A non-commercial fan project.")
    ap.add_argument("--version", action="version", version="%(prog)s " + __version__)
    ap.add_argument("--zen", action="store_true", help="start in zen mode with autopilot on")
    ap.add_argument("--no-cockpit", action="store_true", help="hide the cockpit frame")
    ap.add_argument("--stats", action="store_true", help="print average frame time on exit")
    args = ap.parse_args()
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return print("drivingfalcon needs a real terminal.")
    fd, out, game = sys.stdin.fileno(), sys.stdout, None
    old = termios.tcgetattr(fd)

    def _term(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGHUP, _term)
    try:
        tty.setcbreak(fd)
        # 备用屏幕、隐藏光标、关闭自动换行、开启 SGR 鼠标全量追踪
        out.write("\033[?1049h\033[?25l\033[?7l\033[?1000h\033[?1003h\033[?1006h\033[0m\033[2J")
        out.flush()
        game = Game(fd, args)
        game.run()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        out.write("\033[?1003l\033[?1006l\033[?1000l\033[?7h\033[0m\033[2J\033[H\033[?1049l\033[?25h")
        out.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    if game and game.stats:
        st = sorted(game.stats)
        print("frames %d · avg %.1f ms · p95 %.1f ms" % (len(st), 1000 * sum(st) / len(st), 1000 * st[int(len(st) * 0.95)]))


if __name__ == "__main__":
    main()

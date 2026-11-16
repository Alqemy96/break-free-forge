"""Known-answer serials for CodecModule.health(). Real community-database serials, hard-coded.

Each row: (label, serial, level, category_id, seed, parts_string). The expected values were taken
from the legacy codec (the parity oracle) when this module was written. This file holds data only:
health() never opens a file.
"""
from __future__ import annotations

KNOWN_SERIALS = (
    ('pistol',
     '@UgbV{rFme!K<~2}HRG}7?s6*{UokOKVwL^7k4(b-FB?1',
     50, 3, 1651,
     '3, 0, 1, 50| 2, 1651|| {78} {2} {5} {4} {3} {77} {51} {52} {54} {14} {25} {43} {70}|'),
    ('shotgun',
     '@Ugd77*Fme##(obkKs!)wO)R3V_%/yLKg+bLpwL;ZGokIW',
     50, 7, 319,
     '7, 0, 1, 50| 2, 319|| {97} {2} {6} {3} {1:12} {8} {73} {71} {16} {26} {38} {42} {51}|'),
    ('class mod (list part)',
     '@Ug!pHG2}TYgTyhDeLv?D7LB%zwlBrUu5~<RtlBn9zoJ;}',
     50, 254, 302,
     '254, 0, 1, 50| 2, 302|| {52} {14} {281} {344} {194} {162} {130} {98} {66} {234:[7 67]}|'),
    ('repair kit (list + int parts)',
     '@Ugr$N8m/)}}!X^07q8@cV8f`KSHR^n$0R',
     50, 261, 496,
     '261, 0, 1, 50| 2, 496|| {5} {7} {243:[106 99]} {6} {243:97}|'),
    ('gadget',
     '@Ugr$WBm/)}}!qB{+Obu#%Z$Os-',
     50, 267, 2964,
     '267, 0, 1, 50| 2, 2964|| {12} {1} {245:23} {11}|'),
    ('assault rifle (string tokens)',
     '@Ugfs(8Fme!KqDF8mh(Y2vD0PkBZTJ^f`?AaDvYQ;1=fCE(d`?fd;qvl)o_@O<RH9cw3=+RVsS6&K)4$@dTwZ2>VX?0{EuYiVZMeKVpQqpMGBv3=s8py{s9&gcsDB6',
     50, 13, 2209,
     '13, 0, 1, 50| 2, 2209|| "DAD_AR.comp_05_legendary_firstimpression" {1} {4} "DAD_AR.part_barrel_01_firstimpression" {12} {9} {25} {36} {38} {47} {53} {63}|'),
)

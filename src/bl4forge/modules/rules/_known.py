"""Known-answer serials for `health()`. They are constants so the module needs no file access.

Each was taken from, or built on, a real database serial; `tests/modules/test_rules.py` re-derives
every expectation from the data and the legacy oracle, so a stale constant fails loudly.
"""
from __future__ import annotations

# (label, serial, note). The pack facts are checked against part_meta at run time.
BASE_SERIAL = '@UgbV{rFme!KC@oM=RG}7?s74)XC+Zw39jYCwQ*%(aP~#8'          # Jakobs Pistol, Legendary Phantom Flame: base game only, structurally sound
STORY_PACK_SERIAL = '@UgbV{rFme!KC@oM=RG}7?s74)XC+Zw39jYCwQ*%(aP~%W(5d'    # the same pistol with Shoals' barrel (3:84, tagged story_pack_1) added
STORY_PACK_REF = (3, 84)
STORY_PACK = "story_pack_1"
BOUNTY_SERIAL = '@UgwSAs2}TYg%#;echw6t)RHGJksG&oJ8q}xGpxU77pjM$$p<*Eb'        # real database item "Frangible": base-game name, Raiden barrel (20:59) from bounty_pack_3
BOUNTY_REF = (20, 59)
BOUNTY_PACK = "bounty_pack_3"
TWO_COMPS_SERIAL = '@UgbV{rFme!KC@oM=RG}7?s74)XC+Zw39jYCwQ*%(aP~%Xg5d'     # BASE_SERIAL + an Epic composition part: a non-pearl with two, must be flagged
PEARL_TWO_COMPS_SERIAL = '@Ugy>*^2}TYg%%uv-i7M2g5)~7bsZQ-dtwPm8%/g9H?L(zS00'   # Order Sniper (Legendary) + comp_05_legendary_temper, which part_meta tags Pearl
KIT_SERIAL = '@Ugr$TAm/)}}!X=bYq8@cVnrl)`@(3=80RR'       # Jakobs Repair Kit carrying list parts {243:[...]}

"""The look of the code sheet, kept apart from the logic so a later web-UI phase can restyle it.

CSS is ONE module-level constant. The first block is the legacy forge sheet, verbatim (the sheet
is in daily use); the last three rules (.warn, .empty) are additive and only style content the
legacy sheet never showed (item warnings, an empty loadout).

Everything here is a constant: no state, no logic.
"""
from __future__ import annotations

from typing import Dict

# Vocab element name -> the CSS class of the badge. The class names are the legacy ones
# (radiation -> "rad", corrosive -> "corr"). Labels come from core.vocab.ELEMENT_LABELS, never from here.
ELEMENT_CSS_CLASS: Dict[str, str] = {
    "cryo": "cryo",
    "fire": "fire",
    "radiation": "rad",
    "shock": "shock",
    "corrosive": "corr",
    "impact": "impact",
}

CSS = """
:root{--bg:#0a1420;--panel:#101d2e;--raised:#142438;--border:#1f3650;
--ice:#7fd8f0;--ice-b:#bdf0ff;--ice-d:#4a7f96;--rad:#a8e05f;--shock:#c99bff;
--corr:#8fe07f;--fire:#e8935a;--impact:#d7c48a;--text:#dce8f0;--dim:#8fa3b5;
--faint:#5c7286;--good:#7fd8a8;--warn:#e0a25f;
--serif:Georgia,'Iowan Old Style','Palatino Linotype',serif;
--mono:'SF Mono','Cascadia Code',Consolas,monospace;}
*{box-sizing:border-box;}html,body{margin:0;padding:0;}
body{background:radial-gradient(ellipse 900px 500px at 15% -10%,rgba(127,216,240,.09),transparent 60%),var(--bg);
color:var(--text);font-family:var(--serif);line-height:1.55;padding:0 0 80px;}
.wrap{max-width:900px;margin:0 auto;padding:0 24px;}
header.hero{padding:48px 24px 32px;border-bottom:1px solid var(--border);}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--ice-d);margin:0 0 8px;}
h1{font-size:clamp(26px,4.5vw,38px);margin:0 0 8px;color:var(--ice-b);font-weight:600;}
.subtitle{font-size:15px;color:var(--dim);margin:0;max-width:66ch;}
.tldr{margin-top:20px;padding:15px 18px;background:var(--panel);border:1px solid var(--border);
border-left:3px solid var(--ice);border-radius:4px;font-size:14.5px;}
.tldr strong{color:var(--ice-b);}
section{padding:30px 24px;border-bottom:1px solid var(--border);}
h2{font-size:13px;font-family:var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--ice-d);margin:0 0 16px;font-weight:600;}
.card{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:15px 17px;margin-bottom:13px;}
.chead{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;}
.cname{font-size:18px;color:var(--ice-b);font-weight:600;}
.ctype{font-family:var(--mono);font-size:11px;color:var(--faint);text-transform:uppercase;letter-spacing:.05em;}
.cnote{font-size:13.5px;color:var(--dim);margin:7px 0 11px;}
.badge{font-family:var(--mono);font-size:10.5px;padding:2px 9px;border-radius:20px;text-transform:uppercase;letter-spacing:.05em;margin-left:6px;}
.badge.cryo{color:var(--ice-b);background:rgba(127,216,240,.14);border:1px solid var(--ice-d);}
.badge.rad{color:var(--rad);background:rgba(168,224,95,.12);border:1px solid rgba(168,224,95,.4);}
.badge.shock{color:var(--shock);background:rgba(201,155,255,.12);border:1px solid rgba(201,155,255,.4);}
.badge.corr{color:var(--corr);background:rgba(143,224,127,.12);border:1px solid rgba(143,224,127,.4);}
.badge.fire{color:var(--fire);background:rgba(232,147,90,.12);border:1px solid rgba(232,147,90,.4);}
.badge.impact{color:var(--impact);background:rgba(215,196,138,.1);border:1px solid rgba(215,196,138,.35);}
.serialrow{display:flex;gap:10px;align-items:stretch;background:var(--raised);border:1px solid var(--border);border-radius:6px;padding:8px 8px 8px 12px;}
.serial{font-family:var(--mono);font-size:12px;color:var(--good);word-break:break-all;flex:1;padding:4px 0;user-select:all;}
.copy{flex-shrink:0;font-family:var(--mono);font-size:12px;color:var(--ice);background:rgba(127,216,240,.1);
border:1px solid var(--ice-d);border-radius:5px;padding:4px 14px;cursor:pointer;transition:.15s;}
.copy:hover{background:rgba(127,216,240,.22);color:var(--ice-b);}
.copy.done{color:var(--good);border-color:var(--good);background:rgba(127,216,168,.15);}
.steps{counter-reset:s;display:flex;flex-direction:column;gap:8px;}
.step{display:grid;grid-template-columns:26px 1fr;gap:12px;font-size:13.5px;color:var(--dim);align-items:start;}
.step .n{counter-increment:s;width:24px;height:24px;border-radius:50%;background:rgba(127,216,240,.12);
border:1px solid var(--ice-d);display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:12px;color:var(--ice);}
.step .n::before{content:counter(s);}.step b{color:var(--text);}
footer{padding:26px 24px 0;text-align:center;color:var(--faint);font-size:12px;font-family:var(--mono);}
.odds{font-family:var(--mono);font-size:11.5px;color:var(--warn);margin:0 0 9px;letter-spacing:.01em;}
details.parts{margin:0 0 10px;}
details.parts summary{font-family:var(--mono);font-size:11px;color:var(--faint);cursor:pointer;
text-transform:uppercase;letter-spacing:.05em;}
details.parts summary:hover{color:var(--ice-d);}
details.parts p{font-size:12.5px;color:var(--dim);margin:7px 0 0;line-height:1.7;}
.warn{font-family:var(--mono);font-size:11.5px;color:var(--warn);margin:0 0 9px;line-height:1.5;}
.warn b{text-transform:uppercase;letter-spacing:.05em;font-weight:600;}
.empty{font-size:14px;color:var(--dim);margin:0;}
"""

COPY_JS = """
function cp(b){var s=b.getAttribute('data-s');var d=function(){var o=b.textContent;b.textContent='Copied';b.classList.add('done');setTimeout(function(){b.textContent=o;b.classList.remove('done');},1400);};
if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(s).then(d).catch(function(){fb(s,d);});}else{fb(s,d);}}
function fb(s,d){var t=document.createElement('textarea');t.value=s;t.style.position='fixed';t.style.opacity='0';document.body.appendChild(t);t.select();try{document.execCommand('copy');d();}catch(e){}document.body.removeChild(t);}
"""

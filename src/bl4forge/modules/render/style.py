"""The look of the code sheet, kept apart from the logic.

CSS is ONE module-level constant. It carries the Break Free Forge look (near-black, vault yellow,
cyan and pink accents, stencil headings, mono serials, hazard stripes). The class names are the
legacy ones. Nothing is fetched: the named fonts (Saira Stencil One etc.) are only used when
already installed, otherwise the stacks fall back to system stencil-ish/condensed faces.

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
:root{--bg:#07080b;--panel:#0f1116;--raised:#171a22;--border:#3a3f4c;
--cream:#efe5c8;--dim:#b9b5a6;--faint:#9b9889;--hazard:#ffe03d;--hazard-ink:#15110a;
--cyan:#35e8d4;--pink:#ff3d8b;--good:#9fe7c0;--warn:#ffb627;
--cryo:#5ce1ff;--fire:#ff8a6b;--rad:#5bff7a;--shock:#9db0ff;--corr:#c8f53a;--impact:#a7b1be;
--display:'Saira Stencil One',Impact,'Arial Narrow Bold','Arial Narrow',sans-serif;
--cond:'Barlow Condensed','Arial Narrow',Impact,sans-serif;
--sans:'Barlow',system-ui,-apple-system,'Segoe UI',sans-serif;
--mono:'JetBrains Mono',ui-monospace,'Cascadia Code',Consolas,monospace;}
*{box-sizing:border-box;}html,body{margin:0;padding:0;}
body{background:radial-gradient(circle,rgba(53,232,212,.11) 1.3px,transparent 1.8px) 0 0/10px 10px,var(--bg);
color:var(--cream);font-family:var(--sans);line-height:1.5;padding:0 0 80px;font-synthesis:none;}
::selection{background:rgba(255,224,61,.4);color:#fff;}
.wrap{max-width:900px;margin:0 auto;padding:0 24px;}
header.hero{padding:0 24px 32px;border-bottom:4px solid var(--hazard);}
header.hero::before{content:"";display:block;height:14px;margin:0 -24px 36px;
background:repeating-linear-gradient(-45deg,var(--hazard) 0 14px,#000 14px 28px);}
header.hero .wrap{padding:0;}
.eyebrow{display:inline-block;font-family:var(--mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;
color:#000;background:var(--cyan);padding:3px 10px;margin:0 0 12px;transform:rotate(-1deg);box-shadow:3px 3px 0 var(--pink);}
h1{font-family:var(--display);font-weight:400;font-size:clamp(30px,6vw,54px);line-height:1.05;margin:0 0 10px;
color:var(--hazard);text-transform:uppercase;letter-spacing:.01em;text-shadow:3px 3px 0 #000,-2px 0 0 rgba(255,61,139,.75);}
.subtitle{font-size:15px;color:var(--dim);margin:0;max-width:66ch;}
.tldr{margin-top:22px;padding:15px 18px;background:var(--panel);border:2px solid #000;
border-left:6px solid var(--pink);font-size:14.5px;box-shadow:5px 5px 0 #000;}
.tldr strong{color:var(--hazard);font-weight:600;}
section{padding:30px 24px;border-bottom:1px solid var(--border);}
h2{display:inline-block;font-family:var(--display);font-weight:400;font-size:16px;letter-spacing:.08em;text-transform:uppercase;
color:var(--hazard-ink);background:var(--hazard);padding:3px 12px;margin:0 0 18px;transform:skew(-6deg);box-shadow:3px 3px 0 #000;}
.card{background:repeating-linear-gradient(0deg,rgba(255,255,255,.028) 0 1px,transparent 1px 3px),var(--panel);
border:2px solid #000;border-left:5px solid var(--cyan);padding:15px 17px;margin-bottom:16px;box-shadow:5px 5px 0 #000;}
.chead{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;}
.cname{font-family:var(--cond);font-size:23px;line-height:1.15;color:var(--cream);font-weight:700;text-transform:uppercase;letter-spacing:.02em;}
.ctype{font-family:var(--mono);font-size:11px;color:var(--faint);text-transform:uppercase;letter-spacing:.05em;}
.cnote{font-size:13.5px;color:var(--dim);margin:7px 0 11px;}
.cnote em{color:var(--pink);font-style:normal;font-weight:600;}
.badge{font-family:var(--mono);font-size:10.5px;padding:2px 9px;border-radius:0;text-transform:uppercase;letter-spacing:.06em;margin-left:6px;
color:var(--cream);background:rgba(167,177,190,.1);border:1px solid var(--impact);}
.badge.cryo{color:var(--cryo);background:rgba(92,225,255,.12);border:1px solid var(--cryo);}
.badge.rad{color:var(--rad);background:rgba(91,255,122,.12);border:1px solid var(--rad);}
.badge.shock{color:var(--shock);background:rgba(157,176,255,.12);border:1px solid var(--shock);}
.badge.corr{color:var(--corr);background:rgba(200,245,58,.12);border:1px solid var(--corr);}
.badge.fire{color:var(--fire);background:rgba(255,138,107,.12);border:1px solid var(--fire);}
.badge.impact{color:var(--impact);background:rgba(167,177,190,.12);border:1px solid var(--impact);}
.serialrow{display:flex;gap:10px;align-items:stretch;background:#000;border:1px solid var(--border);padding:8px 8px 8px 12px;}
.serial{font-family:var(--mono);font-size:12px;color:var(--good);word-break:break-all;flex:1;padding:4px 0;user-select:all;}
.copy{flex-shrink:0;font-family:var(--cond);font-weight:700;font-size:14px;letter-spacing:.08em;text-transform:uppercase;
color:var(--hazard-ink);background:var(--hazard);border:2px solid #000;padding:4px 16px;cursor:pointer;box-shadow:3px 3px 0 #000;transition:.12s;}
.copy:hover{background:#fff07a;transform:translate(-1px,-1px);}
.copy:focus-visible{outline:3px solid var(--cyan);outline-offset:2px;}
.copy.done{color:#000;background:var(--good);}
.steps{counter-reset:s;display:flex;flex-direction:column;gap:10px;}
.step{display:grid;grid-template-columns:28px 1fr;gap:12px;font-size:13.5px;color:var(--dim);align-items:start;}
.step .n{counter-increment:s;width:26px;height:26px;background:var(--pink);color:#000;border:2px solid #000;
display:flex;align-items:center;justify-content:center;font-family:var(--display);font-size:13px;transform:rotate(-4deg);}
.step .n::before{content:counter(s);}.step b{color:var(--cream);}
footer{padding:26px 24px 0;text-align:center;color:var(--faint);font-size:12px;font-family:var(--mono);}
footer::before{content:"";display:block;height:8px;margin:0 0 18px;
background:repeating-linear-gradient(-45deg,var(--hazard) 0 10px,#000 10px 20px);}
.odds{font-family:var(--mono);font-size:11.5px;color:var(--warn);margin:0 0 9px;letter-spacing:.01em;}
details.parts{margin:0 0 10px;}
details.parts summary{font-family:var(--mono);font-size:11px;color:var(--faint);cursor:pointer;
text-transform:uppercase;letter-spacing:.05em;}
details.parts summary:hover{color:var(--cyan);}
details.parts p{font-size:12.5px;color:var(--dim);margin:7px 0 0;line-height:1.7;}
.warn{font-family:var(--mono);font-size:11.5px;color:var(--pink);margin:0 0 9px;line-height:1.5;}
.warn b{text-transform:uppercase;letter-spacing:.05em;font-weight:600;}
.empty{font-size:14px;color:var(--dim);margin:0;}
@media (max-width:520px){.serialrow{flex-direction:column;}.copy{padding:8px 16px;}}
"""

COPY_JS = """
function cp(b){var s=b.getAttribute('data-s');var d=function(){var o=b.textContent;b.textContent='Copied';b.classList.add('done');setTimeout(function(){b.textContent=o;b.classList.remove('done');},1400);};
if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(s).then(d).catch(function(){fb(s,d);});}else{fb(s,d);}}
function fb(s,d){var t=document.createElement('textarea');t.value=s;t.style.position='fixed';t.style.opacity='0';document.body.appendChild(t);t.select();try{document.execCommand('copy');d();}catch(e){}document.body.removeChild(t);}
"""

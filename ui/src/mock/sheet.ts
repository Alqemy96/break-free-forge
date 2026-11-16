/** A small stand-in for the render module's sheet (mock mode only), with copy buttons + script. */
import type { Loadout } from '@/api/types'

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] ?? c)

export function renderMockSheet(lo: Loadout): string {
  const sections = lo.groups
    .map((g) => {
      const cards = lo.items
        .filter((it) => it.group === g)
        .map(
          (it) => `<div class="card"><div class="chead"><span class="cname">${esc(it.shown_name)}</span>
<span class="ctype">${esc(it.category ?? it.label)} · ${esc(it.rarity)} · Lv ${it.level ?? '?'}</span></div>
${it.note ? `<p class="cnote">${it.note}</p>` : ''}<p class="odds">${esc(it.odds)}</p>
<div class="serialrow"><span class="serial">${esc(it.serial)}</span><button class="copy" data-code="${esc(it.serial)}">Copy</button></div></div>`,
        )
        .join('\n')
      return `<section><h2>${esc(g)}</h2>${cards}</section>`
    })
    .join('\n')
  return `<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>${esc(lo.title)}</title>
<style>body{margin:0;background:#0a1420;color:#dce8f0;font-family:Georgia,serif;padding:32px}
h1{color:#bdf0ff;margin:0 0 6px}h2{font:600 13px monospace;letter-spacing:.08em;text-transform:uppercase;color:#4a7f96}
.card{background:#101d2e;border:1px solid #1f3650;border-radius:8px;padding:14px 16px;margin:0 0 12px}
.chead{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}.cname{font-size:18px;color:#bdf0ff}
.ctype{font:11px monospace;color:#5c7286;text-transform:uppercase}.odds{font:11.5px monospace;color:#e0a25f}
.cnote{color:#8fa3b5}.serialrow{display:flex;gap:10px;background:#142438;border:1px solid #1f3650;border-radius:6px;padding:8px}
.serial{font:12px monospace;color:#7fd8a8;word-break:break-all;flex:1}
.copy{font:12px monospace;color:#7fd8f0;background:transparent;border:1px solid #4a7f96;border-radius:5px;cursor:pointer}
.copy.done{color:#7fd8a8;border-color:#7fd8a8}</style></head><body>
<p style="font:12px monospace;color:#4a7f96">MOCK SHEET · not the render module's output</p><h1>${esc(lo.title)}</h1>
${sections}
<script>document.querySelectorAll('.copy').forEach(function(b){b.addEventListener('click',function(){
var t=b.getAttribute('data-code');var done=function(){b.textContent='Copied';b.classList.add('done');setTimeout(function(){b.textContent='Copy';b.classList.remove('done')},1400)};
if(navigator.clipboard){navigator.clipboard.writeText(t).then(done,function(){})}});});</script></body></html>`
}

export function renderMockText(lo: Loadout): string {
  const lines = [lo.title, '='.repeat(lo.title.length), '']
  if (lo.level !== null) lines.push(`All codes re-leveled to ${lo.level}.`, '')
  for (const g of lo.groups) {
    lines.push(`[${g}]`)
    for (const it of lo.items.filter((i) => i.group === g)) {
      lines.push(`${it.shown_name}${it.element ? `  (${it.element[0]?.toUpperCase()}${it.element.slice(1)})` : ''}`, it.serial, '')
    }
  }
  return lines.join('\n')
}

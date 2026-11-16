/** SVG filter used by `.ink-edge` (brush-ink borders). Rendered once at the app root. */
export function InkDefs() {
  return (
    <svg width="0" height="0" className="pointer-events-none absolute" aria-hidden focusable="false">
      <defs>
        <filter id="bf-rough" x="-5%" y="-5%" width="110%" height="110%">
          <feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="3" seed="4" result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale="5" />
        </filter>
      </defs>
    </svg>
  )
}

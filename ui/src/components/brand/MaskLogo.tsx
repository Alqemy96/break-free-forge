import { useId } from 'react'

/**
 * The mark: a blank, cracked visor mask under a hood. Original artwork (plain shapes only):
 * no real group's logo and no real mask design. Decorative unless `title` is given.
 */
export function MaskLogo({ className, title }: { className?: string; title?: string }) {
  const id = useId()
  return (
    <svg viewBox="0 0 64 64" className={className} role={title ? 'img' : undefined} aria-hidden={title ? undefined : true} aria-labelledby={title ? id : undefined}>
      {title ? <title id={id}>{title}</title> : null}
      <path d="M5 63C3 30 15 4 32 4s29 26 27 59z" fill="#0a0b10" stroke="#35e8d4" strokeWidth="2.5" strokeLinejoin="round" />
      <ellipse cx="32" cy="35" rx="15" ry="20" fill="#efe5c8" stroke="#000" strokeWidth="3" />
      <path d="M23 31.5l8 1.4v3.6l-8-1.4zM41 31.5l-8 1.4v3.6l8-1.4z" fill="#000" />
      <path d="M31 16l4 8-5 6 4 9-3 7" fill="none" stroke="#000" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
      <rect x="42" y="20" width="9" height="3" fill="#ff3d8b" />
      <rect x="12" y="44" width="8" height="2.5" fill="#35e8d4" />
      <rect x="46" y="48" width="6" height="2.5" fill="#ffe03d" />
    </svg>
  )
}

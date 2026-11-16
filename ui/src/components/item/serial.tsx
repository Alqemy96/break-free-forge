import { truncateSerial } from '@/lib/format'
import { cn } from '@/lib/utils'

/** A serial in the mono face; truncated form keeps both ends, the full code is in the title. */
export function SerialText({ serial, full = false, className }: { serial: string; full?: boolean; className?: string }) {
  return (
    <code
      title={full ? undefined : serial}
      className={cn('font-mono text-[12.5px] text-serial', full ? 'break-all select-all' : 'whitespace-nowrap', className)}
    >
      {full ? serial : truncateSerial(serial)}
    </code>
  )
}

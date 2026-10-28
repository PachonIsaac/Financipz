import { COLOR_CHOICES, ICON_CHOICES, ICONS } from '../appearance'

/** Color and icon of a category, each as a group of options. Both are optional: empty means "guess it". */
export function AppearancePicker({
  icon,
  color,
  onIcon,
  onColor,
}: {
  icon: string
  color: string
  onIcon: (key: string) => void
  onColor: (color: string) => void
}) {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <p id="color-label" className="mb-2 text-sm font-medium text-slate-300">
          Color
        </p>
        <div role="radiogroup" aria-labelledby="color-label" className="flex flex-wrap gap-3">
          {COLOR_CHOICES.map((choice) => (
            <button
              key={choice.color}
              type="button"
              role="radio"
              aria-checked={color === choice.color}
              aria-label={choice.label}
              onClick={() => onColor(choice.color)}
              className={`size-11 rounded-full border-[3px] ${color === choice.color ? 'border-slate-50' : 'border-transparent'}`}
              style={{ background: choice.color }}
            />
          ))}
        </div>
      </div>
      <div>
        <p id="icon-label" className="mb-2 text-sm font-medium text-slate-300">
          Icono
        </p>
        <div role="radiogroup" aria-labelledby="icon-label" className="grid grid-cols-5 gap-2">
          {ICON_CHOICES.map((choice) => {
            const Icon = ICONS[choice.key]
            if (!Icon) return null
            const selected = icon === choice.key
            return (
              <button
                key={choice.key}
                type="button"
                role="radio"
                aria-checked={selected}
                aria-label={choice.label}
                onClick={() => onIcon(choice.key)}
                className={`flex h-12 items-center justify-center rounded-2xl border ${selected ? 'border-emerald-500 bg-emerald-500/10' : 'border-slate-800 bg-slate-800'}`}
              >
                <Icon aria-hidden="true" size={22} strokeWidth={1.75} color={selected ? (color || '#ff8a3d') : '#f5f5f7'} />
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

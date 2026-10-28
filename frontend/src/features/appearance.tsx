// How categories and accounts look: an icon and a color. A category can carry its own `icon` and `color`;
// when it does not, they are guessed from its name so the lists are never plain.
import {
  ArrowLeftRight,
  Banknote,
  Briefcase,
  Car,
  Coins,
  CreditCard,
  Ellipsis,
  Gift,
  GraduationCap,
  HeartPulse,
  House,
  Landmark,
  type LucideIcon,
  PawPrint,
  Percent,
  PiggyBank,
  Plane,
  Receipt,
  Repeat,
  Shirt,
  ShoppingCart,
  Smartphone,
  Sparkles,
  Ticket,
  Undo2,
  Utensils,
  Wallet,
  Zap,
} from 'lucide-react'
import type { AccountType, Category, CategoryType } from '../api/types'

export const TONES = {
  orange: '#ff8a3d',
  blue: '#5b9ef0',
  aqua: '#3cc49c',
  violet: '#a98bea',
  gold: '#d4a72c',
  pink: '#e879a6',
  green: '#4ade80',
  gray: '#a6a6ad',
} as const

export interface Look {
  Icon: LucideIcon
  color: string
}

export const ICONS: Record<string, LucideIcon> = {
  'shopping-cart': ShoppingCart,
  utensils: Utensils,
  car: Car,
  house: House,
  zap: Zap,
  'heart-pulse': HeartPulse,
  ticket: Ticket,
  'graduation-cap': GraduationCap,
  shirt: Shirt,
  repeat: Repeat,
  'paw-print': PawPrint,
  gift: Gift,
  plane: Plane,
  smartphone: Smartphone,
  receipt: Receipt,
  ellipsis: Ellipsis,
  briefcase: Briefcase,
  sparkles: Sparkles,
  percent: Percent,
  undo: Undo2,
}

// The first rule whose words appear in the (accent-free, lowercase) name wins.
const NAME_RULES: { words: string[]; icon: string; tone: keyof typeof TONES }[] = [
  { words: ['mercado', 'super', 'market', 'tienda'], icon: 'shopping-cart', tone: 'orange' },
  { words: ['restaur', 'comida', 'almuerzo', 'cena', 'domicilio', 'cafe'], icon: 'utensils', tone: 'aqua' },
  { words: ['transporte', 'gasolina', 'taxi', 'uber', 'bus', 'parqueadero', 'peaje'], icon: 'car', tone: 'blue' },
  { words: ['vivienda', 'arriendo', 'casa', 'hogar'], icon: 'house', tone: 'violet' },
  { words: ['servicio', 'luz', 'agua', 'energia', 'internet', 'gas'], icon: 'zap', tone: 'gold' },
  { words: ['salud', 'medic', 'farmacia', 'doctor'], icon: 'heart-pulse', tone: 'pink' },
  { words: ['ocio', 'entreten', 'cine', 'diversion'], icon: 'ticket', tone: 'violet' },
  { words: ['educacion', 'curso', 'universidad', 'colegio'], icon: 'graduation-cap', tone: 'blue' },
  { words: ['ropa', 'vestuario'], icon: 'shirt', tone: 'pink' },
  { words: ['suscrip', 'netflix', 'spotify'], icon: 'repeat', tone: 'violet' },
  { words: ['mascota'], icon: 'paw-print', tone: 'gold' },
  { words: ['regalo'], icon: 'gift', tone: 'pink' },
  { words: ['viaje', 'vuelo', 'hotel', 'vacaciones'], icon: 'plane', tone: 'aqua' },
  { words: ['tecnolog', 'celular', 'electronic'], icon: 'smartphone', tone: 'blue' },
  { words: ['comision', 'impuesto', 'cuota de manejo'], icon: 'receipt', tone: 'gray' },
  { words: ['sueldo', 'salario', 'nomina'], icon: 'briefcase', tone: 'green' },
  { words: ['extra', 'freelance', 'honorarios'], icon: 'sparkles', tone: 'green' },
  { words: ['interes', 'rendimiento'], icon: 'percent', tone: 'green' },
  { words: ['reembolso', 'devolucion'], icon: 'undo', tone: 'green' },
]

function plain(text: string): string {
  return text.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()
}

const HEX = /^#[0-9a-fA-F]{6}$/

/** Icon and color for a category: its own when set, else guessed from the name, else a neutral dots icon. */
export function categoryLook(category: Pick<Category, 'name' | 'icon' | 'color' | 'type'> | undefined, fallback?: CategoryType): Look {
  if (!category) return { Icon: fallback === 'transfer' ? ArrowLeftRight : Ellipsis, color: TONES.gray }
  const guessed = NAME_RULES.find((rule) => rule.words.some((word) => plain(category.name).includes(word)))
  const Icon = (category.icon && ICONS[category.icon]) || (guessed && ICONS[guessed.icon]) || Ellipsis
  const color = category.color && HEX.test(category.color) ? category.color : guessed ? TONES[guessed.tone] : TONES.gray
  return { Icon, color }
}

const ACCOUNT_ICONS: Record<AccountType, LucideIcon> = {
  cash: Banknote,
  bank: Landmark,
  credit_card: CreditCard,
  savings: PiggyBank,
  wallet: Wallet,
  exchange: Coins,
  loan: ArrowLeftRight,
  system: Ellipsis,
}

export function accountIcon(type: AccountType): LucideIcon {
  return ACCOUNT_ICONS[type]
}

/** A rounded square with an icon, tinted with `color` (or neutral when none is given). */
export function IconChip({
  icon: Icon,
  color,
  size = 40,
}: {
  icon: LucideIcon
  color?: string | undefined
  size?: number
}) {
  const tinted = color !== undefined
  return (
    <span
      aria-hidden="true"
      className="flex shrink-0 items-center justify-center rounded-xl"
      style={{ width: size, height: size, background: tinted ? `${color}29` : '#1e1e21' }}
    >
      <Icon size={Math.round(size * 0.5)} strokeWidth={1.75} color={color ?? '#f5f5f7'} />
    </span>
  )
}

/** What the person picks when editing a category: icons by their stored key, and the palette colors. */
export const ICON_CHOICES: { key: string; label: string }[] = [
  { key: 'shopping-cart', label: 'Carrito' },
  { key: 'utensils', label: 'Cubiertos' },
  { key: 'car', label: 'Auto' },
  { key: 'house', label: 'Casa' },
  { key: 'zap', label: 'Rayo' },
  { key: 'heart-pulse', label: 'Salud' },
  { key: 'ticket', label: 'Entrada' },
  { key: 'graduation-cap', label: 'Educación' },
  { key: 'shirt', label: 'Ropa' },
  { key: 'repeat', label: 'Suscripción' },
  { key: 'paw-print', label: 'Mascota' },
  { key: 'gift', label: 'Regalo' },
  { key: 'plane', label: 'Viaje' },
  { key: 'smartphone', label: 'Tecnología' },
  { key: 'receipt', label: 'Recibo' },
  { key: 'briefcase', label: 'Trabajo' },
  { key: 'sparkles', label: 'Extra' },
  { key: 'percent', label: 'Intereses' },
  { key: 'undo', label: 'Reembolso' },
  { key: 'ellipsis', label: 'Otros' },
]

export const COLOR_CHOICES: { label: string; color: string }[] = [
  { label: 'Naranja', color: TONES.orange },
  { label: 'Azul', color: TONES.blue },
  { label: 'Turquesa', color: TONES.aqua },
  { label: 'Violeta', color: TONES.violet },
  { label: 'Dorado', color: TONES.gold },
  { label: 'Rosa', color: TONES.pink },
  { label: 'Verde', color: TONES.green },
  { label: 'Gris', color: TONES.gray },
]

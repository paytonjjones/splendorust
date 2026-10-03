import type { CSSProperties } from 'react';
import type { Card } from './types';

export const COLORS = ['white', 'blue', 'green', 'red', 'black', 'gold'] as const;
export const COLOR_NAMES = ['White', 'Blue', 'Green', 'Red', 'Black', 'Gold'];
export const colorStyle = (color: number) => ({ '--gem': `var(--${COLORS[color]})`, '--wash': `var(--${COLORS[color]}-wash)` }) as CSSProperties;

/** The raster sprite sheets are generated assets. No vector art is used. */
export function Gem({ color, className = '' }: { color: number; className?: string }) {
  const positions = ['0% 0%', '50% 0%', '100% 0%', '0% 100%', '50% 100%', '100% 100%'];
  return <span className={`gem ${className}`} style={{ ...colorStyle(color), backgroundPosition: positions[color] }} aria-hidden="true"/>;
}
export function Engraving({ card }: { card: Card }) {
  const positions = ['0% 0%', '50% 0%', '100% 0%', '0% 100%', '50% 100%', '100% 100%'];
  return <span className="engraving" style={{ backgroundPosition: positions[card.id % 6] }} aria-hidden="true"/>;
}
export function Seal({ variant = 0 }: { variant?: number }) {
  return <span className="seal" style={{ backgroundPosition: `${variant % 3 * 50}% 50%` }} aria-hidden="true"/>;
}
export function Icon({ name }: { name: 'bookmark' | 'close' | 'arrow' | 'help' | 'restart' }) {
  const labels = {bookmark: 'Reserve', close: 'Close', arrow: 'Continue', help: 'Help', restart: 'New game'};
  return <span className="text-icon" aria-hidden="true">{labels[name]}</span>;
}

export function cardLabel(card: Card, location: string) {
  return `${location}, tier ${card.tier}, ${card.points} prestige, ${COLOR_NAMES[card.bonus]} bonus. Cost: ${card.cost.map((n, c) => n ? `${n} ${COLOR_NAMES[c].toLowerCase()}` : '').filter(Boolean).join(', ') || 'free'}`;
}

export function Cost({ amounts, className = '' }: { amounts: number[]; className?: string }) {
  return <span className={`costs ${className}`}>{amounts.map((n, color) => n > 0 && <span className="cost" key={color} title={`${n} ${COLOR_NAMES[color]}`}><Gem color={color}/><span>{n}</span></span>)}</span>;
}

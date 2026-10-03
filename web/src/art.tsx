import type { CSSProperties } from 'react';
import type { Card } from './types';

export const COLORS = ['white', 'blue', 'green', 'red', 'black', 'gold'] as const;
export const COLOR_NAMES = ['White', 'Blue', 'Green', 'Red', 'Black', 'Gold'];
export const colorStyle = (color: number) => ({ '--gem': `var(--${COLORS[color]})`, '--wash': `var(--${COLORS[color]}-wash)` }) as CSSProperties;

type Crop = readonly [x: number, y: number, width: number, height: number];

// Bounds of the generated illustrations, including two pixels of edge padding.
// Equal atlas cells do not have equal transparent margins.
const GEM_CROPS: readonly Crop[] = [
  [24, 28, 106, 90], [146, 26, 93, 92], [267, 23, 88, 95],
  [30, 135, 93, 94], [150, 128, 84, 108], [261, 134, 99, 98],
];
const ENGRAVING_CROPS: readonly Crop[] = [
  [17, 70, 242, 166], [268, 44, 232, 194], [536, 66, 204, 171],
  [14, 275, 234, 193], [261, 286, 244, 180], [518, 301, 239, 165],
];
const SEAL_CROPS: readonly Crop[] = [[14, 6, 80, 80], [104, 6, 80, 80], [194, 6, 80, 80]];

function RasterInk({ crop, atlas }: { crop: Crop; atlas: readonly [number, number] }) {
  const [x, y, width, height] = crop;
  const [atlasWidth, atlasHeight] = atlas;
  const style = {
    '--sprite-ratio': width / height,
    backgroundSize: `${atlasWidth / width * 100}% ${atlasHeight / height * 100}%`,
    backgroundPosition: `${x / (atlasWidth - width) * 100}% ${y / (atlasHeight - height) * 100}%`,
  } as CSSProperties;
  return <span className="raster-ink" style={style}/>;
}

/** The raster sprite sheets are generated assets. No vector art is used. */
export function Gem({ color, className = '' }: { color: number; className?: string }) {
  return <span className={`gem ${className}`} style={colorStyle(color)} aria-hidden="true"><RasterInk crop={GEM_CROPS[color]} atlas={[384, 256]}/></span>;
}
export function Engraving({ card }: { card: Card }) {
  return <span className="engraving" aria-hidden="true"><RasterInk crop={ENGRAVING_CROPS[card.id % 6]} atlas={[768, 512]}/></span>;
}
export function Seal({ variant = 0 }: { variant?: number }) {
  return <span className="seal" aria-hidden="true"><RasterInk crop={SEAL_CROPS[variant % 3]} atlas={[288, 96]}/></span>;
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

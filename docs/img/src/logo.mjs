// Hand-drawn quokka logo (front view, sitting). Usage: cd docs/img/src && npm install && node logo.mjs  -> docs/logo.svg
import rough from 'roughjs';
import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'logo.svg');
const gen = rough.generator();
const parts = [];
let seed = 21;
const ink = '#3a2a1f';
const o = (x = {}) => ({ seed: seed++, roughness: 1.0, bowing: 0.7, stroke: ink, strokeWidth: 2.2, ...x });
const add = (d) => { for (const p of gen.toPaths(d)) parts.push(p); };
const fur = (fill, x = {}) => o({ fill, fillStyle: 'solid', ...x });
const FUR = '#9a8270', HEAD = '#a68c78', DARK = '#7a6352', PALE = '#e6d3b6';

// background badge
add(gen.rectangle(6, 6, 244, 244, o({ fill: '#f3e4c6', fillStyle: 'solid', stroke: '#c9b48f', strokeWidth: 2, roughness: 0.8 })));

// body: round, sitting
add(gen.path('M128 132 C168 132 196 168 196 206 C196 232 170 242 128 242 C86 242 60 232 60 206 C60 168 88 132 128 132 Z', fur(FUR)));
add(gen.ellipse(128, 202, 64, 74, fur(PALE, { strokeWidth: 1.2 })));
// long hind feet pointing forward
add(gen.ellipse(100, 238, 40, 16, fur(DARK)));
add(gen.ellipse(156, 238, 40, 16, fur(DARK)));
// little front paws held at the chest
add(gen.ellipse(112, 168, 20, 13, fur(DARK)));
add(gen.ellipse(144, 168, 20, 13, fur(DARK)));

// ears: small, round, high, tilted out
add(gen.ellipse(90, 52, 30, 36, fur(DARK, { roughness: 0.8 })));
add(gen.ellipse(166, 52, 30, 36, fur(DARK, { roughness: 0.8 })));
add(gen.ellipse(91, 55, 14, 20, fur('#d8a28d', { strokeWidth: 1 })));
add(gen.ellipse(165, 55, 14, 20, fur('#d8a28d', { strokeWidth: 1 })));
// head: round top, chubby cheeks low on the sides, small chin
add(gen.path('M128 46 C158 46 178 62 182 86 C196 96 198 122 186 134 C174 146 152 152 128 152 C104 152 82 146 70 134 C58 122 60 96 74 86 C78 62 98 46 128 46 Z', fur(HEAD)));
// pale chin only (no round muzzle disc)
add(gen.path('M108 134 C116 146 140 146 148 134 C142 140 114 140 108 134 Z', fur(PALE, { strokeWidth: 0.8, roughness: 0.5 })));
// big dark eyes set wide
add(gen.circle(98, 96, 22, fur('#1f1610', { strokeWidth: 1 })));
add(gen.circle(158, 96, 22, fur('#1f1610', { strokeWidth: 1 })));
add(gen.circle(102, 91, 7, o({ fill: '#ffffff', fillStyle: 'solid', stroke: '#ffffff', strokeWidth: 0.5, roughness: 0.3 })));
add(gen.circle(162, 91, 7, o({ fill: '#ffffff', fillStyle: 'solid', stroke: '#ffffff', strokeWidth: 0.5, roughness: 0.3 })));
// cheek blush
add(gen.ellipse(82, 122, 18, 10, o({ fill: '#e8968a', fillStyle: 'solid', stroke: 'none', roughness: 0.5 })));
add(gen.ellipse(174, 122, 18, 10, o({ fill: '#e8968a', fillStyle: 'solid', stroke: 'none', roughness: 0.5 })));
// wide nose
add(gen.path('M116 112 Q128 106 140 112 Q136 123 128 125 Q120 123 116 112 Z', fur('#1f1610', { strokeWidth: 1.2, roughness: 0.5 })));
// the quokka smile: corners curl up
add(gen.path('M128 125 L128 129', o({ strokeWidth: 2.4, roughness: 0.4 })));
add(gen.path('M108 126 Q110 138 128 129 Q146 138 148 126', o({ strokeWidth: 2.6, roughness: 0.5 })));

const body = parts.map((p) => `<path d="${p.d}" stroke="${p.stroke}" stroke-width="${p.strokeWidth}" fill="${p.fill || 'none'}" stroke-linecap="round" stroke-linejoin="round"/>`).join('\n  ');
writeFileSync(OUT, `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256" role="img" aria-label="nomess quokka">\n  ${body}\n</svg>\n`);
console.log('wrote', OUT);

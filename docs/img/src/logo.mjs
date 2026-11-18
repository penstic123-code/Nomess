// Hand-drawn quokka logo. Usage: cd docs/img/src && npm install && node logo.mjs  -> docs/logo.svg
import rough from 'roughjs';
import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'logo.svg');
const gen = rough.generator();
const parts = [];
let seed = 7;
const ink = '#3a2a1f';
const o = (x = {}) => ({ seed: seed++, roughness: 1.1, bowing: 0.8, stroke: ink, strokeWidth: 2.2, ...x });
const add = (d) => { for (const p of gen.toPaths(d)) parts.push(p); };
const fur = (fill, x = {}) => o({ fill, fillStyle: 'solid', ...x });

// background badge
add(gen.rectangle(6, 6, 244, 244, o({ fill: '#f3e4c6', fillStyle: 'solid', stroke: '#c9b48f', strokeWidth: 2, roughness: 0.8 })));

// tail peeking out on the right
add(gen.path('M168 214 C200 214 214 196 214 176', o({ strokeWidth: 9, stroke: '#7d6552', roughness: 0.8 })));
// body: round, sitting
add(gen.ellipse(128, 196, 118, 96, fur('#9c8470')));
// belly
add(gen.ellipse(128, 204, 70, 66, fur('#e3cfb2', { strokeWidth: 1.4 })));
// feet
add(gen.ellipse(100, 240, 34, 16, fur('#7d6552')));
add(gen.ellipse(156, 240, 34, 16, fur('#7d6552')));

// ears: small, round, on top
add(gen.circle(88, 62, 34, fur('#8a7260')));
add(gen.circle(168, 62, 34, fur('#8a7260')));
add(gen.circle(89, 64, 17, fur('#d9a690', { strokeWidth: 1.2 })));
add(gen.circle(167, 64, 17, fur('#d9a690', { strokeWidth: 1.2 })));

// head: wide chubby cheeks
add(gen.path('M128 52 C170 52 196 78 196 110 C196 140 168 160 128 160 C88 160 60 140 60 110 C60 78 86 52 128 52 Z', fur('#a88f7a')));
// pale face / muzzle
add(gen.ellipse(128, 128, 64, 46, fur('#ead8bd', { strokeWidth: 1.4 })));

// eyes
add(gen.circle(100, 104, 12, fur('#1f1610', { strokeWidth: 1 })));
add(gen.circle(156, 104, 12, fur('#1f1610', { strokeWidth: 1 })));
add(gen.circle(103, 101, 4, o({ fill: '#ffffff', fillStyle: 'solid', stroke: '#ffffff', strokeWidth: 0.5, roughness: 0.3 })));
add(gen.circle(159, 101, 4, o({ fill: '#ffffff', fillStyle: 'solid', stroke: '#ffffff', strokeWidth: 0.5, roughness: 0.3 })));
// cheeks
add(gen.ellipse(84, 130, 16, 9, o({ fill: '#e8968a', fillStyle: 'solid', stroke: 'none', roughness: 0.6 })));
add(gen.ellipse(172, 130, 16, 9, o({ fill: '#e8968a', fillStyle: 'solid', stroke: 'none', roughness: 0.6 })));
// nose
add(gen.path('M118 117 Q128 111 138 117 Q135 127 128 128 Q121 127 118 117 Z', fur('#1f1610', { strokeWidth: 1.2, roughness: 0.6 })));
// the quokka smile
add(gen.path('M128 128 L128 134', o({ strokeWidth: 2.4, roughness: 0.5 })));
add(gen.path('M110 132 Q119 145 128 134 Q137 145 146 132', o({ strokeWidth: 2.6, roughness: 0.6 })));
// little hands held at the chest
add(gen.ellipse(108, 172, 22, 15, fur('#7d6552')));
add(gen.ellipse(148, 172, 22, 15, fur('#7d6552')));

const body = parts.map((p) => `<path d="${p.d}" stroke="${p.stroke}" stroke-width="${p.strokeWidth}" fill="${p.fill || 'none'}" stroke-linecap="round" stroke-linejoin="round"/>`).join('\n  ');
writeFileSync(OUT, `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256" role="img" aria-label="nomess quokka">\n  ${body}\n</svg>\n`);
console.log('wrote', OUT);

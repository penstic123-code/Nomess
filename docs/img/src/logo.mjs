// Hand-drawn quokka logo (side view, sitting). Usage: cd docs/img/src && npm install && node logo.mjs  -> docs/logo.svg
import rough from 'roughjs';
import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'logo.svg');
const gen = rough.generator();
const parts = [];
let seed = 11;
const ink = '#3a2a1f';
const o = (x = {}) => ({ seed: seed++, roughness: 1.0, bowing: 0.7, stroke: ink, strokeWidth: 2.2, ...x });
const add = (d) => { for (const p of gen.toPaths(d)) parts.push(p); };
const fur = (fill, x = {}) => o({ fill, fillStyle: 'solid', ...x });
const FUR = '#9a8270', DARK = '#7a6352', PALE = '#e6d3b6';

// background badge
add(gen.rectangle(6, 6, 244, 244, o({ fill: '#f3e4c6', fillStyle: 'solid', stroke: '#c9b48f', strokeWidth: 2, roughness: 0.8 })));
// ground line
add(gen.line(26, 236, 232, 236, o({ stroke: '#c9b48f', strokeWidth: 2, roughness: 1.4 })));

// tail lying on the ground behind
add(gen.path('M188 214 C210 222 226 228 238 232', o({ strokeWidth: 11, stroke: DARK, roughness: 0.6 })));
// long hind foot (macropod) flat on the ground
add(gen.ellipse(128, 232, 84, 14, fur(DARK)));
// body: hunched, sitting upright
add(gen.path('M124 116 C166 104 208 140 208 190 C208 222 188 234 158 234 L120 234 C98 234 92 216 98 196 C104 172 102 140 124 116 Z', fur(FUR)));
// pale chest and belly
add(gen.ellipse(122, 186, 40, 84, fur(PALE, { strokeWidth: 1.2 })));
// thigh
add(gen.ellipse(166, 200, 58, 50, fur('#8f7764', { strokeWidth: 1.6 })));
// little front paws held at the chest
add(gen.ellipse(106, 160, 18, 11, fur(DARK)));
add(gen.ellipse(116, 170, 18, 11, fur(DARK)));

// ear: small, rounded, high on the back of the head
add(gen.ellipse(132, 56, 28, 30, fur(DARK, { roughness: 0.8 })));
add(gen.ellipse(132, 58, 14, 17, fur('#d8a28d', { strokeWidth: 1 })));
// head with a short pointed snout facing left
add(gen.path('M150 92 C150 62 124 48 100 54 C82 58 72 70 68 84 C65 92 64 100 70 106 C82 118 100 128 120 128 C140 128 152 112 150 92 Z', fur('#a68c78')));
// pale lower face
add(gen.path('M70 106 C82 118 100 126 120 126 C134 126 142 120 146 110 C128 116 104 114 86 106 Z', fur(PALE, { strokeWidth: 0.8, roughness: 0.6 })));
// nose at the snout tip
add(gen.path('M62 96 C63 90 71 89 74 93 C75 99 71 103 66 103 C63 102 61 100 62 96 Z', fur('#1f1610', { strokeWidth: 1, roughness: 0.4 })));
// eye
add(gen.circle(100, 84, 15, fur('#1f1610', { strokeWidth: 1 })));
add(gen.circle(103, 81, 4.5, o({ fill: '#ffffff', fillStyle: 'solid', stroke: '#ffffff', strokeWidth: 0.5, roughness: 0.3 })));
// cheek blush
add(gen.ellipse(118, 104, 16, 9, o({ fill: '#e8968a', fillStyle: 'solid', stroke: 'none', roughness: 0.5 })));
// the quokka smile, corner turned up
add(gen.path('M69 105 Q82 118 100 108', o({ strokeWidth: 2.4, roughness: 0.5 })));

const body = parts.map((p) => `<path d="${p.d}" stroke="${p.stroke}" stroke-width="${p.strokeWidth}" fill="${p.fill || 'none'}" stroke-linecap="round" stroke-linejoin="round"/>`).join('\n  ');
writeFileSync(OUT, `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256" role="img" aria-label="nomess quokka">\n  ${body}\n</svg>\n`);
console.log('wrote', OUT);

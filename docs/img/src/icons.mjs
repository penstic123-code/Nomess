// Hand-drawn section icons. Usage: cd docs/img/src && npm install && node icons.mjs  -> docs/img/icons/*.svg
import rough from 'roughjs';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'icons');
mkdirSync(OUT, { recursive: true });
const INK = '#2b2b2b', TEAL = '#0f6b5c', MINT = '#d6eee7', RED = '#b83227', PINK = '#f8ddd8', SAND = '#f3e4c6', WHITE = '#ffffff';

function icon(name, draw) {
  const gen = rough.generator();
  const parts = [];
  let seed = 3;
  const o = (x = {}) => ({ seed: seed++, roughness: 1.0, bowing: 0.8, stroke: INK, strokeWidth: 2.4, ...x });
  const fill = (f, x = {}) => o({ fill: f, fillStyle: 'solid', ...x });
  const add = (d) => { for (const p of gen.toPaths(d)) parts.push(p); };
  // soft round badge behind every icon
  add(gen.circle(32, 32, 58, o({ fill: SAND, fillStyle: 'solid', stroke: 'none', roughness: 0.6 })));
  draw({ gen, add, o, fill });
  const body = parts.map((p) => `<path d="${p.d}" stroke="${p.stroke}" stroke-width="${p.strokeWidth}" fill="${p.fill || 'none'}" stroke-linecap="round" stroke-linejoin="round"/>`).join('');
  writeFileSync(join(OUT, name + '.svg'), `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">${body}</svg>\n`);
}

// 1 lean-change: magnifier over a code line
icon('lean', ({ gen, add, o, fill }) => {
  add(gen.rectangle(12, 14, 30, 34, fill(WHITE)));
  add(gen.line(17, 22, 34, 22, o({ strokeWidth: 2 })));
  add(gen.line(17, 29, 30, 29, o({ strokeWidth: 2 })));
  add(gen.line(17, 36, 26, 36, o({ strokeWidth: 2 })));
  add(gen.circle(38, 36, 18, fill(MINT, { stroke: TEAL })));
  add(gen.line(45, 43, 54, 52, o({ stroke: TEAL, strokeWidth: 4 })));
});
// 2 workflow + gate: shield with a check
icon('gate', ({ gen, add, o, fill }) => {
  add(gen.path('M32 9 L52 16 C52 34 46 46 32 55 C18 46 12 34 12 16 Z', fill(MINT, { stroke: TEAL })));
  add(gen.path('M22 32 L29 39 L43 24', o({ stroke: TEAL, strokeWidth: 4 })));
});
// 3 system map: three linked nodes
icon('map', ({ gen, add, o, fill }) => {
  add(gen.line(20, 22, 44, 22, o({ strokeWidth: 2 })));
  add(gen.line(20, 22, 32, 44, o({ strokeWidth: 2 })));
  add(gen.line(44, 22, 32, 44, o({ strokeWidth: 2 })));
  add(gen.rectangle(11, 15, 18, 14, fill(WHITE)));
  add(gen.rectangle(35, 15, 18, 14, fill(WHITE)));
  add(gen.rectangle(23, 38, 18, 14, fill(MINT, { stroke: TEAL })));
});
// 4 memory and lessons: notebook with a bookmark
icon('lessons', ({ gen, add, o, fill }) => {
  add(gen.rectangle(15, 11, 32, 42, fill(WHITE)));
  add(gen.line(21, 11, 21, 53, o({ strokeWidth: 1.6 })));
  add(gen.line(26, 22, 41, 22, o({ strokeWidth: 2 })));
  add(gen.line(26, 29, 41, 29, o({ strokeWidth: 2 })));
  add(gen.line(26, 36, 36, 36, o({ strokeWidth: 2 })));
  add(gen.path('M39 9 L47 9 L47 24 L43 20 L39 24 Z', fill(RED, { stroke: RED, strokeWidth: 1.6 })));
});
// 5 path-scoped rules: folder with a pinned note
icon('rules', ({ gen, add, o, fill }) => {
  add(gen.path('M9 20 L24 20 L28 25 L55 25 L55 50 L9 50 Z', fill(MINT, { stroke: TEAL })));
  add(gen.rectangle(26, 12, 20, 20, fill(WHITE, { strokeWidth: 2 })));
  add(gen.line(30, 19, 42, 19, o({ strokeWidth: 1.8 })));
  add(gen.line(30, 25, 38, 25, o({ strokeWidth: 1.8 })));
  add(gen.circle(36, 12, 7, fill(RED, { stroke: RED, strokeWidth: 1.4 })));
});
// 6 mess detection + ratchet: a step line that only goes down, with a cross on the jump up
icon('ratchet', ({ gen, add, o, fill }) => {
  add(gen.line(10, 52, 54, 52, o({ strokeWidth: 2 })));
  add(gen.path('M12 18 L26 18 L26 30 L40 30 L40 42 L52 42', o({ stroke: TEAL, strokeWidth: 3.6 })));
  add(gen.path('M44 14 L52 22 M52 14 L44 22', o({ stroke: RED, strokeWidth: 3.4 })));
});
// together: two arrows joining
icon('together', ({ gen, add, o, fill }) => {
  add(gen.circle(22, 32, 22, fill(MINT, { stroke: TEAL })));
  add(gen.circle(42, 32, 22, fill(PINK, { stroke: RED })));
  add(gen.circle(32, 32, 8, fill(WHITE)));
});
// sizes: three bars small / medium / large
icon('sizes', ({ gen, add, o, fill }) => {
  add(gen.rectangle(12, 38, 10, 14, fill(WHITE)));
  add(gen.rectangle(27, 28, 10, 24, fill(MINT, { stroke: TEAL })));
  add(gen.rectangle(42, 16, 10, 36, fill(TEAL, { stroke: TEAL })));
});
// quick start: rocket-ish arrow
icon('start', ({ gen, add, o, fill }) => {
  add(gen.path('M32 10 C42 18 44 32 40 44 L24 44 C20 32 22 18 32 10 Z', fill(WHITE)));
  add(gen.circle(32, 26, 9, fill(MINT, { stroke: TEAL })));
  add(gen.path('M24 40 L16 50 L26 46 M40 40 L48 50 L38 46', fill(RED, { stroke: RED, strokeWidth: 2 })));
});
console.log('wrote icons to', OUT);

// Hand-drawn concept diagrams for the README.
// Usage: cd docs/img/src && npm install && node diagrams.mjs
// Writes docs/img/zh/*.svg and docs/img/en/*.svg. Every diagram is a function of L(zh, en).
import rough from 'roughjs';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..');
const W = 760;
const FONT = `"Segoe Print","Comic Sans MS","Kaiti SC","KaiTi","PingFang SC","Microsoft YaHei",cursive,sans-serif`;
const MONO = `Consolas,"Cascadia Mono",Menlo,"Microsoft YaHei",monospace`;
const C = {
  ink: '#2b2b2b', bg: '#fbfaf5', edge: '#e2ded3',
  accent: '#0f6b5c', accentFill: '#d6eee7',
  red: '#b83227', redFill: '#f8ddd8',
  yellow: '#a8700f', yellowFill: '#fbecc6',
  gray: '#6b6f76', grayFill: '#ecebe6', white: '#ffffff',
};
const TONES = {
  plain: [C.ink, C.white], accent: [C.accent, C.accentFill], red: [C.red, C.redFill],
  yellow: [C.yellow, C.yellowFill], gray: [C.gray, C.grayFill], solid: [C.accent, C.accent],
};

// ---------- drawing context ----------
function canvas(h) {
  const gen = rough.generator();
  let seed = 1;
  const shapes = [];
  const texts = [];
  const warnings = [];
  const opts = (o = {}) => ({ seed: seed++, roughness: 1.2, bowing: 1, strokeWidth: 1.6, ...o });
  const push = (d) => { for (const p of gen.toPaths(d)) shapes.push(p); };

  // text width estimate (px), good enough for fitting checks
  const tw = (s, size, mono) => {
    let w = 0;
    for (const ch of s) {
      if (/[⺀-￿]/.test(ch) && !/[✓✗↺→←↓↑↔⇄·×]/.test(ch)) w += size * 1.0;
      else if (mono) w += size * 0.55;
      else if (ch === ' ') w += size * 0.3;
      else if (/[A-Z0-9]/.test(ch)) w += size * 0.66;
      else if (/[il.,:;'|!]/.test(ch)) w += size * 0.3;
      else w += size * 0.58;
    }
    return w;
  };

  const text = (x, y, s, o = {}) => {
    const { size = 14, anchor = 'start', color = C.ink, weight = 400, mono = false, halo = true, lh = 1.3 } = o;
    texts.push({ x, y, s: String(s), size, anchor, color, weight, mono, halo, lh });
  };

  // fit multi-line label into width w (shrinks font, warns when still too wide)
  const fit = (label, w, h, size, mono) => {
    const lines = String(label).split('\n');
    const widest = Math.max(...lines.map((l) => tw(l, size, mono)));
    let s = size;
    if (widest > w - 14) s = Math.max(11, size * (w - 14) / widest);
    if (Math.max(...lines.map((l) => tw(l, s, mono))) > w - 6) warnings.push(`too wide: "${label}" in ${w}px`);
    if (lines.length * s * 1.3 > h + 2) warnings.push(`too tall: "${label}" in ${h}px`);
    return s;
  };

  const label = (cx, cy, s, w, h, o = {}) => {
    const size = fit(s, w, h, o.size || 15, o.mono);
    const lines = String(s).split('\n');
    const lh = size * 1.3;
    const y0 = cy - (lines.length - 1) * lh / 2 + size * 0.35;
    text(cx, y0, s, { ...o, size, anchor: 'middle', halo: false });
  };

  // box: x, y = top-left. returns anchors
  const box = (x, y, w, h, s = '', o = {}) => {
    const [stroke, fill] = TONES[o.tone || 'plain'];
    push(gen.rectangle(x, y, w, h, opts({ stroke, fill: o.fill || fill, fillStyle: 'solid',
      strokeLineDash: o.dashed ? [6, 5] : undefined, strokeWidth: o.sw || 1.6 })));
    if (s) label(x + w / 2, y + h / 2 + (o.dy || 0), s, w, h, { color: o.textColor || (o.tone === 'solid' ? C.white : C.ink), weight: o.weight, size: o.size, mono: o.mono });
    return { x, y, w, h, l: [x, y + h / 2], r: [x + w, y + h / 2], t: [x + w / 2, y], b: [x + w / 2, y + h], cx: x + w / 2, cy: y + h / 2 };
  };

  const ellipse = (cx, cy, w, h, s = '', o = {}) => {
    const [stroke, fill] = TONES[o.tone || 'plain'];
    push(gen.ellipse(cx, cy, w, h, opts({ stroke, fill, fillStyle: 'solid' })));
    if (s) label(cx, cy, s, w * 0.85, h, { size: o.size || 14, mono: o.mono, color: o.textColor });
    return { l: [cx - w / 2, cy], r: [cx + w / 2, cy], t: [cx, cy - h / 2], b: [cx, cy + h / 2], cx, cy };
  };

  // chip with auto width; returns width
  const chip = (x, y, s, o = {}) => {
    const size = o.size || 13;
    const w = tw(s, size, o.mono) + 18;
    box(x, y, w, o.h || 26, s, { ...o, size });
    return w;
  };

  const head = (p, q, color, sw) => {
    const a = Math.atan2(q[1] - p[1], q[0] - p[0]);
    for (const da of [0.45, -0.45]) {
      push(gen.line(q[0], q[1], q[0] - 11 * Math.cos(a + da), q[1] - 11 * Math.sin(a + da), opts({ stroke: color, strokeWidth: sw, roughness: 0.6 })));
    }
  };

  // arrow through points (polyline). o.curve -> smooth curve
  const arrow = (pts, o = {}) => {
    const color = o.color || C.ink;
    const sw = o.sw || 1.6;
    const ro = opts({ stroke: color, strokeWidth: sw, roughness: 0.9, strokeLineDash: o.dashed ? [7, 5] : undefined });
    push(o.curve ? gen.curve(pts, ro) : gen.linearPath(pts, ro));
    if (!o.noHead) head(pts[pts.length - 2], pts[pts.length - 1], color, sw);
    if (o.both) head(pts[1], pts[0], color, sw);
    if (o.label) {
      const [lx, ly] = o.at || [(pts[0][0] + pts[pts.length - 1][0]) / 2, (pts[0][1] + pts[pts.length - 1][1]) / 2 - 8];
      text(lx, ly, o.label, { size: o.size || 13, anchor: o.anchor || 'middle', color: o.labelColor || color });
    }
  };

  const line = (x1, y1, x2, y2, o = {}) => push(gen.line(x1, y1, x2, y2, opts({ stroke: o.color || C.gray, strokeWidth: o.sw || 1.4, strokeLineDash: o.dashed ? [6, 5] : undefined, roughness: o.roughness ?? 1 })));

  const mark = (x, y, kind, s = 1) => {
    if (kind === 'ok') {
      push(gen.linearPath([[x - 8 * s, y], [x - 2 * s, y + 7 * s], [x + 9 * s, y - 8 * s]], opts({ stroke: C.accent, strokeWidth: 2.6, roughness: 0.7 })));
    } else {
      line(x - 7 * s, y - 7 * s, x + 7 * s, y + 7 * s, { color: C.red, sw: 2.6, roughness: 0.7 });
      line(x + 7 * s, y - 7 * s, x - 7 * s, y + 7 * s, { color: C.red, sw: 2.6, roughness: 0.7 });
    }
  };

  const title = (s) => text(28, 38, s, { size: 18, weight: 700, color: C.ink });

  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const render = (name) => {
    const out = [];
    out.push(`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${h}" viewBox="0 0 ${W} ${h}" role="img" aria-label="${esc(name)}">`);
    out.push(`<rect x="3" y="3" width="${W - 6}" height="${h - 6}" rx="18" fill="${C.bg}" stroke="${C.edge}" stroke-width="2"/>`);
    out.push('<g fill="none" stroke-linecap="round" stroke-linejoin="round">');
    for (const p of shapes) out.push(`<path d="${p.d}" stroke="${p.stroke}" stroke-width="${p.strokeWidth}" fill="${p.fill || 'none'}"/>`);
    out.push('</g>');
    for (const t of texts) {
      const lines = t.s.split('\n');
      const fam = t.mono ? MONO : FONT;
      const halo = t.halo ? ` stroke="${C.bg}" stroke-width="5" stroke-linejoin="round" paint-order="stroke"` : '';
      const tsp = lines.map((l, i) => `<tspan x="${t.x.toFixed(1)}" dy="${i ? (t.size * t.lh).toFixed(1) : 0}">${esc(l)}</tspan>`).join('');
      out.push(`<text x="${t.x.toFixed(1)}" y="${t.y.toFixed(1)}" font-family='${fam}' font-size="${t.size.toFixed(1)}" font-weight="${t.weight}" fill="${t.color}" text-anchor="${t.anchor}" xml:space="preserve"${halo}>${tsp}</text>`);
    }
    out.push('</svg>');
    return out.join('\n');
  };
  return { box, ellipse, chip, arrow, line, mark, text, title, tw, render, warnings };
}

// ---------- diagrams ----------
const D = {};

D['memory-loop'] = (L) => {
  const g = canvas(330);
  const n1 = g.box(60, 40, 220, 64, L('记录经验', 'Record lessons'), { weight: 700, size: 17 });
  const n2 = g.box(480, 40, 220, 64, L('整理并核实', 'Tidy and verify'), { tone: 'accent', weight: 700, size: 17 });
  const n3 = g.box(480, 216, 220, 64, L('提炼成规则', 'Distill into rules'), { tone: 'accent', weight: 700, size: 17 });
  const n4 = g.box(60, 216, 220, 64, L('修改相关代码时加载', 'Load when related code changes'), { tone: 'solid', weight: 700, size: 16 });
  g.arrow([n1.r, n2.l], { sw: 1.8 });
  g.arrow([n2.b, n3.t], { sw: 1.8 });
  g.arrow([n3.l, n4.r], { sw: 1.8 });
  g.arrow([[90, 216], [90, 104]], { sw: 1.8, label: L('新经验', 'new lessons'), at: [100, 166], anchor: 'start', labelColor: C.gray });
  g.chip(196, 112, L('开发记忆', 'dev memory'), { size: 13, tone: 'gray' });
  g.chip(614, 112, L('项目文档', 'project docs'), { size: 13, tone: 'gray' });
  g.chip(538, 288, L('路径规则', 'path rules'), { size: 13, tone: 'gray' });
  g.text(380, 168, L('项目长期记忆', 'Long-term project memory'), { size: 18, weight: 700, color: C.accent, anchor: 'middle' });
  return g;
};

D['rules-load'] = (L) => {
  const g = canvas(300);
  g.box(24, 24, 300, 252, '', { tone: 'gray', fill: '#f3f1ea' });
  g.text(44, 54, L('项目', 'Project'), { size: 16, weight: 700 });
  const rows = [['A', 'accent'], ['B', 'plain'], ['C', 'plain']];
  const rs = rows.map(([k, tone], i) => {
    const y = 74 + i * 64;
    g.box(44, y, 120, 46, L('目录 ', 'folder ') + k, { size: 15 });
    return g.box(184, y + 6, 118, 34, L('规则 ', 'rules ') + k, { tone, size: 14 });
  });
  g.box(460, 60, 270, 180, '', { tone: 'plain', dashed: true, sw: 1.2 });
  g.text(476, 88, L('上下文', 'Context'), { size: 16, weight: 700 });
  const inCtx = g.box(520, 130, 150, 44, L('规则 A', 'rules A'), { tone: 'accent', weight: 700, size: 15 });
  g.arrow([rs[0].r, inCtx.l], { color: C.accent, sw: 2, label: L('读取目录 A 的文件', 'reading a file in A'), at: [380, 78] });
  g.mark(595, 208, 'ok', 0.9);
  return g;
};

D['docs-sources'] = (L) => {
  const g = canvas(300);
  const rows = [
    [L('代码能分析出的', 'What the code can tell'), L('脚本生成', 'generated by scripts'), L('系统地图', 'System map'), 'plain'],
    [L('代码看不出的', 'What the code cannot tell'), L('审查后写入', 'written after review'), L('项目文档', 'Project docs'), 'accent'],
    [L('需要反复提醒的', 'What needs repeating'), L('核实后提炼', 'distilled once verified'), L('路径规则', 'Path rules'), 'solid'],
  ];
  rows.forEach(([src, how, dst, tone], i) => {
    const y = 34 + i * 86;
    const a = g.box(40, y, 220, 56, src, { tone: 'gray', size: 16 });
    const b = g.box(520, y, 200, 56, dst, { tone, weight: 700, size: 17 });
    g.arrow([a.r, b.l], { sw: 1.6, label: how, at: [390, y + 20], labelColor: C.gray, size: 14 });
  });
  return g;
};

D['baseline'] = (L) => {
  const g = canvas(310);
  const base = 230, unit = 40;
  const cols = [
    [L('接入时', 'On install'), 3, 'gray', L('冻结为基线', 'frozen as baseline'), null],
    [L('新增问题', 'New problem'), 4, 'red', L('拦下', 'blocked'), 'no'],
    [L('修好一个', 'One fixed'), 2, 'accent', L('收紧基线', 'baseline tightened'), 'ok'],
    [L('之后', 'Later'), 3, 'red', L('回不来', "can't come back"), 'no'],
  ];
  cols.forEach(([h, n, tone, cap, m], i) => {
    const x = 70 + i * 170;
    g.text(x + 45, 40, h, { size: 15, anchor: 'middle', weight: 700 });
    for (let k = 0; k < n; k++) g.box(x + 15, base - (k + 1) * unit + 4, 60, unit - 8, '', { tone });
    g.text(x + 45, base + 32, cap, { size: 14, anchor: 'middle', color: tone === 'red' ? C.red : tone === 'gray' ? C.gray : C.accent });
    if (m) g.mark(x + 100, base - n * unit + 16, m, 0.9);
  });
  g.line(40, base, 720, base, { color: C.ink, sw: 1.4 });
  g.arrow([[44, base - 3 * unit - 2], [400, base - 3 * unit - 2], [400, base - 2 * unit - 2], [720, base - 2 * unit - 2]], { color: C.accent, dashed: true, sw: 2, noHead: true });
  g.text(48, base - 3 * unit - 10, L('基线', 'baseline'), { size: 13, color: C.accent });
  return g;
};

D['fix-root'] = (L) => {
  const g = canvas(300);
  const panel = (x, ttl, color, ok) => {
    g.box(x, 20, 346, 260, '', { tone: 'plain', fill: ok ? '#f4faf8' : '#fdf7f5', dashed: true, sw: 1 });
    g.mark(x + 26, 48, ok ? 'ok' : 'no');
    g.text(x + 44, 54, ttl, { size: 17, weight: 700, color });
  };
  panel(20, L('给症状打补丁', 'Patch the symptoms'), C.red, false);
  panel(394, L('在根因处解决', 'Fix the root cause'), C.accent, true);
  [0, 1, 2].forEach((i) => {
    const s = g.box(40 + i * 104, 84, 94, 40, L('症状', 'symptom'), { size: 14 });
    g.box(46 + i * 104, 136, 82, 28, L('补丁', 'patch'), { tone: 'red', size: 13 });
    g.arrow([[87 + i * 104, 222], [87 + i * 104, 168]], { color: C.gray, sw: 1.2 });
    const t = g.box(414 + i * 104, 84, 94, 40, L('症状', 'symptom'), { tone: 'gray', size: 14, dashed: true });
    g.arrow([[565, 214], [t.cx, 126]], { color: C.gray, sw: 1.2, noHead: true, dashed: true });
  });
  g.box(110, 222, 154, 44, L('根因还在', 'root still there'), { tone: 'red', weight: 700, size: 15 });
  g.box(488, 214, 154, 44, L('根因已修', 'root fixed'), { tone: 'accent', weight: 700, size: 15 });
  return g;
};

D['flow-tiers'] = (L) => {
  const g = canvas(460);
  g.text(380, 36, L('错了会坏到哪？', 'If it goes wrong, what breaks?'), { size: 16, weight: 700, anchor: 'middle', color: C.gray });
  const src = g.box(28, 231, 110, 50, L('一个改动', 'A change'), { weight: 700 });
  const rows = [
    [L('什么都不坏：注释、文档', 'Nothing: comments, docs'), L('直接改', 'Just do it'), 'plain'],
    [L('一个模块内部', 'Inside one module'), L('改完过检查', 'Change, pass the check'), 'accent'],
    [L('一个系统对外的功能', "One system's features"), L('几行方案\n改完审一次', 'A few lines of plan,\none code review'), 'accent'],
    [L('别的系统 · 共享数据 · 持久格式', 'Other systems · shared data · stored formats'), L('再加：写方案、定归属\n先审方案', 'Plus: written plan, owners,\nplan reviewed first'), 'solid'],
    [L('整个系统：新建或重做', 'A whole system: new or rebuilt'), L('再加：设计、原型\n签字、里程碑', 'Plus: design, prototype,\nsign-off, milestones'), 'solid'],
  ];
  rows.forEach(([cond, res, tone], i) => {
    const y = 60 + i * 80;
    const c = g.box(190, y, 290, 56, cond, { tone: 'gray', size: 15 });
    g.arrow([src.r, c.l], { sw: 1.4 });
    const r = g.box(530, y, 200, 56, res, { tone, weight: 700, size: 15 });
    g.arrow([c.r, r.l], { sw: 1.4 });
  });
  return g;
};

// ---------- build ----------
let warned = 0;
for (const lang of ['zh', 'en']) {
  const L = (zh, en) => (lang === 'zh' ? zh : en);
  mkdirSync(join(OUT, lang), { recursive: true });
  for (const [name, fn] of Object.entries(D)) {
    const g = fn(L);
    writeFileSync(join(OUT, lang, `${name}.svg`), g.render(name));
    for (const w of g.warnings) { console.warn(`[${lang}/${name}] ${w}`); warned++; }
  }
}
console.log(`${Object.keys(D).length} diagrams x 2 languages written to ${OUT}${warned ? `, ${warned} warnings` : ''}`);

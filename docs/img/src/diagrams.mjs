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

D['lean-ladder'] = (L) => {
  const g = canvas(440);
  g.title(L('决策阶梯：从上往下问，能停就停', 'Decision ladder: ask top-down, stop as early as you can'));
  const steps = [
    [L('能不做？', 'Do we need it?'), L('例：没人用的开关，不加', 'e.g. a toggle nobody uses: skip it')],
    [L('仓库里已有？', 'Already in the repo?'), L('例：已有 validate_name()，直接调', 'e.g. call the existing validate_name()')],
    [L('标准库 / 已装依赖？', 'Stdlib / installed dependency?'), L('例：用 pathlib，不手拼路径', 'e.g. pathlib, not hand-built paths')],
    [L('先查可靠资料', 'Check reliable sources'), L('例：协议、并发、陌生第三方接口', 'e.g. protocols, concurrency, new APIs')],
    [L('写最小完整实现', 'Write the smallest complete fix'), L('例：够解决问题，不多写', 'e.g. just enough to solve it')],
  ];
  steps.forEach(([q, ex], i) => {
    const x = 36 + i * 40, y = 62 + i * 66;
    const b = g.box(x, y, 250, 46, q, { tone: i === 4 ? 'accent' : 'plain', weight: i === 4 ? 700 : 400 });
    g.arrow([[x + 262, y + 23], [x + 290, y + 23]], { color: C.gray, sw: 1.3 });
    g.text(x + 300, y + 28, ex, { size: 14, color: C.gray });
    if (i < 4) g.arrow([[x + 70, y + 46], [x + 70, y + 66]], { color: C.ink, label: L('走不通', 'no'), at: [x + 82, y + 61], anchor: 'start', size: 12 });
  });
  g.text(36, 420, L('交付时说明：停在哪一级、用什么验证了改动', 'At hand-off the agent says which step it stopped at and how it verified the change'), { size: 14, color: C.accent });
  return g;
};

D['lean-shared-layer'] = (L) => {
  const g = canvas(350);
  // left panel: symptom fixes
  g.box(20, 20, 352, 310, '', { tone: 'plain', fill: '#fdf7f5', dashed: true, sw: 1 });
  g.mark(46, 48, 'no');
  g.text(64, 54, L('修在症状处', 'Fix at the symptom'), { size: 17, weight: 700, color: C.red });
  const ys = [86, 160, 234];
  const names = [L('上传入口 A', 'Upload A'), L('上传入口 B', 'Upload B'), L('新入口 C', 'New entry C')];
  const save = g.box(306, 86, 52, 188, L('保存', 'Save'), { tone: 'gray' });
  ys.forEach((y, i) => {
    g.box(36, y, 108, 40, names[i], { dashed: i === 2 });
    if (i < 2) {
      g.box(170, y + 4, 104, 32, L('补 if 空名', 'patch: if blank'), { tone: 'red', size: 13 });
      g.arrow([[144, y + 20], [168, y + 20]], { sw: 1.3 });
      g.arrow([[274, y + 20], [304, y + 20]], { sw: 1.3 });
    } else {
      g.arrow([[144, y + 20], [304, y + 20]], { color: C.red, label: L('bug 又回来', 'bug is back'), at: [224, y + 12], labelColor: C.red });
    }
  });
  g.text(196, 310, L('每个入口各补一个判断', 'a check patched into each entry'), { size: 13, color: C.gray, anchor: 'middle' });
  // right panel: shared layer
  g.box(388, 20, 352, 310, '', { tone: 'plain', fill: '#f4faf8', dashed: true, sw: 1 });
  g.mark(414, 48, 'ok');
  g.text(432, 54, L('修在共享层', 'Fix in the shared layer'), { size: 17, weight: 700, color: C.accent });
  const shared = g.box(556, 140, 106, 80, L('共享校验\n拒绝空名', 'shared check:\nreject blank'), { tone: 'accent', weight: 700, size: 14 });
  g.box(684, 86, 44, 188, L('保\n存', 'S\na\nv\ne'), { tone: 'gray', size: 14 });
  ys.forEach((y, i) => {
    g.box(404, y, 108, 40, names[i], { dashed: i === 2 });
    g.arrow([[512, y + 20], [554, 160 + i * 20]], { sw: 1.3, color: i === 2 ? C.accent : C.ink });
  });
  g.arrow([[662, 180], [682, 180]], { sw: 1.3 });
  g.text(564, 310, L('所有入口走同一套逻辑，新入口也受保护', 'every entry, new ones too, shares one check'), { size: 13, color: C.gray, anchor: 'middle' });
  return g;
};

D['flow-tiers'] = (L) => {
  const g = canvas(330);
  g.title(L('三档：按改动碰到什么来选', 'Three tiers: pick by what the change touches'));
  const src = g.box(28, 150, 110, 50, L('一个改动', 'A change'), { weight: 700 });
  const rows = [
    [L('注释、文档之类的小改动', 'Small edits: comments, docs'), L('直接改', 'Just do it'), 'plain', ''],
    [L('自成一块的单点修复', 'Self-contained fix'), L('轻流程', 'Light workflow'), 'accent', ''],
    [L('改接口、存档格式、\n执行时序、数据归属', 'Interfaces, save formats,\nexecution order, data ownership'), L('全套流程', 'Full workflow'), 'solid', L('先定谁读、谁写、何时写', 'decide who reads, who writes, when')],
  ];
  rows.forEach(([cond, res, tone, note], i) => {
    const y = 66 + i * 82;
    const c = g.box(196, y, 280, 54, cond, { tone: 'gray', size: 14 });
    g.arrow([src.r, c.l], { sw: 1.4 });
    const r = g.box(530, y + 4, 180, 46, res, { tone, weight: 700, size: 16 });
    g.arrow([c.r, r.l], { sw: 1.4 });
    if (note) g.text(620, y + 72, note, { size: 12, color: C.accent, anchor: 'middle' });
  });
  return g;
};

D['flow-pipeline'] = (L) => {
  const g = canvas(350);
  const r1 = [L('方案', 'Design'), L('审方案', 'Review design'), L('试读简报', 'Trial read'), L('派包', 'Hand out')];
  const r2 = [L('写代码', 'Write code'), L('交回', 'Hand back'), L('审代码', 'Review code'), L('合并', 'Merge')];
  const xs = [72, 242, 412, 582];
  const top = r1.map((s, i) => g.box(xs[i], 92, 128, 48, s, { tone: i === 2 ? 'accent' : 'plain', weight: 700 }));
  const bot = r2.map((s, i) => g.box(xs[i], 224, 128, 48, s, { tone: i === 3 ? 'solid' : 'plain', weight: 700 }));
  for (let i = 0; i < 3; i++) { g.arrow([top[i].r, top[i + 1].l]); g.arrow([bot[i].r, bot[i + 1].l]); }
  g.arrow([top[3].b, [646, 182], [136, 182], bot[0].t]);
  // trial read finds a gap -> back to design
  g.arrow([[476, 92], [440, 58], [306, 50], [172, 58], [136, 90]], { curve: true, dashed: true, color: C.gray });
  g.text(306, 40, L('↺ 没参与讨论的子代理读出缺口 → 回方案', '↺ a fresh subagent finds a gap → back to design'), { size: 13, color: C.gray, anchor: 'middle' });
  // premise broken during work -> back to design
  g.arrow([bot[0].l, [40, 248], [40, 116], top[0].l], { dashed: true, color: C.red });
  g.text(36, 300, L('红虚线：执行中发现前提不成立 → 退回方案，不在代码里绕', 'red dashes: a premise breaks mid-work → back to design, no workaround in code'), { size: 13, color: C.red });
  g.text(36, 324, L('并行包各用一个 worktree', 'one worktree per parallel package'), { size: 12, color: C.gray });
  return g;
};

D['flow-gate-tree'] = (L) => {
  const g = canvas(370);
  g.title(L('提交闸门检查的是"这次要提交的那棵树"', 'The commit gate checks the tree you are about to commit'));
  const wt = g.box(24, 70, 176, 56, L('工作区\n未暂存的草稿', 'Working tree\nunstaged drafts'), { tone: 'gray', dashed: true, size: 14 });
  const idx = g.box(24, 184, 176, 56, L('暂存区\ngit add 的内容', 'Index\nwhat you git add'), { size: 14, weight: 700 });
  g.arrow([wt.r, [262, 98]], { color: C.gray, dashed: true, noHead: true });
  g.mark(270, 98, 'no', 0.8);
  g.text(208, 88, L('内置检查不看', 'built-in checks ignore'), { size: 12, color: C.gray });
  const cand = g.box(300, 184, 150, 56, L('候选树', 'Candidate tree'), { tone: 'accent', weight: 700 });
  g.arrow([idx.r, cand.l], { label: 'git write-tree', at: [250, 204], size: 12 });
  const genb = g.box(300, 290, 150, 54, L('刷新的生成物\n（主分支提交时）', 'regenerated files\n(commits on main)'), { tone: 'gray', size: 13 });
  g.arrow([genb.t, cand.b], { label: '+', at: [388, 274], size: 18 });
  const chk = g.box(494, 188, 84, 48, L('检查', 'Check'), { weight: 700 });
  g.arrow([cand.r, chk.l]);
  const ok = g.box(606, 92, 136, 58, L('通过：\n写进这次提交', 'Pass:\ngoes into this commit'), { tone: 'accent', size: 13 });
  const no = g.box(606, 270, 136, 58, L('不通过：\n挡下，什么都不改', 'Fail: blocked,\nnothing changed'), { tone: 'red', size: 13 });
  g.arrow([[536, 188], [536, 121], ok.l]);
  g.arrow([[536, 236], [536, 299], no.l], { color: C.red });
  g.text(24, 280, L('git add -p 只暂存半个改动？\n就按那半个改动检查', 'git add -p staged half a change?\nthe checks see that half'), { size: 12, color: C.gray });
  return g;
};

D['map-pipeline'] = (L) => {
  const g = canvas(320);
  g.title(L('系统图：从代码算出来，不靠手画', 'System map: computed from code, not hand-drawn'));
  // files
  for (let i = 0; i < 4; i++) g.box(30 + i * 6, 80 + i * 22, 96, 30, i === 3 ? 'src/…' : '', { mono: true, size: 12 });
  g.text(84, 212, L('Git 文件清单', 'files from Git'), { size: 13, anchor: 'middle', color: C.gray });
  g.arrow([[150, 135], [200, 135]], { label: L('解析\nimport', 'parse\nimports'), at: [175, 160], size: 12 });
  // file graph grouped
  const grp = [[214, 64, 70, 70, 'billing'], [300, 64, 70, 70, 'ledger'], [252, 150, 82, 54, 'ui']];
  grp.forEach(([x, y, w, h, n]) => { g.box(x, y, w, h, '', { tone: 'gray', dashed: true, sw: 1 }); g.text(x + 4, y + h + 14, n, { size: 11, color: C.gray, mono: true }); });
  const pts = [[234, 88], [262, 112], [322, 92], [350, 116], [276, 176], [312, 180]];
  [[0, 2], [1, 3], [4, 0], [5, 1], [4, 5], [0, 1]].forEach(([a, b]) => g.line(pts[a][0], pts[a][1], pts[b][0], pts[b][1], { color: C.ink, sw: 1.1 }));
  pts.forEach(([x, y]) => g.ellipse(x, y, 14, 14, '', { tone: 'accent' }));
  g.text(292, 240, L('文件依赖', 'file dependencies'), { size: 13, anchor: 'middle', color: C.gray });
  g.arrow([[380, 135], [444, 135]], { label: L('按 systems\n汇总', 'roll up by\nsystems'), at: [412, 160], size: 12 });
  // subsystem graph
  const bi = g.ellipse(490, 92, 80, 40, 'billing', { tone: 'accent', mono: true, size: 12 });
  const le = g.ellipse(568, 160, 80, 40, 'ledger', { tone: 'accent', mono: true, size: 12 });
  const ui = g.ellipse(486, 196, 64, 36, 'ui', { tone: 'accent', mono: true, size: 12 });
  g.arrow([[522, 108], [552, 140]], { sw: 1.4 });
  g.arrow([[492, 178], [492, 113]], { sw: 1.4 });
  g.arrow([[516, 190], [534, 174]], { sw: 1.4 });
  g.text(528, 240, L('子系统图', 'subsystem graph'), { size: 13, anchor: 'middle', color: C.gray });
  g.arrow([[612, 135], [640, 135]]);
  g.box(646, 78, 92, 116, '', { tone: 'plain' });
  [100, 118, 136, 154, 172].forEach((y, i) => g.line(656, y, 728 - (i % 2) * 18, y, { color: C.accent, sw: 1.2 }));
  g.text(692, 216, 'docs/\nsystem-map/', { size: 12, anchor: 'middle', mono: true });
  g.text(28, 290, L('没配 systems 就按源码顶层目录分 · 手动重建：nomess map', 'no systems config → group by top-level source dir · rebuild: nomess map'), { size: 13, color: C.gray });
  return g;
};

D['map-gen-section'] = (L) => {
  const g = canvas(360);
  g.box(30, 24, 400, 314, '', { tone: 'plain' });
  g.text(48, 56, L('# 结算', '# Billing'), { size: 17, weight: 700 });
  const prose = (y, n) => { for (let i = 0; i < n; i++) g.line(48, y + i * 16, 400 - ((i * 53) % 90), y + i * 16, { color: '#9a9a9a', sw: 1.2, roughness: 1.6 }); };
  prose(76, 3);
  g.text(48, 140, '<!-- GEN:events BEGIN -->', { size: 13, mono: true, color: C.accent });
  g.box(48, 150, 360, 82, '', { tone: 'accent' });
  ['order.paid      billing/pay.py', 'order.refunded  billing/refund.py', 'ledger.written  ledger/write.py'].forEach((r, i) => g.text(60, 172 + i * 22, r, { size: 13, mono: true, halo: false }));
  g.text(48, 254, '<!-- GEN:events END -->', { size: 13, mono: true, color: C.accent });
  prose(276, 3);
  // right side
  g.text(456, 56, L('人写：设计取舍、踩过的坑', 'People write: trade-offs, pitfalls'), { size: 14, color: C.gray });
  g.arrow([[452, 50], [404, 84]], { color: C.gray, sw: 1.2 });
  const src = g.box(456, 96, 280, 44, 'EMIT("order.paid")', { mono: true, size: 14 });
  g.text(596, 156, L('src/billing/pay.py 里的调用', 'a call in src/billing/pay.py'), { size: 12, color: C.gray, anchor: 'middle' });
  const doc = g.box(456, 192, 280, 58, L('nomess docgen\n主分支提交时自动刷新', 'nomess docgen\nauto-refresh on main commits'), { tone: 'accent', size: 14, weight: 700 });
  g.arrow([src.b, doc.t]);
  g.arrow([doc.l, [414, 192]], { color: C.accent, sw: 2 });
  g.text(456, 292, L('只替换两行标记之间的内容', 'Only text between the markers changes'), { size: 13, color: C.accent });
  g.text(456, 316, L('动态拼出来的事件名不在表里', 'dynamically built names are not covered'), { size: 12, color: C.gray });
  return g;
};

D['lessons-lifecycle'] = (L) => {
  const g = canvas(330);
  g.title(L('一条教训的一生', 'Life of a lesson'));
  const a = g.box(24, 66, 196, 52, L('/nomess:lesson "…"\n修完故障记一句', '/nomess:lesson "…"\none line after a fix'), { size: 13 });
  const b = g.box(256, 66, 150, 52, 'docs/lessons/\ninbox.md', { mono: true, size: 13 });
  const c = g.box(442, 66, 150, 52, L('/nomess:dream\n出提案', '/nomess:dream\nproposal'), { tone: 'accent', size: 14, weight: 700 });
  const d = g.box(628, 66, 108, 52, L('你确认', 'You confirm'), { weight: 700 });
  g.arrow([a.r, b.l]); g.arrow([b.r, c.l]); g.arrow([c.r, d.l]);
  g.text(682, 138, L('可划掉：\nexecute strike 2 5', 'drop items:\nexecute strike 2 5'), { size: 12, color: C.gray, anchor: 'middle' });
  const e = g.box(392, 194, 344, 92, '', { tone: 'accent' });
  g.text(410, 216, '/nomess:dream execute', { size: 13, mono: true, color: C.accent, halo: false });
  let x = 408;
  for (const s of [L('合并重复', 'merge'), L('删过期说法', 'drop stale'), L('升成规则', 'promote to rule')]) x += g.chip(x, 236, s, { size: 13 }) + 10;
  g.arrow([[682, 172], [682, 192]]);
  const f = g.box(120, 210, 190, 60, L('git 提交\n可 revert', 'git commit\nrevertable'), { tone: 'solid', weight: 700 });
  g.arrow([e.l, f.r]);
  g.text(24, 312, L('先用代码和 Git 历史核对提案里的事实；没核实的条目标成"未核实"', 'Facts in the proposal are checked against code and Git history; unchecked entries stay marked unverified'), { size: 12, color: C.gray });
  return g;
};

D['lessons-find'] = (L) => {
  const g = canvas(330);
  g.box(20, 20, 430, 290, '', { tone: 'plain', fill: '#f4faf8', dashed: true, sw: 1 });
  g.text(36, 50, '$ nomess lessons find src/billing/', { size: 14, mono: true, color: C.accent, weight: 700 });
  const rows = [
    [L('结算重试复用原幂等键', 'retry: reuse the key'), 'src/billing/', true],
    [L('首页缓存要带版本号', 'version the page cache'), 'ui/', false],
    [L('只有账本模块调底层写入', 'only ledger writes'), 'src/billing/', true],
    [L('登录限流按账号计', 'login rate limit'), 'src/auth/', false],
  ];
  rows.forEach(([t, p, hit], i) => {
    const y = 68 + i * 44;
    g.box(36, y, 300, 34, '', { tone: hit ? 'accent' : 'gray' });
    g.text(46, y + 22, t, { size: 13, halo: false, color: hit ? C.ink : C.gray });
    g.text(326, y + 22, p, { size: 11, mono: true, anchor: 'end', halo: false, color: hit ? C.accent : C.gray });
    if (hit) g.mark(352, y + 17, 'ok', 0.8);
  });
  g.text(378, 146, L('命中\n2 条', '2\nhits'), { size: 15, weight: 700, color: C.accent });
  g.text(36, 268, L('普通 Markdown：短、能审 diff、跟着分支走', 'Plain Markdown: short, diff-reviewable, branch-aware'), { size: 13, color: C.ink });
  g.text(36, 292, L('代价：换了说法的同义教训可能搜不到', 'trade-off: a lesson worded differently can be missed'), { size: 12, color: C.gray });
  // vector db
  g.box(466, 20, 274, 290, '', { tone: 'plain', fill: '#f6f5f2', dashed: true, sw: 1 });
  g.mark(490, 48, 'no');
  g.text(508, 54, L('向量库', 'Vector database'), { size: 17, weight: 700, color: C.gray });
  const em = g.box(500, 82, 206, 44, L('嵌入模型', 'embedding model'), { tone: 'gray' });
  const st = g.box(500, 168, 206, 44, L('向量存储', 'vector store'), { tone: 'gray' });
  g.arrow([em.b, st.t], { color: C.gray });
  g.text(603, 246, L('多一套依赖要维护', 'one more dependency to run'), { size: 13, color: C.red, anchor: 'middle' });
  g.text(603, 272, L('存的东西人读不了、审不了', 'storage people cannot read or review'), { size: 13, color: C.red, anchor: 'middle' });
  return g;
};

D['rules-paths'] = (L) => {
  const g = canvas(350);
  g.box(20, 24, 320, 302, '', { tone: 'gray', fill: '#f3f1ea' });
  g.text(36, 52, '.claude/rules/nomess/', { size: 15, mono: true, weight: 700 });
  const card = (y, name, glob, rule, tone) => {
    const b = g.box(36, y, 288, 116, '', { tone });
    g.text(48, y + 22, name, { size: 12, mono: true, color: C.gray, halo: false });
    g.text(48, y + 44, `paths:\n  - "${glob}"`, { size: 13, mono: true, halo: false, lh: 1.25 });
    g.text(48, y + 100, rule, { size: 13, halo: false });
    return b;
  };
  const c1 = card(70, '3fa1c0….md', 'src/billing/**', L('结算重试沿用原请求的幂等键', 'retries reuse the original key'), 'accent');
  card(198, '9c2e47….md', 'src/auth/**', L('（auth 的规则）', '(rules for auth)'), 'plain');
  // scenarios
  const ai1 = g.ellipse(410, 110, 46, 46, 'AI', { tone: 'solid', textColor: C.white });
  g.text(442, 100, L('打开', 'opens'), { size: 13, color: C.gray });
  g.text(442, 122, 'src/billing/pay.py', { size: 14, mono: true, weight: 700 });
  g.arrow([c1.r, [384, 120]], { color: C.accent, sw: 2 });
  g.mark(470, 152, 'ok', 0.9);
  g.text(488, 158, L('只加载 billing 这份', 'loads only the billing file'), { size: 14, color: C.accent });
  g.ellipse(410, 236, 46, 46, 'AI', { tone: 'solid', textColor: C.white });
  g.text(442, 226, L('打开', 'opens'), { size: 13, color: C.gray });
  g.text(442, 248, 'ui/home.css', { size: 14, mono: true, weight: 700 });
  g.text(442, 278, L('一份规则都不加载', 'loads no rule at all'), { size: 14, color: C.gray });
  g.text(360, 318, L('只 grep 到几行不算，打开文件才加载', 'grep hits do not count; opening the file does'), { size: 12, color: C.gray });
  return g;
};

D['rules-context'] = (L) => {
  const g = canvas(320);
  g.title(L('上下文占用', 'Context window use'));
  const X = 230, WB = 500;
  const bar = (y, segs, cap) => {
    g.box(X, y, WB, 40, '', { tone: 'plain', dashed: true, sw: 1 });
    let x = X;
    for (const [w, s, tone] of segs) { g.box(x, y, w, 40, s, { tone, size: 12 }); x += w; }
    if (cap) g.text(X, y + 58, cap, { size: 12, color: C.gray });
  };
  g.text(28, 92, L('全塞进 AGENTS.md', 'All in AGENTS.md'), { size: 15, weight: 700, color: C.red });
  bar(68, [[90, L('通用规矩', 'general'), 'gray'], [80, 'billing', 'red'], [70, 'auth', 'red'], [70, 'ui', 'red'], [80, 'ledger', 'red'], [70, L('…', '…'), 'red']],
    L('一直占着；真正通用的规矩也被淹没', 'always loaded; the general rules get buried'));
  g.text(28, 190, L('按路径加载', 'Path-scoped'), { size: 15, weight: 700, color: C.accent });
  g.text(28, 212, L('改 billing 时', 'editing billing'), { size: 12, color: C.gray });
  bar(170, [[90, L('通用规矩', 'general'), 'gray'], [80, 'billing', 'accent']]);
  g.text(28, 264, L('改 ui 样式时', 'editing ui styles'), { size: 12, color: C.gray });
  bar(232, [[90, L('通用规矩', 'general'), 'gray']]);
  g.text(X + WB - 8, 202, L('空出来留给代码', 'room left for code'), { size: 13, color: C.accent, anchor: 'end' });
  g.text(X, 298, L('每份规则文件不超过 400 token，用到才进来', 'each rule file ≤ 400 tokens, loaded only when needed'), { size: 12, color: C.gray });
  return g;
};

D['smell-winnow'] = (L) => {
  const g = canvas(470);
  g.title(L('D1 复制粘贴：只比指纹，不两两比全文', 'D1 copy-paste: compare fingerprints, not whole files'));
  // 1 code -> tokens
  g.text(28, 76, L('① 切词', '① tokenize'), { size: 14, weight: 700, color: C.accent });
  g.box(120, 56, 250, 32, 'if not name: raise Err', { mono: true, size: 13 });
  g.arrow([[378, 72], [404, 72]]);
  let x = 412;
  for (const t of ['if', 'not', 'name', ':', 'raise', 'Err', '…']) x += g.chip(x, 59, t, { mono: true, size: 12 }) + 4;
  g.text(120, 106, L('去掉空白和能识别的注释', 'whitespace and known comments dropped'), { size: 12, color: C.gray });
  // 2 hashes + winnowing
  g.text(28, 162, L('② 哈希', '② hash'), { size: 14, weight: 700, color: C.accent });
  const hs = [77, 42, 91, 13, 58, 66, 24, 80, 35, 19, 71];
  hs.forEach((h, i) => {
    const pick = h === 13 || h === 19;
    g.box(120 + i * 44, 144, 38, 30, String(h), { mono: true, size: 13, tone: pick ? 'accent' : 'plain', weight: pick ? 700 : 400 });
  });
  g.text(120, 196, L('每 25 个连续词元算一个哈希；每组 26 个里挑最小的当指纹（winnowing）', 'one hash per 25 consecutive tokens; the smallest in each window of 26 is a fingerprint (winnowing)'), { size: 12, color: C.gray });
  g.line(120, 138, 380, 138, { color: C.accent, sw: 1.4 });
  g.text(250, 132, L('一个窗口 → 取最小 13', 'one window → min 13'), { size: 12, color: C.accent, anchor: 'middle' });
  // 3 collision + extend
  g.text(28, 236, L('③ 撞上', '③ match'), { size: 14, weight: 700, color: C.accent });
  const fa = g.box(120, 214, 290, 36, '', { tone: 'plain' });
  const fb = g.box(120, 282, 290, 36, '', { tone: 'plain' });
  g.text(130, 238, 'src/import.py', { size: 12, mono: true, halo: false });
  g.text(130, 306, 'src/validate.py', { size: 12, mono: true, halo: false });
  g.box(300, 218, 44, 28, '13', { tone: 'accent', mono: true, size: 12 });
  g.box(300, 286, 44, 28, '13', { tone: 'accent', mono: true, size: 12 });
  g.line(322, 246, 322, 286, { color: C.accent, sw: 2, dashed: true });
  g.arrow([[470, 266], [690, 266]], { both: true, color: C.ink });
  g.text(580, 254, L('回到原词元，向两端扩', 'back to tokens, grow both ways'), { size: 12, anchor: 'middle' });
  g.text(580, 290, L('量出实际重复多长', 'measure the real length'), { size: 12, anchor: 'middle', color: C.gray });
  // 4 outcome
  g.text(28, 370, L('④ 定色', '④ color'), { size: 14, weight: 700, color: C.accent });
  g.box(120, 350, 250, 40, L('一字不差 → 红，挡提交', 'identical → red, blocks'), { tone: 'red', size: 14 });
  g.box(390, 350, 300, 40, L('改了变量名才相同 → 黄', 'same after renames → yellow'), { tone: 'yellow', size: 14 });
  g.text(120, 424, L('太多文件都有的常见指纹直接跳过，样板代码不拖慢提交', 'fingerprints shared by too many files are skipped, so boilerplate stays cheap'), { size: 12, color: C.gray });
  return g;
};

D['smell-ratchet'] = (L) => {
  const g = canvas(350);
  g.title(L('棘轮：额度只降不升', 'Ratchet: the allowance only goes down'));
  const base = 250, unit = 44;
  const cols = [
    [L('冻结基线', 'Freeze baseline'), 2, 'gray', L('记下 P1×2', 'records P1×2'), null],
    [L('新提交', 'New commit'), 2, 'accent', L('P1×2 放行', 'P1×2 passes'), 'ok'],
    [L('新提交', 'New commit'), 3, 'red', L('P1×3 挡下', 'P1×3 blocked'), 'no'],
    [L('修掉一处', 'Fix one'), 1, 'accent', '--tighten', 'ok'],
    [L('之后', 'Later'), 2, 'red', L('P1×2 也挡', 'P1×2 now blocked'), 'no'],
  ];
  cols.forEach(([h, n, tone, cap, m], i) => {
    const x = 50 + i * 140;
    g.text(x + 40, 76, h, { size: 14, anchor: 'middle', weight: 700 });
    for (let k = 0; k < n; k++) g.box(x + 10, base - (k + 1) * unit + 4, 60, unit - 8, 'P1', { tone, mono: true, size: 13 });
    g.text(x + 40, base + 26, cap, { size: 13, anchor: 'middle', color: tone === 'red' ? C.red : tone === 'gray' ? C.gray : C.accent, mono: cap.startsWith('--') });
    if (m) g.mark(x + 92, base - n * unit + 16, m, 0.9);
  });
  g.line(30, base, 730, base, { color: C.ink, sw: 1.4 });
  // allowance line
  g.arrow([[40, base - 2 * unit - 2], [460, base - 2 * unit - 2], [460, base - unit - 2], [730, base - unit - 2]], { color: C.accent, dashed: true, sw: 2, noHead: true });
  g.text(44, base - 2 * unit - 10, L('基线额度', 'baseline allowance'), { size: 12, color: C.accent });
  g.text(470, base - unit - 54, L('额度收回，回不去', 'allowance taken back'), { size: 12, color: C.accent });
  g.text(30, 330, L('按规则号、路径和问题自身特征认人，行号只用于提示', 'findings matched by rule, path and own traits; line numbers are only for messages'), { size: 12, color: C.gray });
  return g;
};

D['smell-arch'] = (L) => {
  const g = canvas(280);
  g.title(L('子系统依赖约束（A1 / arch）', 'Subsystem constraints (A1 / arch)'));
  const panel = (x, ttl, color) => { g.box(x, 56, 228, 180, '', { tone: 'plain', fill: '#ffffff', dashed: true, sw: 1 }); g.text(x + 114, 226, ttl, { size: 13, anchor: 'middle', color }); };
  panel(20, L('上层依赖下层：允许', 'upper uses lower: allowed'), C.accent);
  const u1 = g.box(84, 74, 100, 40, 'ui', { mono: true });
  const c1 = g.box(84, 160, 100, 40, 'core', { mono: true });
  g.arrow([u1.b, c1.t], { color: C.accent, sw: 2 });
  g.mark(206, 136, 'ok');
  panel(266, L('登记的禁止方向：下层依赖上层', 'forbidden: lower → upper'), C.red);
  const u2 = g.box(330, 74, 100, 40, 'ui', { mono: true });
  const c2 = g.box(330, 160, 100, 40, 'core', { mono: true });
  g.arrow([c2.t, u2.b], { color: C.red, sw: 2 });
  g.mark(452, 136, 'no');
  panel(512, L('成环：Python 导入构成的环报红', 'Python-import cycle: red'), C.red);
  const a = g.box(536, 116, 70, 40, 'a', { mono: true });
  const b = g.box(656, 116, 70, 40, 'b', { mono: true });
  g.arrow([[606, 128], [654, 128]], { color: C.red, sw: 2 });
  g.arrow([[654, 146], [606, 146]], { color: C.red, sw: 2 });
  g.mark(631, 186, 'no');
  g.text(28, 264, L('近似提取才成立的环报黄 · 还可登记单一写入归属', 'cycles that rely on approximate extraction are yellow · single-writer ownership can be declared too'), { size: 12, color: C.gray });
  return g;
};

D['together'] = (L) => {
  const g = canvas(380);
  g.title(L('一条教训怎么变成两道防线', 'How one lesson becomes two lines of defense'));
  const a = g.box(18, 158, 140, 64, L('/nomess:lesson\n记下原因', '/nomess:lesson\nrecord why'), { size: 13 });
  const b = g.box(178, 158, 140, 64, L('/nomess:dream\n核实', '/nomess:dream\nverify'), { tone: 'accent', size: 13, weight: 700 });
  g.arrow([a.r, b.l]);
  const p = g.box(344, 66, 210, 78, L('路径规则 src/billing/**\n"重试沿用原幂等键"\n要读上下文判断', 'path rule src/billing/**\n"retry reuses the key"\nneeds judgment'), { tone: 'accent', size: 13 });
  const f = g.box(344, 236, 210, 78, L('红色 forbid 规则\n"只有账本模块调底层写入"\n能机械判定', 'red forbid rule\n"only ledger calls the write fn"\nmechanically checkable'), { tone: 'red', size: 13 });
  g.arrow([[318, 176], [342, 110]]);
  g.arrow([[318, 204], [342, 270]]);
  const p2 = g.box(588, 66, 150, 78, L('AI 读结算文件时\n被提醒', 'AI is reminded\nwhen it reads\nbilling files'), { size: 13 });
  const f2 = g.box(588, 236, 150, 78, L('漏了？提交时\nGit 钩子挡下', 'Missed it?\nthe Git hook\nblocks the commit'), { tone: 'solid', size: 13 });
  g.arrow([p.r, p2.l]); g.arrow([f.r, f2.l], { color: C.red });
  g.text(663, 166, L('第一道', 'first line'), { size: 12, anchor: 'middle', color: C.accent });
  g.text(663, 228, L('兜底', 'backstop'), { size: 12, anchor: 'middle', color: C.red });
  g.line(663, 176, 663, 214, { color: C.gray, dashed: true });
  g.text(24, 350, L('合法写入的那个文件在 allow 里留一条带理由的例外', 'the one file that legitimately writes gets a justified entry in allow'), { size: 12, color: C.gray });
  return g;
};

D['sizes'] = (L) => {
  const g = canvas(372);
  const cols = [
    ['small', L('一个人，一次一个代理', 'you + one agent at a time'), [['D1'], ['P1'], ['S1']], 'light', []],
    ['medium', L('几个代理并行', 'several agents in parallel'), [['D1'], ['P1'], ['S1'], ['A1', 1]], 'standard', []],
    ['large', L('多个代理，用排期表管任务', 'many agents, tasks on a schedule'), [['D1'], ['P1'], ['S1'], ['A1'], ['C4', 1], ['PL-DUP', 1], ['PL-STALE', 1]], 'standard', [L('排期表', 'schedule'), L('归属图', 'ownership map')]],
  ];
  cols.forEach(([name, sub, checks, rev, extra], i) => {
    const x = 20 + i * 244;
    g.box(x, 20, 228, 310, '', { tone: i === 0 ? 'plain' : i === 1 ? 'plain' : 'plain', fill: i === 2 ? '#eef7f4' : '#ffffff' });
    g.text(x + 114, 52, name, { size: 20, weight: 700, anchor: 'middle', color: C.accent, mono: true });
    g.text(x + 114, 76, sub, { size: 12, anchor: 'middle', color: C.gray });
    g.text(x + 14, 108, L('检查', 'checks'), { size: 13, weight: 700 });
    let cx = x + 14, cy = 118;
    for (const [c, isNew] of checks) {
      const w = g.tw(c, 12, true) + 18;
      if (cx + w > x + 216) { cx = x + 14; cy += 34; }
      g.chip(cx, cy, c, { mono: true, size: 12, tone: isNew ? 'accent' : 'plain' });
      cx += w + 6;
    }
    g.text(x + 14, 232, L('审查档', 'review'), { size: 13, weight: 700 });
    g.chip(x + 14, 242, rev, { mono: true, size: 12, tone: 'gray' });
    if (extra.length) { let ex = x + 14; g.text(x + 14, 298, '+', { size: 14, weight: 700 }); ex += 14; for (const e of extra) ex += g.chip(ex, 282, e, { size: 11 }) + 6; }
  });
  g.text(380, 354, L('绿色 = 比上一档多开的检查；nomess status --suggest 给升降档依据', 'green = checks added over the previous size; nomess status --suggest explains when to change'), { size: 12, color: C.gray, anchor: 'middle' });
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

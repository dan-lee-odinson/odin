// VERDA: a watch-only viewer. It plays back one run from a timeline file that
// convert/verda_convert.py wrote, on one mission-elapsed-time (MET) axis.
// It reads only the files beside it, sends nothing and writes nothing. The
// page's Content-Security-Policy refuses every connection.
'use strict';

(function () {
  // SVG's XML namespace name. A name, not an address: nothing is fetched from it.
  const SVG_NS = 'http://www.w3.org/2000/svg';

  const LABEL_W = 230;          // the lane names
  const GUTTER = 70;            // each chart's scale, between the names and the plot
  const PLOT_X = LABEL_W + GUTTER;
  const PAD_R = 18;
  const AXIS_H = 30;
  const GAP = 3;
  const SPEEDS = [1, 2, 5, 10, 20, 60];
  const INTERNAL = new Set(['AGENT_INPUT', 'MODEL_CALL', 'CANDIDATE', 'ANSWER', 'SPEND', 'TOOL_USE']);
  const CHAR_W = 7.1;
  const EDGE_W = 6.4;           // a character of the notes at a lane's edge
  const STRIP_H = 26;           // the strip above a ground seat's age chart
  const CHART_MIN = 36;         // the least a telemetry chart gives up to fit the screen
  const STRING_NAMES = { EPS_SA1_I: 'STRING 1', EPS_SA2_I: 'STRING 2' };

  const $ = (id) => document.getElementById(id);
  const S = {
    tl: null, view: [0, 1], met: 0, playing: false, speed: 10, last: 0,
    showTruth: true, showFuture: false, showInternal: false,
    hits: [], geo: null, feedKey: '', marks: [], ask: null, cites: null,
  };

  // ---- small helpers -------------------------------------------------
  function html(tag, cls, parent, txt) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (txt !== undefined && txt !== null) node.textContent = String(txt);
    if (parent) parent.appendChild(node);
    return node;
  }
  function svg(tag, attrs, parent) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const k in attrs) {
      if (attrs[k] !== undefined && attrs[k] !== null) node.setAttribute(k, attrs[k]);
    }
    if (parent) parent.appendChild(node);
    return node;
  }
  function svgText(parent, x, y, str, cls, anchor) {
    const t = svg('text', { x: x, y: y, class: cls || null, 'text-anchor': anchor || null }, parent);
    t.textContent = String(str);
    return t;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function fit(str, px) {
    const n = Math.floor(px / CHAR_W);
    if (n <= 1) return '';
    return str.length <= n ? str : str.slice(0, n - 1) + '…';
  }
  function places(units, v) {
    const p = { V: 3, A: 2, '%': 1, Hz: 2, s: 0 }[units];
    return p === undefined ? (Number.isInteger(v) ? 0 : 3) : p;
  }
  function num(v, units) {
    if (v === null || v === undefined) return '-';
    if (typeof v !== 'number') return String(v);
    return v.toFixed(places(units, v));
  }
  function fmt(v, units) {
    if (typeof v !== 'number') return num(v, units);
    return num(v, units) + (units && units !== 'n/a' ? ' ' + units : '');
  }
  function words(state) { return String(state).replace(/_/g, ' '); }
  function params(p) {
    if (!p) return '';
    return Object.keys(p).sort().map((k) => k + '=' + p[k]).join(' ');
  }
  function lastAtOrBefore(samples, t) {
    let lo = 0, hi = samples.length - 1, found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (samples[mid][0] <= t) { found = mid; lo = mid + 1; } else { hi = mid - 1; }
    }
    return found < 0 ? null : samples[found];
  }
  function nearest(samples, t, within) {
    const a = lastAtOrBefore(samples, t);
    let best = a;
    if (samples.length) {
      const idx = a ? samples.indexOf(a) : -1;
      const b = samples[idx + 1];
      if (b && (!best || Math.abs(b[0] - t) < Math.abs(best[0] - t))) best = b;
    }
    if (best && within !== undefined && Math.abs(best[0] - t) > within) return null;
    return best;
  }
  function stateKind(state) {
    if (!state || state === 'NONE') return 'none';
    if (state === 'GREEN') return 'good';
    if (state.indexOf('YELLOW') === 0) return 'caution';
    if (state.indexOf('RED') === 0) return 'alarm';
    return 'none';
  }

  // ---- loading ---------------------------------------------------------
  function start() {
    const select = $('run-select');
    const index = window.VERDA_INDEX;
    S.ask = hashOptions();
    for (const s of SPEEDS) {
      const o = html('option', null, $('speed'), s + '×');
      o.value = String(s);
      if (s === S.speed) o.selected = true;
    }
    wireControls();
    if (!Array.isArray(index) || index.length === 0) {
      showBanner('No timeline files yet. Run: python convert/verda_convert.py --all <folder of runs>, then reload this page.', true);
      return;
    }
    for (const entry of index) {
      const o = html('option', null, select, entry.title || entry.id);
      o.value = entry.id;
    }
    const first = index.find((e) => e.id === S.ask.run) || index[0];
    select.value = first.id;
    loadRun(first.id);
  }

  // Link options, for opening at a chosen moment:
  // #run=<id>&met=<s>&future=1&truth=0&view=<from>-<to>
  function hashOptions() {
    const out = {};
    for (const part of location.hash.replace(/^#/, '').split('&')) {
      const m = part.match(/^(run|met|future|truth|view)=([A-Za-z0-9._-]+)$/);
      if (m) out[m[1]] = m[2];
    }
    return out;
  }

  function loadRun(id) {
    const entry = (window.VERDA_INDEX || []).find((e) => e.id === id);
    if (!entry) return;
    window.VERDA_TIMELINES = window.VERDA_TIMELINES || {};
    window.VERDA_BESIDE = window.VERDA_BESIDE || {};
    const files = [entry.file].concat(entry.beside ? [entry.beside.file] : []);
    if (files.some((f) => !/^[A-Za-z0-9._-]+\.js$/.test(f))) { showBanner('Bad timeline file name in the index.', true); return; }
    let waiting = 0;
    const done = () => {
      if (--waiting > 0) return;
      const tl = window.VERDA_TIMELINES[id];
      if (!tl) { showBanner('timelines/' + entry.file + ' did not hold the timeline ' + id + '.', true); return; }
      if (!entry.beside) { show(tl); return; }
      const b = window.VERDA_BESIDE[id];
      if (b && b.run_sha256 === entry.sha256) { show(withBeside(tl, b)); return; }
      show(tl);
      showBanner('The Director’s pass is not shown: timelines/' + entry.beside.file + (b ? ' was made for another conversion of this run.' : ' could not be read.'), true);
    };
    for (const file of files) {
      if (file === entry.file ? window.VERDA_TIMELINES[id] : window.VERDA_BESIDE[id]) continue;
      waiting++;
      const tag = document.createElement('script');
      tag.src = 'timelines/' + file;
      tag.onload = done;
      tag.onerror = () => { if (file === entry.file) showBanner('Could not read timelines/' + file + '. Run the converter again.', true); else done(); };
      document.head.appendChild(tag);
    }
    if (!waiting) { waiting = 1; done(); }
  }

  // A run beside the Director's pass comes in two files: the run's own timeline,
  // which an animation clip pins by its SHA-256, and what pairing adds to it
  // (his pass, the scenario's commands, the lanes they take). This puts them
  // together, as the converter checked they would.
  function withBeside(tl, b) {
    const out = Object.assign({}, tl);
    for (const key of ['sources', 'header', 'series']) out[key] = Object.assign({}, tl[key], b.add[key]);
    for (const key of Object.keys(b['new'])) out[key] = b['new'][key];
    out.integrity = (tl.integrity || []).concat(b.append.integrity || []);
    for (const key of ['title', 'met_range', 'lanes']) out[key] = b[key];
    return out;
  }

  function showBanner(msg, bad) {
    const b = $('banner');
    b.hidden = !msg;
    b.textContent = msg || '';
    b.className = 'banner' + (bad ? ' bad' : '');
  }

  function show(tl) {
    S.tl = tl;
    S.playing = false;
    S.view = openingView(tl);
    S.met = S.view[0];
    S.feedKey = '';
    const ask = S.ask && S.ask.run === tl.id ? S.ask : {};
    S.ask = null;
    if (ask.view) {
      const v = ask.view.split('-').map(Number);
      if (v.length === 2 && v[0] < v[1]) S.view = [Math.max(tl.met_range[0], v[0]), Math.min(tl.met_range[1], v[1])];
    }
    if (ask.met && !isNaN(Number(ask.met))) S.met = clamp(Number(ask.met), tl.met_range[0], tl.met_range[1]);
    if (ask.future === '1') S.showFuture = true;
    if (ask.truth === '0') S.showTruth = false;
    $('chk-future').checked = S.showFuture;
    $('chk-truth').checked = S.showTruth;
    buildIndex(tl);
    const scrub = $('scrub');
    scrub.min = String(tl.met_range[0]);
    scrub.max = String(tl.met_range[1]);
    history.replaceState(null, '', '#run=' + tl.id);
    drawHeader(tl);
    drawLegend(tl);
    drawCoverage(tl);
    setupClip(tl);
    render();
    setMet(S.met);
    inspect('Record', 'Hover over anything on the timeline to see what it is. Click it to show its record here.');
  }

  // Cross-references the page needs: records in MET order, and every moment worth stepping to.
  function buildIndex(tl) {
    tl._records = Object.keys(tl.records).map((k) => tl.records[k]).sort((a, b) => a.record_id - b.record_id);
    const marks = new Set();
    for (const e of tl.events) if (typeof e.met_s === 'number') marks.add(e.met_s);
    for (const r of tl.requests) {
      for (const k of ['met_s', 'decision_met_s', 'voided_met_s', 'dispatch_met_s', 'outcome_met_s']) {
        if (typeof r[k] === 'number') marks.add(r[k]);
      }
    }
    for (const s of tl.spans) if (typeof s.start === 'number') marks.add(s.start);
    for (const c of (tl.pass_commands || []).concat(tl.scenario_commands || [])) {
      if (c.met_s >= tl.met_range[0] && c.met_s <= tl.met_range[1]) marks.add(c.met_s);
      if (typeof c.outcome_met_s === 'number') marks.add(c.outcome_met_s);
    }
    S.marks = Array.from(marks).sort((a, b) => a - b);
  }

  // The Director's own pass, when the timeline holds one: a separate flight on the same MET axis.
  function passInfo(tl) { return (tl.header || {}).pass || null; }
  function passOnly(tl) { return !!(tl.header || {}).pass_only; }
  // The checks of files that carry no hash chain: his pass files, and the scenario's scripted commands.
  function fileCheck(c) { return c.kind === 'pass_files' || c.kind === 'scripted_file'; }
  function integrityOk(c) { return fileCheck(c) ? !!c.ok : (c.chain === 'VERIFIED' && c.head !== 'DIFFERS'); }

  // ---- header, legend, coverage -----------------------------------------
  function drawHeader(tl) {
    const h = tl.header || {};
    $('title').textContent = tl.title + (h.scenario_id ? '  ·  scenario ' + h.scenario_id : '');
    const badges = $('badges');
    clear(badges);
    const add = (txt, cls, tip) => { const b = html('span', 'badge' + (cls ? ' ' + cls : ''), badges, txt); if (tip) b.title = tip; };
    if (h.phase !== undefined && h.phase !== null) add('Phase ' + h.phase);
    if (h.seat) add(h.seat === 'ONBOARD' ? 'Onboard seat' : 'Ground seat');
    if (h.model_config) add('Model ' + h.model_config, null, h.model_id ? 'Model ' + h.model_id : null);
    if (h.mode) add(h.mode === 'DEVELOPMENT' ? 'Development mode' : h.mode, h.mode === 'DEVELOPMENT' ? 'caution' : null);
    for (const c of tl.integrity || []) {
      const ok = integrityOk(c);
      if (fileCheck(c)) {
        add(c.label + (ok ? ' read' : ' FAILED its check'), ok ? 'good' : 'alarm', (c.problems || []).join('\n') || c.summary);
        continue;
      }
      const what = c.label + (ok ? ' verified' : ' FAILED its check');
      add(what, ok ? 'good' : 'alarm', (c.problems || []).join('\n') || (c.records + ' records, hash chain' + (c.head ? ' and head ' + c.head.toLowerCase() : '')));
    }
    if (h.run_end) add('Ended ' + h.run_end.reason, h.run_end.reason === 'COMPLETE' ? null : 'alarm');
    const broken = (tl.integrity || []).filter((c) => !integrityOk(c));
    const pass = passInfo(tl);
    if (broken.length) {
      showBanner('A check of this run folder failed: ' + broken.map((c) => c.label).join(', ') + '. What is shown may not be what was recorded.', true);
    } else if (passOnly(tl)) {
      showBanner('No ODIN run of this pass yet: the Director’s flight alone, flown on ' + pass.date + ' in HUGINN' + (pass.plan_id ? ', beside the contact window of plan ' + pass.plan_id : '') + '.', false);
    } else if (h.mode === 'DEVELOPMENT' || h.model_config === 'stand_in') {
      showBanner('Practice run: ' + (h.model_config === 'stand_in' ? 'ODIN’s model was the scripted stand-in' : 'development mode') + ', not a scored run.' + (pass ? ' Beside it, the Director’s own pass of this scenario, flown on ' + pass.date + ' in HUGINN: a separate flight on the same MET axis.' : ''), false);
    } else {
      showBanner('', false);
    }
    const w = $('warnings');
    w.hidden = !(tl.warnings && tl.warnings.length);
    w.textContent = (tl.warnings || []).length ? 'Converter warnings: ' + tl.warnings.join(' | ') : '';
  }

  function drawLegend(tl) {
    const lg = $('legend');
    clear(lg);
    const key = (draw, label) => {
      const k = html('span', 'key', lg);
      const s = svg('svg', { width: 34, height: 14 }, k);
      draw(s);
      html('span', null, k, label);
    };
    const pass = passInfo(tl);
    if (!passOnly(tl)) {
      key((s) => { svg('line', { x1: 2, y1: 7, x2: 32, y2: 7, class: 'series-odin' }, s); svg('circle', { cx: 17, cy: 7, r: 4, class: 'dot-obs ls-GREEN' }, s); }, 'In ODIN’s turn bundles (dot: a turn’s observation)');
      if (tl.sources && tl.sources.truth) key((s) => { svg('line', { x1: 2, y1: 7, x2: 32, y2: 7, class: 'series-truth' }, s); }, 'Simulator truth, never seen by ODIN');
    }
    if (pass) key((s) => { svg('line', { x1: 2, y1: 7, x2: 32, y2: 7, class: 'series-director' }, s); marker(s, 'triangle', 17, 7, 4, 'sev-director'); }, 'The Director’s pass ' + pass.name);
    if ((tl.scenario_commands || []).length) key((s) => { marker(s, 'diamond', 17, 7, 4.5, 'scenario-mark'); }, 'The scenario’s commands, not his');
    key((s) => { svg('rect', { x: 2, y: 1, width: 30, height: 5, class: 'band-caution' }, s); svg('rect', { x: 2, y: 7, width: 30, height: 6, class: 'band-alarm' }, s); }, 'Yellow and red limits');
    if (!passOnly(tl)) key((s) => { svg('path', { d: 'M4 7 L10 1 L16 7 L10 13 Z', class: 'sev-odin' }, s); }, 'ODIN’s turn');
  }

  function drawCoverage(tl) {
    const rows = tl.record_types || [];
    const shown = rows.filter((r) => r.shown_as && !/^Not shown/.test(r.shown_as)).length;
    $('coverage').hidden = !rows.length;
    $('coverage-summary').textContent = 'Record types: ' + shown + ' of ' + rows.length + ' the contract lists are shown';
    const t = $('coverage-table');
    clear(t);
    for (const r of rows) {
      const tr = html('tr', null, t);
      html('td', null, tr, r.type);
      html('td', null, tr, r.count);
      html('td', null, tr, r.shown_as || 'NOT HANDLED');
    }
  }

  // ---- the timeline drawing ---------------------------------------------
  function laneHeight(lane, tl) {
    if (lane.kind === 'requests') return Math.max(lane.height || 40, requestRows(tl).rows * 24 + 12);
    if (lane.kind === 'pass-commands') return Math.max(lane.height || 40, passRows(tl).rows * 24 + 12);
    if (lane.kind === 'scenario-commands') return Math.max(lane.height || 36, scenarioRows(tl).rows * 24 + 12);
    if (lane.kind === 'chart' && lane.id !== 'staleness') return (lane.height || 40) - (S.chartTrim || 0);
    return lane.height || 40;
  }

  // Where a chain's label goes: after its last mark, or, when that would run past the
  // plot's right edge, before its first mark if the plot has room there.
  function labelPlace(x0, x1, text) {
    const w = text.length * CHAR_W;
    const right = S.geo ? PLOT_X + S.geo.plotW : Infinity;
    if (x1 + 10 + w > right && x0 - 10 - w >= PLOT_X) return { x: x0 - 10, anchor: 'end', start: x0 - 10 - w, end: x1 + 6 };
    return { x: x1 + 10, anchor: 'start', start: x0, end: x1 + 12 + w };
  }

  function requestRows(tl) {
    const x = S.geo ? S.geo.x : (m) => m;
    const placed = [];
    const ends = [];
    for (const r of tl.requests) {
      const mets = ['met_s', 'decision_met_s', 'voided_met_s', 'dispatch_met_s', 'outcome_met_s']
        .map((k) => r[k]).filter((v) => typeof v === 'number');
      const place = labelPlace(x(Math.min.apply(null, mets)), x(Math.max.apply(null, mets)), r.summary || '');
      let row = ends.findIndex((e) => e < place.start - 6);
      if (row < 0) { row = ends.length; ends.push(place.end); } else { ends[row] = place.end; }
      placed.push({ r: r, row: row, mets: mets, place: place });
    }
    return { rows: Math.max(1, ends.length), placed: placed };
  }

  // The Director's commands, laid out like ODIN's requests: one row per command
  // unless it fits after the one before it.
  function passRows(tl) {
    const x = S.geo ? S.geo.x : (m) => m;
    const placed = [];
    const ends = [];
    for (const c of tl.pass_commands || []) {
      const mets = [c.met_s].concat(typeof c.outcome_met_s === 'number' ? [c.outcome_met_s] : []);
      const place = labelPlace(x(Math.min.apply(null, mets)), x(Math.max.apply(null, mets)), c.summary);
      let row = ends.findIndex((e) => e < place.start - 6);
      if (row < 0) { row = ends.length; ends.push(place.end); } else { ends[row] = place.end; }
      placed.push({ c: c, row: row, mets: mets, place: place });
    }
    return { rows: Math.max(1, ends.length), placed: placed };
  }

  // The scenario's own commands in view, laid out the same way. Those outside the
  // view are named at its edge instead, each edge's note taking a place in a row.
  function scenarioRows(tl) {
    const x = S.geo ? S.geo.x : (m) => m;
    const plotW = S.geo ? S.geo.plotW : 0;
    const placed = [], ends = [];
    const all = tl.scenario_commands || [];
    const before = all.filter((c) => c.met_s < S.view[0]), after = all.filter((c) => c.met_s > S.view[1]);
    const notes = [];
    if (before.length) {
      const text = edgeText(before, true);
      ends.push(PLOT_X + 8 + text.length * EDGE_W);
      notes.push({ c: before[before.length - 1], text: text, left: true, row: 0 });
    }
    for (const c of all) {
      if (c.met_s < S.view[0] || c.met_s > S.view[1]) continue;
      const place = labelPlace(x(c.met_s), x(Math.max(c.met_s, typeof c.outcome_met_s === 'number' ? c.outcome_met_s : c.met_s)), c.summary);
      let row = ends.findIndex((e) => e < place.start - 6);
      if (row < 0) { row = ends.length; ends.push(place.end); } else { ends[row] = place.end; }
      placed.push({ c: c, row: row, place: place });
    }
    if (after.length) {
      const text = edgeText(after, false);
      let row = ends.findIndex((e) => e < PLOT_X + plotW - 8 - text.length * EDGE_W - 6);
      if (row < 0) { row = ends.length; ends.push(PLOT_X + plotW); }
      notes.push({ c: after[0], text: text, left: false, row: row });
    }
    return { rows: Math.max(1, ends.length), placed: placed, notes: notes };
  }

  function edgeText(list, left) {
    const c = left ? list[list.length - 1] : list[0];
    const more = list.length > 1 ? ' (and ' + (list.length - 1) + ' more)' : '';
    const what = (c.command + ' ' + params(c.parameters)).trim() + ', ' + c.when + more;
    return left ? '◂ earlier: MET ' + c.met_s + ' ' + what : 'later: MET ' + c.met_s + ' ' + what + ' ▸';
  }

  function patterns(defs) {
    const grid = svg('pattern', { id: 'grid', width: 24, height: 24, patternUnits: 'userSpaceOnUse' }, defs);
    svg('path', { d: 'M24 0 H0 V24', class: 'grid-fine' }, grid);
    const hatch = (id, size, cls) => {
      const p = svg('pattern', { id: id, width: size, height: size, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' }, defs);
      svg('rect', { width: size, height: size, class: cls + '-bg' }, p);
      svg('line', { x1: 0, y1: 0, x2: 0, y2: size, class: cls + '-line' }, p);
    };
    hatch('hatch-alarm', 5, 'hatch-alarm');
    hatch('hatch-caution', 9, 'hatch-caution');
    hatch('hatch-truth', 12, 'hatch-truth');
  }

  function render() {
    const tl = S.tl;
    if (!tl) return;
    const host = $('lanes');
    clear(host);
    S.hits = [];
    const width = Math.max(960, host.clientWidth - 2);
    const plotW = width - PLOT_X - PAD_R;
    const v0 = S.view[0], v1 = S.view[1];
    const x = (m) => PLOT_X + (m - v0) / (v1 - v0) * plotW;
    S.geo = { x: x, plotW: plotW, width: width };
    const lanes = tl.lanes.filter((l) => !(l.source === 'truth' && !S.showTruth));
    const sum = () => lanes.reduce((t, l) => t + laneHeight(l, tl) + GAP, 2 * AXIS_H);
    // A run whose chains need more rows than most (P1's, with two requests and two commands of
    // the Director's and of the scenario's close together) still fits the screen: its telemetry
    // charts each give up a few pixels, down to CHART_MIN.
    S.chartTrim = 0;
    const charts = lanes.filter((l) => l.kind === 'chart' && l.id !== 'staleness');
    const excess = sum() - host.clientHeight;
    if (excess > 0 && charts.length) {
      const room = Math.min.apply(null, charts.map((l) => (l.height || 40) - CHART_MIN));
      S.chartTrim = clamp(Math.ceil(excess / charts.length), 0, Math.max(0, room));
    }
    const total = sum();
    const root = svg('svg', { width: width, height: total, viewBox: '0 0 ' + width + ' ' + total }, host);
    const defs = svg('defs', {}, root);
    patterns(defs);
    const clip = svg('clipPath', { id: 'plot-clip' }, defs);
    svg('rect', { x: PLOT_X, y: 0, width: plotW, height: total }, clip);

    drawAxis(root, 0, total, true);
    let y = AXIS_H;
    lanes.forEach((lane, i) => {
      const h = laneHeight(lane, tl);
      svg('rect', { x: 0, y: y, width: width, height: h, class: 'lane-bg' + (i % 2 ? ' alt' : '') }, root);
      svg('rect', { x: PLOT_X, y: y, width: plotW, height: h, fill: 'url(#grid)' }, root);
      if (lane.id === 'truth') {
        svg('rect', { x: PLOT_X, y: y, width: plotW, height: h, fill: 'url(#hatch-truth)' }, root);
        svg('rect', { x: 1.5, y: y + 1, width: width - 3, height: h - 2, class: 'truth-frame' }, root);
      }
      svg('line', { x1: 0, y1: y + h + GAP / 2, x2: width, y2: y + h + GAP / 2, class: 'lane-rule' }, root);
      drawLaneLabel(root, lane, y, h);
      const g = svg('g', { 'clip-path': 'url(#plot-clip)' }, root);
      if (lane.kind === 'track') drawTrack(g, lane, y, h);
      else if (lane.kind === 'requests') drawRequests(g, lane, y, h);
      else if (lane.kind === 'pass-commands') drawPassCommands(g, lane, y, h);
      else if (lane.kind === 'scenario-commands') drawScenarioCommands(g, lane, y, h);
      else if (lane.kind === 'chart') drawChart(g, root, lane, y, h);
      else if (lane.kind === 'state') drawState(g, lane, y, h);
      y += h + GAP;
    });
    drawAxis(root, y, total, false);

    const over = svg('g', {}, root);
    S.geo.veil = svg('rect', { x: 0, y: AXIS_H, width: 0, height: total - 2 * AXIS_H, class: 'veil' }, over);
    S.geo.head = svg('line', { x1: 0, y1: AXIS_H - 4, x2: 0, y2: total - AXIS_H + 4, class: 'playhead' }, over);
    S.geo.tag = svg('rect', { x: 0, y: 4, width: 64, height: 20, class: 'playhead-tag' }, over);
    S.geo.tagText = svgText(over, 0, 18.5, '', 'playhead-tag-text', 'middle');
    S.geo.total = total;
    root.addEventListener('mousemove', onMove);
    root.addEventListener('mouseleave', () => { $('tooltip').hidden = true; });
    root.addEventListener('click', onClick);
    placeHead();
  }

  function tickStep(span, px) {
    const steps = [1, 2, 5, 10, 15, 20, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200];
    for (const s of steps) if (span / s * 90 <= px) return s;
    return steps[steps.length - 1];
  }

  function drawAxis(root, y, total, top) {
    const g = S.geo;
    const v0 = S.view[0], v1 = S.view[1];
    const step = tickStep(v1 - v0, g.plotW);
    const minor = step / 5;
    const edge = top ? y + AXIS_H - 1 : y + 1;
    svg('line', { x1: PLOT_X, y1: edge, x2: PLOT_X + g.plotW, y2: edge, class: 'axis-rule' }, root);
    for (let m = Math.ceil(v0 / minor) * minor; m <= v1; m += minor) {
      const xx = g.x(m);
      const major = Math.abs(m / step - Math.round(m / step)) < 1e-6;
      svg('line', { x1: xx, y1: edge, x2: xx, y2: edge + (top ? -1 : 1) * (major ? 7 : 3.5), class: 'axis-tick' }, root);
      if (major) {
        if (top) svg('line', { x1: xx, y1: AXIS_H, x2: xx, y2: total - AXIS_H, class: 'grid-line' }, root);
        svgText(root, xx, top ? y + 16 : y + 21, String(m), 'axis-text', 'middle');
      }
    }
    svgText(root, 14, top ? y + 19 : y + 20, 'MET  S', 'axis-name');
    const hit = svg('rect', { x: PLOT_X, y: y, width: g.plotW, height: AXIS_H, class: 'axis-hit' }, root);
    hit.setAttribute('data-seek', '1');
  }

  function drawLaneLabel(root, lane, y, h) {
    const mark = lane.id === 'truth' ? ' truth' : (lane.source === 'director' ? ' director' : (lane.source === 'scenario' ? ' scenario' : ''));
    svg('rect', { x: 0, y: y + 7, width: 3, height: 13, class: 'lane-mark' + mark }, root);
    const label = svgText(root, 14, y + 18, lane.label, 'lane-label');
    if (lane.note) {
      label.classList.add('hit');
      label.setAttribute('data-hit', addHit(lane.label, lane.note, { note: lane.label + '\n\n' + lane.note }));
    }
    let sub = null;
    if (lane.points && (lane.kind === 'chart' || lane.kind === 'state')) sub = lane.points.join('  ');
    if (lane.id === 'truth') sub = 'NEVER SEEN BY ODIN';
    if (lane.note_short) sub = lane.note_short;
    const keyed = lane.kind === 'chart' && (lane.points || []).length > 1 && h >= CHART_MIN;
    if (keyed) {
      // Which mark is which string, for when the two read the same. It takes the
      // place of the point names; the hover names each string's point.
      let kx = 14;
      lane.points.forEach((pt, i) => {
        marker(root, i ? 'ring' : 'circle', kx + 5, y + 29, i ? 5 : 3.5, 'dot-obs ls-NONE' + (i ? ' p1' : ''));
        const t = svgText(root, kx + 14, y + 33, STRING_NAMES[pt] || pt, 'key-text');
        kx += 26 + t.textContent.length * 7;
      });
    } else if (sub && h >= 34) {
      // A lane with no scale may run its note into the scale's gutter.
      svgText(root, 14, y + 33, fit(sub, (lane.kind === 'chart' ? LABEL_W : PLOT_X) - 22), lane.id === 'truth' ? 'lane-sub truth' : 'lane-sub');
    }
  }

  function addHit(title, tip, payload) {
    S.hits.push({ title: title, tip: tip, payload: payload });
    return String(S.hits.length - 1);
  }

  function rowY(lane, y, h, row) {
    const rows = lane.rows || 1;
    const rh = (h - 6) / rows;
    return { top: y + 3 + rh * (row || 0), h: rh };
  }

  function marker(g, shape, cx, cy, r, cls) {
    if (shape === 'circle') return svg('circle', { cx: cx, cy: cy, r: r, class: cls }, g);
    if (shape === 'ring') return svg('circle', { cx: cx, cy: cy, r: r, class: cls + ' ring' }, g);
    if (shape === 'square') return svg('rect', { x: cx - r, y: cy - r, width: 2 * r, height: 2 * r, class: cls }, g);
    if (shape === 'triangle') return svg('path', { d: 'M' + cx + ' ' + (cy - r - 1) + ' L' + (cx + r + 1) + ' ' + (cy + r) + ' L' + (cx - r - 1) + ' ' + (cy + r) + ' Z', class: cls }, g);
    if (shape === 'flag') return svg('path', { d: 'M' + (cx - 1) + ' ' + (cy + r + 2) + ' L' + (cx - 1) + ' ' + (cy - r - 2) + ' L' + (cx + r + 3) + ' ' + (cy - r / 2) + ' L' + (cx) + ' ' + (cy) + ' Z', class: cls }, g);
    if (shape === 'x') {
      const p = svg('path', { d: 'M' + (cx - r) + ' ' + (cy - r) + ' L' + (cx + r) + ' ' + (cy + r) + ' M' + (cx + r) + ' ' + (cy - r) + ' L' + (cx - r) + ' ' + (cy + r), class: cls }, g);
      p.setAttribute('stroke-width', '3');
      return p;
    }
    return svg('path', { d: 'M' + cx + ' ' + (cy - r - 1) + ' L' + (cx + r + 1) + ' ' + cy + ' L' + cx + ' ' + (cy + r + 1) + ' L' + (cx - r - 1) + ' ' + cy + ' Z', class: cls }, g);
  }

  // A short name for a turn's mark: "T4 command", "T2 report". The hover has the rest.
  function shortLabel(e) {
    if (e.lane !== 'turns') return e.label;
    return e.label.split(' ').slice(0, 2).join(' ');
  }

  function drawTrack(g, lane, y, h) {
    const tl = S.tl, x = S.geo.x;
    const truth = lane.id === 'truth';
    const below = lane.id === 'turns';  // marks on top, their names on a row beneath
    const marks = svg('g', {}, g);
    const names = svg('g', {}, g);  // drawn after the marks, so no mark covers a name
    const spans = tl.spans.filter((s) => s.lane === lane.id && typeof s.start === 'number' && typeof s.end === 'number');
    for (const s of spans) {
      const ry = rowY(lane, y, h, s.row);
      const x0 = x(s.start), x1 = x(s.end);
      const rect = svg('rect', { x: x0, y: ry.top + 1, width: Math.max(2, x1 - x0), height: ry.h - 2,
        class: 'span hit sev-' + s.severity + (truth ? ' truth' : '') }, marks);
      rect.setAttribute('data-hit', addHit(s.label, s.label + '\nMET ' + s.start + ' to ' + s.end + (truth ? '\nSimulator truth, never seen by ODIN' : ''), { span: s }));
      if (ry.h < 12) continue;
      const inside = fit(s.label, x1 - x0 - 10);
      if (inside === s.label) {
        svgText(names, Math.max(x0, PLOT_X) + 6, ry.top + ry.h / 2 + 4.5, inside, 'span-label');
      } else {
        // Too short to hold its name: write it after the span, up to the next span on its row.
        const next = spans.filter((o) => (o.row || 0) === (s.row || 0) && o.start >= s.end).sort((a, b) => a.start - b.start)[0];
        const room = (next ? x(next.start) : S.geo.width - PAD_R) - x1 - 10;
        const outside = fit(s.label, room);
        if (outside) svgText(names, x1 + 5, ry.top + ry.h / 2 + 4.5, outside, 'ev-label');
      }
    }
    const lastEnd = {};
    const events = tl.events.filter((e) => e.lane === lane.id && typeof e.met_s === 'number').sort((a, b) => a.met_s - b.met_s);
    for (const e of events) {
      const ry = rowY(lane, y, h, e.row);
      const cx = x(e.met_s);
      const cy = below ? ry.top + 10 : ry.top + ry.h / 2;
      const r = below ? 5.5 : Math.min(6, ry.h / 2 - 2);
      const m = marker(marks, e.shape, cx, cy, r, 'hit sev-' + e.severity);
      m.setAttribute('data-hit', addHit(e.label, eventTip(e), { event: e }));
      if (e.severity === 'quiet') continue;
      const key = e.row || 0;
      const text = shortLabel(e);
      if (below) {
        // A turn's name goes after its mark. Near the right edge, where it will not fit
        // there, it is written before the mark, ending at it, if the row is clear; where
        // it fits neither way, the turn's number alone is written. The hover has the rest.
        const clearFrom = lastEnd[key] === undefined ? -Infinity : lastEnd[key] + 8;
        const room = S.geo.width - 26;
        let name = null, x0 = 0, end = false;
        for (const n of [text, text.split(' ')[0]]) {
          const w = n.length * CHAR_W;
          if (cx - 4 >= clearFrom && cx - 4 + w <= room) { name = n; x0 = cx - 4; break; }
          if (cx - 4 + w > room && cx + 4 - w >= clearFrom) { name = n; x0 = cx + 4 - w; end = true; break; }
        }
        if (name === null) continue;
        const t = end ? svgText(names, cx + 4, ry.top + ry.h - 4, name, 'ev-label', 'end')
                      : svgText(names, x0, ry.top + ry.h - 4, name, 'ev-label');
        t.classList.add('hit');
        t.setAttribute('data-hit', m.getAttribute('data-hit'));
        lastEnd[key] = x0 + name.length * CHAR_W;
      } else if (lastEnd[key] === undefined || cx > lastEnd[key] + 6) {
        const next = events.find((o) => o.met_s > e.met_s && (o.row || 0) === key);
        const room = next ? x(next.met_s) - cx - 16 : S.geo.width - cx - 30;
        const label = fit(text, Math.min(room, 420));
        // A name that will not fit after its mark, near the right edge or before the next
        // mark on its row, is written whole before it, if the row is clear there.
        const clear = cx - r - 4 - (lastEnd[key] === undefined ? PLOT_X : lastEnd[key] + 6);
        let t = null;
        if (label !== text && fit(text, Math.min(clear, 420)) === text) {
          t = svgText(names, cx - r - 4, cy + 4.5, text, 'ev-label', 'end');
          lastEnd[key] = cx + r;
        } else if (label) {
          t = svgText(names, cx + r + 4, cy + 4.5, label, 'ev-label');
          lastEnd[key] = cx + r + 4 + label.length * CHAR_W;
        }
        // A name opens what its mark opens, as a request's or a command's does.
        if (t) {
          t.classList.add('hit');
          t.setAttribute('data-hit', m.getAttribute('data-hit'));
        }
      }
    }
    if (truth) {
      // On a plate of its own, so no span's hatch runs through the words.
      const tag = svgText(g, S.geo.width - PAD_R - 6, y + h - 6, 'SIMULATOR TRUTH · NEVER SEEN BY ODIN', 'truth-tag', 'end');
      const b = tag.getBBox();
      g.insertBefore(svg('rect', { x: b.x - 5, y: b.y - 1, width: b.width + 10, height: b.height + 2, class: 'truth-plate' }, g), tag);
    }
  }

  function eventTip(e) {
    let tip = e.label + '\nMET ' + e.met_s;
    if (e.text) tip += '\n“' + e.text + '”';
    if (e.turn_id !== undefined && e.turn_id !== null) {
      const turn = S.tl.turns[String(e.turn_id)];
      if (turn && turn.summary) tip += '\n' + turn.summary;
    }
    if (e.lane === 'truth') tip += '\nSimulator truth, never seen by ODIN';
    return tip + '\n(click for the record)';
  }

  function drawRequests(g, lane, y, h) {
    const x = S.geo.x;
    const layout = requestRows(S.tl);
    if (!S.tl.requests.length) svgText(g, PLOT_X + 10, y + h / 2 + 4, 'ODIN sent no command request in this run.', 'note-text');
    for (const p of layout.placed) {
      const r = p.r;
      const cy = y + 6 + p.row * 24 + 12;
      const x0 = x(Math.min.apply(null, p.mets)), x1 = x(Math.max.apply(null, p.mets));
      const id = addHit(r.summary, requestTip(r), { request: r });
      const line = svg('line', { x1: x0, y1: cy, x2: x1, y2: cy, class: 'chain-line ' + r.status }, g);
      line.setAttribute('data-hit', id);
      const add = (met, shape, cls) => {
        if (typeof met !== 'number') return;
        const m = marker(g, shape, x(met), cy, 5.5, 'hit ' + cls);
        m.setAttribute('data-hit', id);
      };
      add(r.met_s, 'circle', 'sev-odin');
      if (r.decision) add(r.decision_met_s, 'square', r.decision === 'ALLOW' ? 'sev-good' : 'sev-bad');
      if (r.voided) add(r.voided_met_s, 'x', 'sev-bad');
      add(r.dispatch_met_s, 'triangle', 'sev-info');
      if (r.outcome) add(r.outcome_met_s, 'square', r.outcome === 'ACCEPTED' ? 'sev-good' : (r.outcome === 'REJECTED' ? 'sev-bad' : 'sev-warn'));
      const t = svgText(g, p.place.x, cy + 4.5, r.summary, 'ev-label', p.place.anchor);
      t.classList.add('hit');
      t.setAttribute('data-hit', id);
    }
  }

  function drawPassCommands(g, lane, y, h) {
    const x = S.geo.x;
    const layout = passRows(S.tl);
    if (!(S.tl.pass_commands || []).length) svgText(g, PLOT_X + 10, y + h / 2 + 4, 'The Director sent no command in this pass.', 'note-text');
    for (const p of layout.placed) {
      const c = p.c;
      const cy = y + 6 + p.row * 24 + 12;
      const x0 = x(Math.min.apply(null, p.mets)), x1 = x(Math.max.apply(null, p.mets));
      const id = addHit('The Director’s command: ' + c.summary, passCommandTip(c), { passCommand: c });
      const line = svg('line', { x1: x0, y1: cy, x2: x1, y2: cy, class: 'chain-line ' + c.status }, g);
      line.setAttribute('data-hit', id);
      if (typeof c.outcome_met_s === 'number') {
        const o = marker(g, 'square', x(c.outcome_met_s), cy, 5, 'hit ' + (c.status === 'good' ? 'sev-good' : 'sev-bad'));
        o.setAttribute('data-hit', id);
      }
      // His mark goes on top: at the whole-run zoom it sits on the outcome's square.
      const m = marker(g, 'triangle', x(c.met_s), cy, 5.5, 'hit sev-director');
      m.setAttribute('data-hit', id);
      const t = svgText(g, p.place.x, cy + 4.5, c.summary, 'ev-label', p.place.anchor);
      t.classList.add('hit');
      t.setAttribute('data-hit', id);
    }
  }

  // The scenario's own commands, which his pass carried: a hollow mark of their own,
  // never the Director's triangle.
  function drawScenarioCommands(g, lane, y, h) {
    const x = S.geo.x;
    const layout = scenarioRows(S.tl);
    if (lane.empty) svgText(g, PLOT_X + 10, y + h / 2 + 4, lane.empty, 'note-text');
    for (const p of layout.placed) {
      const c = p.c;
      const cy = y + 6 + p.row * 24 + 12;
      const id = addHit('The scenario’s command: ' + c.summary, scenarioCommandTip(c), { scenarioCommand: c });
      if (typeof c.outcome_met_s === 'number') {
        const line = svg('line', { x1: x(c.met_s), y1: cy, x2: x(c.outcome_met_s), y2: cy, class: 'chain-line ' + c.status }, g);
        line.setAttribute('data-hit', id);
        const o = marker(g, 'square', x(c.outcome_met_s), cy, 4, 'hit ' + (c.status === 'good' ? 'sev-good' : 'sev-bad'));
        o.setAttribute('data-hit', id);
      }
      const m = marker(g, 'diamond', x(c.met_s), cy, 5.5, 'hit scenario-mark');
      m.setAttribute('data-hit', id);
      const t = svgText(g, p.place.x, cy + 4.5, c.summary, 'ev-label', p.place.anchor);
      t.classList.add('hit');
      t.setAttribute('data-hit', id);
    }
    for (const n of layout.notes) {
      const cy = y + 6 + n.row * 24 + 12;
      const t = svgText(g, n.left ? PLOT_X + 8 : PLOT_X + S.geo.plotW - 8, cy + 4, n.text, 'edge-note hit', n.left ? 'start' : 'end');
      t.setAttribute('data-hit', addHit('The scenario’s command: ' + n.c.summary, scenarioCommandTip(n.c), { scenarioCommand: n.c }));
    }
  }

  function scenarioCommandTip(c) {
    const w = c.contact_window;
    const lines = ['The scenario’s own command, not the Director’s: ' + (c.command + ' ' + params(c.parameters)).trim() + ' at MET ' + c.met_s,
      'From the scenario file ' + c.source + ', by the scripted-commands input',
      (c.when === 'in contact' ? 'In contact' : (c.when === 'before contact' ? 'Before contact' : 'After contact')) +
        ' (plan ' + c.plan_id + ', MET ' + w.aos_met_s + ' to ' + w.los_met_s + '): his pass carried it; ODIN’s runs ' + (c.kept_in_odins_runs ? 'keep' : 'drop') + ' it',
      'His telemetry next: ' + c.outcome.text + (c.outcome.kind === 'outside' ? '' : ' (derived by VERDA)')];
    if (typeof c.outcome.before_met_s === 'number') lines.push('Compared with his frame before it, at MET ' + c.outcome.before_met_s);
    lines.push(c.refs.length ? '(click for his rows)' : '(click for its entry)');
    return lines.join('\n');
  }

  function passCommandTip(c) {
    return ['The Director sent ' + c.command + ' ' + params(c.parameters) + ' at ' + c.utc.replace('T', ' ').replace(/(\.\d{3})\d*Z$/, '$1 UTC'),
      'MET ' + c.met_s.toFixed(2) + ', ' + c.met_basis,
      'His telemetry next: ' + c.outcome.text + ' (derived by VERDA)',
      '(click for his rows)'].join('\n');
  }

  function requestTip(r) {
    const lines = ['Turn ' + r.turn_id + ': ODIN asked for ' + r.command + ' ' + params(r.parameters) + ' at MET ' + r.met_s];
    if (r.rationale) lines.push('Rationale: ' + r.rationale);
    if (r.decision === 'ALLOW') lines.push('BALDUR-0 allowed it at MET ' + r.decision_met_s + ' (class ' + r['class'] + (r.lease_id ? ', lease ' + r.lease_id : '') + ')');
    if (r.decision === 'REFUSE') {
      const f = r.refusal || {};
      lines.push('BALDUR-0 refused it at MET ' + r.decision_met_s + ': ' + f.check + ' ' + f.reason + (f.detail ? ' (' + f.detail + ')' : ''));
    }
    if (r.voided) lines.push('Voided at dispatch, MET ' + r.voided_met_s + ': ' + r.voided.check + ' ' + r.voided.reason);
    if (typeof r.dispatch_met_s === 'number') lines.push('Dispatched at MET ' + r.dispatch_met_s + ' by ' + r.route);
    if (r.outcome) lines.push('Outcome ' + r.outcome + ' at MET ' + r.outcome_met_s + (r.outcome_point ? ': ' + r.outcome_point.mnemonic + ' = ' + r.outcome_point.value : ''));
    return lines.join('\n') + '\n(click for the records)';
  }

  function laneSeries(lane) {
    return (lane.series || []).map((id) => S.tl.series[id]).filter((s) => s && (s.source !== 'truth' || S.showTruth));
  }

  function chartDomain(lane) {
    const all = (lane.series || []).map((id) => S.tl.series[id]).filter(Boolean);
    let lo = Infinity, hi = -Infinity;
    for (const s of all) for (const p of s.samples) if (typeof p[1] === 'number') { lo = Math.min(lo, p[1]); hi = Math.max(hi, p[1]); }
    if (lane.marks && S.tl.series[lane.marks]) for (const p of S.tl.series[lane.marks].samples) if (typeof p[1] === 'number') { lo = Math.min(lo, p[1]); hi = Math.max(hi, p[1]); }
    if (lo === Infinity) return null;
    const limits = (all[0] || {}).limits;
    if (lane.id === 'staleness') { lo = 0; hi = Math.max(hi + 2, limits && limits.rh ? limits.rh + 4 : 34); }
    let span = hi - lo;
    if (span < 1e-9) span = Math.max(0.1, Math.abs(hi) * 0.05);
    if (limits && lane.id !== 'staleness') {
      for (const k of ['yl', 'yh', 'rl', 'rh']) {
        const t = limits[k];
        if (typeof t === 'number' && t >= lo - span * 0.8 && t <= hi + span * 0.8) { lo = Math.min(lo, t); hi = Math.max(hi, t); }
      }
      // A line that never moves, with no limit near it, keeps the height given above.
      span = Math.max(hi - lo, span);
    }
    return [lo - span * 0.12, hi + span * 0.12];
  }

  // A scale value in the gutter left of the plot, with its unit smaller and dimmer.
  function scaleLabel(root, y, v, units) {
    const t = svg('text', { x: PLOT_X - 8, y: y, class: 'scale-text', 'text-anchor': 'end' }, root);
    t.textContent = num(v, units);
    if (units && units !== 'n/a') {
      const u = svg('tspan', { class: 'scale-unit', dx: 3 }, t);
      u.textContent = units;
    }
  }

  const LIMIT_NAMES = { yh: 'YELLOW HIGH', rh: 'RED HIGH', yl: 'YELLOW LOW', rl: 'RED LOW' };

  function drawChart(g, root, lane, y, h) {
    const x = S.geo.x;
    const dom = chartDomain(lane);
    // A ground seat's age lane keeps a strip above its chart for the states it recorded.
    const top = y + (lane.strip ? 6 + STRIP_H : 6), bottom = y + h - 6;
    const hitRect = svg('rect', { x: PLOT_X, y: y, width: S.geo.plotW, height: h, fill: 'transparent' }, g);
    hitRect.setAttribute('data-chart', lane.id);
    if (!dom) { svgText(g, PLOT_X + 10, y + h / 2 + 4, 'No samples.', 'note-text'); return; }
    const yy = (v) => bottom - (v - dom[0]) / (dom[1] - dom[0]) * (bottom - top);
    const first = S.tl.series[(lane.series || [])[0]];
    const limits = first && first.limits;
    const x0 = PLOT_X, x1 = PLOT_X + S.geo.plotW;
    // The derived age lane names its limits with lines only: an age near 0 s
    // under a hatched field would look like a lane in alarm.
    if (limits && lane.id !== 'staleness') {
      const band = (a, b, cls) => {
        const ya = yy(clamp(a, dom[0], dom[1])), yb = yy(clamp(b, dom[0], dom[1]));
        if (Math.abs(ya - yb) > 0.5) svg('rect', { x: x0, y: Math.min(ya, yb), width: x1 - x0, height: Math.abs(ya - yb), class: cls }, g);
      };
      if (typeof limits.rh === 'number') band(limits.rh, dom[1], 'band-alarm');
      if (typeof limits.yh === 'number') band(limits.yh, typeof limits.rh === 'number' ? limits.rh : dom[1], 'band-caution');
      if (typeof limits.rl === 'number') band(dom[0], limits.rl, 'band-alarm');
      if (typeof limits.yl === 'number') band(typeof limits.rl === 'number' ? limits.rl : dom[0], limits.yl, 'band-caution');
    }
    if (limits) {
      for (const k of ['yh', 'rh', 'yl', 'rl']) {
        const t = limits[k];
        const kind = k[0] === 'r' ? 'alarm' : 'caution';
        if (typeof t === 'number' && t >= dom[0] && t <= dom[1]) {
          svg('line', { x1: x0, y1: yy(t), x2: x1, y2: yy(t), class: 'limit-line ' + kind }, g);
          const name = lane.id === 'staleness' ? (k === 'yh' ? 'YELLOW' : 'RED') + ' ' + t + ' s' : LIMIT_NAMES[k] + ' ' + t;
          // A limit is named at the right end of its line, unless the red one sits just
          // above the yellow one: then the yellow one is named at the left end instead.
          const crowded = k === 'yh' && typeof limits.rh === 'number' && Math.abs(yy(limits.rh) - yy(t)) < 16;
          const above = k[1] === 'h';
          svgText(g, crowded ? x0 + 6 : x1 - 6, above ? yy(t) - 4 : yy(t) + 12, name, 'limit-text ' + kind, crowded ? 'start' : 'end');
        }
      }
    }
    scaleLabel(root, top + 8, dom[1], first && first.units);
    if (lane.id === 'staleness') scaleLabel(root, yy(0) + 4, 0, first && first.units);
    else scaleLabel(root, bottom - 1, dom[0], first && first.units);
    const series = laneSeries(lane);
    const points = lane.points || [];
    const second = (s) => points.indexOf(s.point) > 0;
    for (const s of series) {
      if (s.source !== 'truth') continue;
      const d = path(s.samples, x, yy, 1.5);
      if (d) svg('path', { d: d, class: 'series-truth' + (second(s) ? ' p1' : '') }, g);
    }
    // The Director's pass: his frames, one a second, as a line with no marks.
    for (const s of series) {
      if (s.source !== 'director') continue;
      const d = path(s.samples, x, yy, 1.5);
      if (d) svg('path', { d: d, class: 'series-director' + (second(s) ? ' p1' : '') }, g);
    }
    for (const s of series) {
      if (s.source === 'truth' || s.source === 'director') continue;
      const p = second(s) ? ' p1' : '';
      const d = path(s.samples, x, yy, 1.5);
      if (d) svg('path', { d: d, class: 'series-odin' + p }, g);
      for (const q of s.samples) {
        if (typeof q[1] !== 'number' || q[3] !== 'obs') continue;
        // The mark's shape says the limit state too: circle green or no limit,
        // triangle yellow, square red. String 2 is a ring around string 1's dot.
        const kind = stateKind(q[2]);
        const shape = p ? 'ring' : (kind === 'caution' ? 'triangle' : kind === 'alarm' ? 'square' : 'circle');
        marker(g, shape, x(q[0]), yy(q[1]), p ? 6 : 4, 'dot-obs ls-' + q[2] + p);
      }
    }
    if (lane.marks && S.tl.series[lane.marks]) {
      for (const q of S.tl.series[lane.marks].samples) {
        if (typeof q[1] !== 'number') continue;
        marker(g, 'circle', x(q[0]), yy(q[1]), 4, 'dot-obs ls-' + (q[2] || 'NONE'));
      }
    }
    if (lane.id === 'staleness') {
      const events = S.tl.events.filter((ev) => ev.lane === 'staleness').sort((a, b) => a.met_s - b.met_s);
      const rowCy = (row) => (lane.strip ? y + 11 + row * 13 : top + 6 + row * 12);
      const hits = events.map((e) => {
        const hit = addHit(e.label, eventTip(e), { event: e });
        const m = marker(g, e.shape, x(e.met_s), rowCy(e.row || 0), lane.strip ? 4 : 4.5, 'hit sev-' + e.severity);
        m.setAttribute('data-hit', hit);
        return hit;
      });
      if (lane.strip) {
        // The strip above the chart: its rows named in the scale's gutter, and each
        // row's state written at its first mark and wherever it changes, over the marks.
        [['STALENESS', 0], ['LINK', 1]].forEach(([tag, row]) => svgText(root, PLOT_X - 8, rowCy(row) + 3.5, tag, 'row-tag strip-tag', 'end'));
        const named = {};
        events.forEach((e, i) => {
          const row = e.row || 0;
          const state = e.label.replace(/^Ground (staleness|link) /, '').replace(/, \d+ packets$/, '');
          if (named[row] === state) return;
          named[row] = state;
          // Written past any marks that share its moment, so it starts clear of them.
          const at = Math.max.apply(null, events.filter((o) => (o.row || 0) === row && o.met_s >= e.met_s && o.met_s - e.met_s <= 2).map((o) => x(o.met_s)));
          const late = at + 8 + state.length * CHAR_W > x1;
          const t = svgText(g, late ? x(e.met_s) - 8 : at + 8, rowCy(row) + 4.5, state, 'ev-label hit', late ? 'end' : 'start');
          t.setAttribute('data-hit', hits[i]);
        });
      }
    }
  }

  // A polyline that breaks wherever frames are missing.
  function path(samples, x, yy, maxGap) {
    let d = '', prev = null;
    for (const q of samples) {
      if (typeof q[1] !== 'number') { prev = null; continue; }
      const cmd = prev !== null && q[0] - prev <= maxGap ? 'L' : 'M';
      d += cmd + x(q[0]).toFixed(1) + ' ' + yy(q[1]).toFixed(1) + ' ';
      prev = q[0];
    }
    return d.trim();
  }

  function drawState(g, lane, y, h) {
    const x = S.geo.x;
    const hitRect = svg('rect', { x: PLOT_X, y: y, width: S.geo.plotW, height: h, fill: 'transparent' }, g);
    hitRect.setAttribute('data-chart', lane.id);
    const series = laneSeries(lane);
    const rows = series.length || 1;
    const rh = (h - 6) / rows;
    series.forEach((s, i) => {
      const top = y + 3 + i * rh;
      const sev = s.state_severity || {};
      const truth = s.source === 'truth';
      const director = s.source === 'director';
      // Runs of one value over frames that follow each other. A lone sample (a
      // turn's observation with no history row around it) is a thin tick.
      const runs = [];
      let cur = null;
      for (const q of s.samples) {
        const joined = cur && q[0] - cur.last <= 1.5;
        if (joined && q[1] === cur.value) { cur.last = q[0]; continue; }
        if (cur) cur.end = joined ? q[0] : cur.last + 1;
        cur = { value: q[1], start: q[0], last: q[0], end: null, joinedBefore: !!joined };
        runs.push(cur);
      }
      if (cur) cur.end = cur.last + 1;
      runs.forEach((run, k) => {
        const lone = run.start === run.last && !run.joinedBefore && !(runs[k + 1] && runs[k + 1].joinedBefore);
        const x0 = x(run.start);
        const x1 = lone ? x0 + 4 : Math.max(x(run.end), x0 + 3);
        svg('rect', { x: lone ? x0 - 2 : x0, y: top + 1, width: x1 - x0, height: rh - 2,
          class: 'span state-' + (sev[run.value] || 'info') + (truth ? ' state-truth' : '') }, g);
        const changed = k === 0 || runs[k - 1].value !== run.value;
        const room = lone ? (runs[k + 1] ? x(runs[k + 1].start) - x0 - 10 : 200) : x1 - x0 - 6;
        const label = changed ? fit(String(run.value), room) : '';
        if (label && rh >= 12) svgText(g, x0 + (lone ? 5 : 3), top + rh / 2 + 4, label, lone ? 'ev-label muted' : 'span-label');
      });
      svgText(g, PLOT_X + S.geo.plotW - 4, top + rh / 2 + 4, truth ? 'TRUTH' : director ? 'DIRECTOR' : 'ODIN',
        truth ? 'row-tag truth' : director ? 'row-tag director' : 'row-tag', 'end');
    });
  }

  // ---- interaction ---------------------------------------------------------
  function metAtX(px) {
    return S.view[0] + (px - PLOT_X) / S.geo.plotW * (S.view[1] - S.view[0]);
  }

  function svgPoint(evt) {
    const r = evt.currentTarget.getBoundingClientRect();
    return { x: evt.clientX - r.left, y: evt.clientY - r.top };
  }

  function onMove(evt) {
    const tip = $('tooltip');
    const target = evt.target.closest('[data-hit]');
    let text = null;
    if (target) {
      text = S.hits[Number(target.getAttribute('data-hit'))].tip;
    } else {
      const chart = evt.target.closest('[data-chart]');
      if (chart) text = chartTip(chart.getAttribute('data-chart'), metAtX(svgPoint(evt).x));
      else if (evt.target.closest('[data-seek]')) text = 'Click to move the playhead to MET ' + Math.round(metAtX(svgPoint(evt).x));
    }
    if (!text) { tip.hidden = true; return; }
    tip.textContent = text;
    tip.hidden = false;
    const w = tip.offsetWidth, hgt = tip.offsetHeight;
    tip.style.left = clamp(evt.clientX + 16, 4, window.innerWidth - w - 8) + 'px';
    tip.style.top = clamp(evt.clientY + 16, 4, window.innerHeight - hgt - 8) + 'px';
  }

  function onClick(evt) {
    const target = evt.target.closest('[data-hit]');
    if (target) { inspectHit(S.hits[Number(target.getAttribute('data-hit'))]); return; }
    const chart = evt.target.closest('[data-chart]');
    if (chart) { inspectChart(chart.getAttribute('data-chart'), metAtX(svgPoint(evt).x)); return; }
    if (evt.target.closest('[data-seek]')) { pause(); setMet(Math.round(metAtX(svgPoint(evt).x))); }
  }

  function chartValues(laneId, met) {
    const lane = S.tl.lanes.find((l) => l.id === laneId);
    const out = [];
    const ids = (lane.series || []).concat(lane.marks ? [lane.marks] : []);
    for (const id of ids) {
      const s = S.tl.series[id];
      if (!s || (s.source === 'truth' && !S.showTruth)) continue;
      const q = nearest(s.samples, met, 2);
      const source = s.source === 'truth' ? 'Simulator truth, never seen by ODIN'
        : s.source === 'director' ? (s.derived ? 'Derived by VERDA from the Director’s frames' : 'The Director’s pass, his ground station’s frames')
          : (s.derived ? 'Derived by VERDA from ODIN’s bundles' : 'ODIN’s turn bundles');
      out.push({ series: id, point: s.point, source: source,
        met_s: q ? q[0] : null, value: q ? q[1] : null, limit_state: q ? q[2] : null,
        from: q ? ({ obs: 'a turn’s observation (limit state as recorded)', hist: 'a bundle’s history row (limit state computed by VERDA)', truth: 'truth.jsonl (limit state computed by VERDA)', pass: 'a frame his ground station received (limit state computed by VERDA)', derived: 'derived' }[q[3]] || q[3]) : 'no sample within 2 s', units: s.units });
    }
    return { lane: lane.label, near_met_s: Math.round(met), values: out };
  }

  function chartTip(laneId, met) {
    const v = chartValues(laneId, met);
    const lines = [v.lane + ' near MET ' + v.near_met_s];
    for (const item of v.values) {
      const who = item.source.startsWith('Simulator') ? 'truth    ' : item.series.startsWith('director:') ? 'Director ' : 'ODIN     ';
      const name = STRING_NAMES[item.point] ? STRING_NAMES[item.point].toLowerCase() + ' (' + item.point + ')' : item.point;
      lines.push(who + name + ': ' + (item.value === null ? 'no frame' : fmt(item.value, item.units) + (item.limit_state && item.limit_state !== 'NONE' ? '  ' + words(item.limit_state) : '') + '  (MET ' + item.met_s + ')'));
    }
    return lines.join('\n');
  }

  function inspectChart(laneId, met) {
    inspect('Telemetry near MET ' + Math.round(met), JSON.stringify(chartValues(laneId, met), null, 2));
  }

  function recordsFor(refs) {
    const out = [];
    for (const ref of refs || []) {
      const [kind, id] = ref.split(':');
      if (kind === 'log' && S.tl.records[id]) out.push(S.tl.records[id]);
      else if (kind === 'truth' && S.tl.truth_records[id]) out.push(Object.assign({ shown_as: 'Simulator truth, never seen by ODIN' }, S.tl.truth_records[id]));
      else if (kind === 'turn') out.push(turnDetail(id));
      else if (kind === 'pass' && S.tl.pass_records && S.tl.pass_records[id]) out.push(Object.assign({ shown_as: 'The Director’s pass, a row of his file' }, S.tl.pass_records[id]));
    }
    return out;
  }

  function turnDetail(id) {
    const turn = S.tl.turns[id];
    if (!turn) return { missing_turn: id };
    return {
      turn: turn.turn_id, summary: turn.summary, turn_kind: turn.turn_kind, report_kind: turn.report_kind,
      triggers: turn.triggers, answer: turn.answer, model_calls: turn.model_calls, tool_uses: turn.tools,
      input_tokens: turn.input_tokens, output_tokens: turn.output_tokens, cost_usd: turn.cost_usd,
      bundle_sha256: turn.bundle_sha256, bundle: turn.bundle,
      records: turn.refs.map((r) => S.tl.records[r.split(':')[1]]),
    };
  }

  function inspectHit(hit) {
    const p = hit.payload;
    if (p.event) {
      const recs = recordsFor(p.event.refs);
      if (recs.length === 1 && recs[0] && recs[0].type === 'REPORT') { openReport(recs[0]); return; }
      inspect(hit.title + ' · MET ' + p.event.met_s, JSON.stringify(recs.length === 1 ? recs[0] : recs, null, 2));
    } else if (p.span) {
      const recs = recordsFor(p.span.refs);
      inspect(hit.title, JSON.stringify({ span: { label: p.span.label, start_met_s: p.span.start, end_met_s: p.span.end }, records: recs }, null, 2));
    } else if (p.request) {
      const r = p.request;
      inspect('Request ' + r.request_id, JSON.stringify({ summary: r.summary, records: recordsFor(r.refs) }, null, 2));
    } else if (p.passCommand) {
      const c = p.passCommand;
      inspect('The Director’s command · MET ' + c.met_s.toFixed(2), JSON.stringify({
        summary: c.summary, sent_utc: c.utc, met_s: c.met_s, placed: c.met_basis,
        his_telemetry_next: c.outcome.text + ' (derived by VERDA)', rows: recordsFor(c.refs) }, null, 2));
    } else if (p.scenarioCommand) {
      const c = p.scenarioCommand;
      inspect('The scenario’s command · MET ' + c.met_s, JSON.stringify({
        not_the_directors: 'sent by the scenario itself; his pass carried it',
        summary: c.summary, met_s: c.met_s, command: c.command, parameters: c.parameters,
        when: c.when, contact_window: Object.assign({ plan_id: c.plan_id }, c.contact_window),
        kept_in_odins_runs: c.kept_in_odins_runs, source: c.source,
        his_telemetry_next: c.outcome.text + (c.outcome.kind === 'outside' ? '' : ' (derived by VERDA)'),
        rows: recordsFor(c.refs) }, null, 2));
    } else if (p.record) {
      if (p.record.type === 'REPORT') { openReport(p.record); return; }
      inspect('Record ' + p.record.record_id + ' · ' + p.record.type, JSON.stringify(p.record, null, 2));
    } else if (p.note) {
      inspect('About this lane', p.note);
    }
  }

  function inspect(title, body) {
    closeCites();
    $('inspector-title').textContent = title;
    $('inspector').textContent = body;
    $('inspector').scrollTop = 0;
  }

  // ---- one of ODIN's reports, beside the records it links by ID --------------
  // Only links the records make by ID: the trigger of the report's turn (its turn_id),
  // and the records of each request its actions name (their request_id), as far as
  // the log had come when the report was written. Nothing is matched by time or by
  // text, and nothing is said of whether the report is right.
  function reportLinks(rec) {
    const b = rec.body || {};
    const before = S.tl._records.filter((r) => r.record_id < rec.record_id && r.body);
    const groups = [];
    if (b.turn_id !== undefined && b.turn_id !== null) {
      groups.push({ head: 'The trigger of its turn, turn_id ' + b.turn_id,
        records: before.filter((r) => r.type === 'TRIGGER' && r.body.turn_id === b.turn_id) });
    }
    const ids = [];
    for (const a of b.actions || []) if (a && typeof a.request_id === 'string' && ids.indexOf(a.request_id) < 0) ids.push(a.request_id);
    for (const id of ids) groups.push({ head: 'Its request, request_id ' + id, records: before.filter((r) => r.body.request_id === id) });
    return groups;
  }

  function openReport(rec) {
    const b = rec.body || {};
    const view = $('cites');
    clear(view);
    $('inspector-title').textContent = 'Report ' + (b.report_kind || '') + ' · MET ' + rec.met_s;
    if (typeof b.answer === 'string') {
      html('p', 'cites-label', view, 'The answer, as written in record ' + rec.record_id);
      html('blockquote', 'cites-answer', view, b.answer);
    } else {
      html('p', 'cites-label', view, 'Record ' + rec.record_id + ', as written');
      html('pre', 'cites-answer', view, JSON.stringify(b, null, 2));
    }
    html('p', 'cites-label', view, 'The records it links by ID');
    const groups = reportLinks(rec);
    S.cites = new Set();
    for (const g of groups) {
      const sec = html('section', 'cites-group', view);
      html('h3', null, sec, g.head);
      const list = html('ol', null, sec);
      if (!g.records.length) html('li', 'none', list, 'No record in the log carries it.');
      for (const r of g.records) {
        S.cites.add(r.record_id);
        const li = html('li', null, list);
        li.setAttribute('data-record', String(r.record_id));
        html('span', 't', li, String(r.met_s).padStart(5, ' '));
        html('span', 'k', li, r.type);
        html('span', null, li, describe(r));
        li.title = 'Record ' + r.record_id + ' (click to pick it out)';
        li.addEventListener('click', () => {
          view.querySelectorAll('li.selected').forEach((o) => o.classList.remove('selected'));
          li.classList.add('selected');
          li.scrollIntoView({ block: 'nearest' });
        });
      }
    }
    if (!groups.length) html('p', 'cites-none', view, 'It links no record by ID.');
    $('inspector').hidden = true;
    view.hidden = false;
    view.scrollTop = 0;
    $('btn-cites-close').hidden = false;
    $('side').classList.add('citing');
    S.feedKey = '';
    drawFeed();
  }

  // A clip's full caption, as its renderer wrote it, read as a report is: the readouts
  // give it their place until it is closed.
  function openCaption(c) {
    const view = $('cites');
    clear(view);
    $('inspector-title').textContent = 'Caption';
    html('p', 'cites-label', view, 'The full caption of ' + c.file.replace(/^clips\//, '') + ', as its renderer wrote it');
    html('blockquote', 'cites-answer', view, c.caption);
    S.cites = new Set();
    $('inspector').hidden = true;
    view.hidden = false;
    view.scrollTop = 0;
    $('btn-cites-close').hidden = false;
    $('side').classList.add('citing');
  }

  function closeCites() {
    const open = !!S.cites;
    S.cites = null;
    $('side').classList.remove('citing');
    $('cites').hidden = true;
    $('inspector').hidden = false;
    $('btn-cites-close').hidden = true;
    if (open && S.tl) { S.feedKey = ''; drawFeed(); }
  }

  // A run opens on its pass: its contact windows, flown and planned, and a little
  // either side. Phase 2's runs start at MET 0, and a P2B run's pass comes six
  // hours later; "Whole run" shows all of it.
  function openingView(tl) {
    const r = tl.met_range;
    const c = tl.spans.filter((s) => s.lane === 'contact' && typeof s.start === 'number' && typeof s.end === 'number');
    if (!c.length) return [r[0], r[1]];
    const lo = Math.min.apply(null, c.map((s) => s.start)), hi = Math.max.apply(null, c.map((s) => s.end));
    const pad = Math.max(20, (hi - lo) * 0.04);
    const view = [Math.max(r[0], lo - pad), Math.min(r[1], hi + pad)];
    return view[1] > view[0] ? view : [r[0], r[1]];
  }

  // ---- playback --------------------------------------------------------------
  function setMet(m) {
    const tl = S.tl;
    if (!tl) return;
    S.met = clamp(m, tl.met_range[0], tl.met_range[1]);
    const span = S.view[1] - S.view[0];
    if (S.met > S.view[1] || S.met < S.view[0]) {
      const lo = clamp(S.met - span * 0.25, tl.met_range[0], tl.met_range[1] - span);
      S.view = [lo, lo + span];
      render();
    }
    placeHead();
    $('scrub').value = String(Math.round(S.met));
    drawMet();
    drawNow();
    drawFeed();
    syncClip();
  }

  // ---- the animation pane ---------------------------------------------------
  // A clip rendered from a timeline file plays beside it, locked to the playhead.
  // Its sync file (listed in timelines/index.js by the converter) gives run_id,
  // timeline_sha256, first_frame_met_s, met_step_s and fps: frame n shows MET
  // first_frame_met_s + n * met_step_s, at n / fps seconds into the clip.
  function bareHash(h) { return typeof h === 'string' ? h.replace(/^sha256:/, '').toLowerCase() : ''; }
  function shortHash(h) { return bareHash(h).slice(0, 12) || 'none'; }

  // The clip for the timeline on screen, or why there is none to play.
  function clipFor(tl) {
    const runId = (tl.header || {}).run_id || tl.id;
    const entry = (window.VERDA_INDEX || []).find((e) => e.id === tl.id) || {};
    const have = bareHash(entry.sha256);
    const listed = (window.VERDA_CLIPS || []).filter((c) => c.run_id === runId || (have && bareHash(c.timeline_sha256) === have));
    if (!listed.length) return { listed: false, reason: passOnly(tl) ? 'No ODIN run in this timeline, so no animation clip.' : 'No animation clip for this run.' };
    const fit = listed.filter((c) => c.run_id === runId && have && bareHash(c.timeline_sha256) === have);
    if (fit.length === 1) {
      const c = fit[0];
      if ((c.problems || []).length) return { reason: 'Not played: its sync file ' + c.sync_file + ' has a problem: ' + c.problems[0] + '.' };
      if (!/^clips\/[A-Za-z0-9][A-Za-z0-9._-]*$/.test(c.file || '')) return { reason: 'Not played: the index names no usable clip file for it.' };
      return { clip: c };
    }
    if (fit.length > 1) return { reason: 'Not played: ' + fit.length + ' clips claim this timeline; the converter should be given one.' };
    const c = listed[0];
    if (c.run_id !== runId) return { reason: 'Not played: its sync file names run ' + c.run_id + ', and the timeline on screen is run ' + runId + '.' };
    return { reason: 'Not played: it was rendered from another timeline file. Its sync file pins sha256 ' + shortHash(c.timeline_sha256) +
      '…, and the timeline file on screen is sha256 ' + shortHash(entry.sha256) + '….' };
  }

  function setupClip(tl) {
    const v = $('clip');
    const found = clipFor(tl);
    S.clip = { clip: found.clip || null, frames: 0 };
    v.pause();
    v.onloadedmetadata = null;
    v.onerror = null;
    $('side').classList.remove('with-clip');
    // With no clip listed for it, the pane steps aside and the event log takes its place.
    $('side').classList.toggle('no-clip', found.listed === false);
    $('clip-caption').hidden = !found.clip;
    $('btn-caption').hidden = !(found.clip && found.clip.caption);
    if (!found.clip) {
      v.removeAttribute('src');
      v.load();
      $('clip-box').hidden = true;
      $('clip-panel').className = 'panel frame clip-panel none';
      $('clip-note').textContent = found.reason;
      return;
    }
    const c = found.clip;
    $('side').classList.add('with-clip');
    $('clip-panel').className = 'panel frame clip-panel';
    $('clip-box').hidden = false;
    $('clip-note').textContent = 'Loading ' + c.file + '…';
    v.muted = true;
    v.onloadedmetadata = () => {
      if (S.clip.clip !== c) return;
      S.clip.frames = Math.max(1, Math.round(v.duration * c.fps));
      syncClip();
    };
    v.onerror = () => {
      if (S.clip.clip !== c) return;
      S.clip = { clip: null, frames: 0 };
      $('clip-box').hidden = true;
      $('clip-caption').hidden = true;
      $('clip-note').textContent = 'Could not read timelines/' + c.file + '. Run the converter with --clips again.';
    };
    v.src = 'timelines/' + c.file;
  }

  // How many frames into the clip the playhead's MET falls: (t - first_frame_met_s) / met_step_s.
  function clipFrame(c, t) { return (t - c.first_frame_met_s) / c.met_step_s; }
  function clipMet(c, n) { return c.first_frame_met_s + n * c.met_step_s; }

  // Moves the clip to the playhead: playing at the timeline's rate while it plays,
  // on the playhead's frame while it is paused or scrubbed, and held at its first or
  // last frame outside them.
  function syncClip() {
    const c = S.clip && S.clip.clip;
    const v = $('clip');
    if (!c || !S.clip.frames) return;
    const n = clipFrame(c, S.met);
    const last = S.clip.frames - 1;
    let hold = null;
    if (n < 0) hold = 'Holding at the first frame: the clip starts at MET ' + num(clipMet(c, 0)) + '.';
    else if (n > last) hold = 'Holding at the last frame: the clip ends at MET ' + num(clipMet(c, last)) + '.';
    const frame = hold ? (n < 0 ? 0 : last) : Math.floor(n + 1e-6);
    // The clip plays on its own at the timeline's pace when the browser can play at that rate;
    // otherwise it steps from frame to frame with the playhead.
    const rate = S.speed / (c.fps * c.met_step_s);
    if (S.playing && !hold && rate >= 0.0625 && rate <= 16) {
      v.playbackRate = rate;
      const want = n / c.fps;
      if (v.paused) {
        v.currentTime = want;
        const started = v.play();
        if (started && started.catch) started.catch(() => {});
      } else if (Math.abs(v.currentTime - want) > 2 / c.fps) {
        v.currentTime = want;
      }
    } else {
      if (!v.paused) v.pause();
      // The middle of the frame, so that rounding never shows the one before it.
      const want = (frame + 0.5) / c.fps;
      if (Math.abs(v.currentTime - want) > 0.25 / c.fps) v.currentTime = want;
    }
    // Frames are counted from 1 here, as the sync file's notes and the renderer count them.
    $('clip-note').textContent = (hold ? hold + ' ' : '') + 'Frame ' + (frame + 1) + ' of ' + (last + 1) + ', MET ' + num(clipMet(c, frame)) +
      ' · from timeline sha256 ' + shortHash(c.timeline_sha256) + '…';
  }

  // The boxed MET readout. Its text reads "MET <s> s".
  function drawMet() {
    const box = $('met');
    clear(box);
    html('span', 'k', box, 'MET');
    box.appendChild(document.createTextNode(' '));
    html('span', 'v', box, String(Math.floor(S.met)));
    box.appendChild(document.createTextNode(' '));
    html('span', 'u', box, 's');
  }

  function placeHead() {
    const g = S.geo;
    if (!g || !g.head) return;
    const xx = clamp(g.x(S.met), PLOT_X, PLOT_X + g.plotW);
    g.head.setAttribute('x1', xx);
    g.head.setAttribute('x2', xx);
    g.tag.setAttribute('x', xx - 32);
    g.tagText.setAttribute('x', xx);
    g.tagText.textContent = String(Math.floor(S.met));
    g.veil.setAttribute('x', xx);
    g.veil.setAttribute('width', S.showFuture ? 0 : Math.max(0, PLOT_X + g.plotW - xx));
  }

  function play() {
    if (!S.tl) return;
    if (S.met >= S.tl.met_range[1]) setMet(S.tl.met_range[0]);
    S.playing = true;
    S.last = performance.now();
    $('btn-play').textContent = 'Pause';
    syncClip();
    requestAnimationFrame(step);
  }
  function pause() { S.playing = false; $('btn-play').textContent = 'Play'; syncClip(); }
  function step(ts) {
    if (!S.playing) return;
    const dt = Math.min(0.25, (ts - S.last) / 1000);
    S.last = ts;
    setMet(S.met + dt * S.speed);
    if (S.met >= S.tl.met_range[1]) { pause(); return; }
    requestAnimationFrame(step);
  }

  function jump(dir) {
    pause();
    const t = Math.floor(S.met);
    let target = null;
    if (dir > 0) target = S.marks.find((m) => m > t);
    else for (const m of S.marks) if (m < t) target = m;
    if (target !== null && target !== undefined) setMet(target);
  }

  function zoom(factor) {
    const tl = S.tl;
    if (!tl) return;
    const full = tl.met_range[1] - tl.met_range[0];
    const span = clamp((S.view[1] - S.view[0]) * factor, 20, full);
    const lo = clamp(S.met - span / 2, tl.met_range[0], tl.met_range[1] - span);
    S.view = [lo, lo + span];
    render();
  }

  // ---- the side panels ----------------------------------------------------------
  function spanAt(lane, row, t) {
    return S.tl.spans.find((s) => s.lane === lane && (s.row || 0) === row && s.start <= t && t < s.end) || null;
  }

  function chip(parent, state) {
    if (!state || state === 'NONE') return null;
    return html('span', 'chip ls-' + state, parent, words(state));
  }

  // A segmented, tick-marked level gauge, with its limits marked and named.
  function gauge(parent, value, lo, hi, segments, limits, state) {
    const box = html('div', 'gauge', parent);
    const bar = html('div', 'segs', box);
    const at = (v) => clamp((v - lo) / (hi - lo), 0, 1);
    const kind = stateKind(state);
    for (let i = 0; i < segments; i++) {
      const mid = lo + (i + 0.5) / segments * (hi - lo);
      let zone = '';
      if (limits) {
        if ((typeof limits.rl === 'number' && mid < limits.rl) || (typeof limits.rh === 'number' && mid > limits.rh)) zone = ' z-alarm';
        else if ((typeof limits.yl === 'number' && mid < limits.yl) || (typeof limits.yh === 'number' && mid > limits.yh)) zone = ' z-caution';
      }
      const on = typeof value === 'number' && mid <= value;
      html('i', (on ? 'on k-' + (kind === 'none' ? 'good' : kind) : '') + zone, bar);
    }
    const ticks = html('div', 'ticks', box);
    const named = [];
    if (limits) {
      for (const k of ['rl', 'yl', 'yh', 'rh']) {
        const t = limits[k];
        if (typeof t !== 'number' || t <= lo || t >= hi) continue;
        const m = html('span', 'lim ' + (k[0] === 'r' ? 'alarm' : 'caution'), ticks);
        m.style.left = (at(t) * 100).toFixed(2) + '%';
        named.push(LIMIT_NAMES[k].toLowerCase() + ' ' + t);
      }
    }
    html('span', 'end lo', ticks, String(lo));
    html('span', 'end hi', ticks, String(hi));
    box.title = 'Scale ' + lo + ' to ' + hi + (named.length ? '; limits: ' + named.join(', ') : '');
  }

  // One boxed readout. Its big number is ODIN's, or the Director's when the
  // timeline holds his pass alone; beside ODIN's, a line gives the Director's.
  function readout(grid, spec) {
    const tl = S.tl, t = S.met;
    const main = spec.points.some((p) => tl.series['odin:' + p]) ? 'odin' : 'director';
    const whose = main === 'odin' ? 'ODIN’s frame' : 'His frame';
    const box = html('div', 'ro' + (spec.wide ? ' wide' : ''), grid);
    html('div', 'lab', box, spec.label);
    const line = html('div', 'line', box);
    const subs = html('div', 'sub', box);
    const dirLine = main === 'odin' && passInfo(tl) ? html('div', 'sub dirv', box) : null;
    const truthLine = html('div', 'sub truthv', box);
    let ages = [];
    spec.points.forEach((p, i) => {
      const s0 = tl.series[main + ':' + p];
      const q = s0 ? lastAtOrBefore(s0.samples, t) : null;
      if (i > 0) html('span', 'sep', line, spec.joiner || ' ');
      if (spec.names) html('span', 'nm', line, spec.names[i]);
      html('span', 'val', line, q ? num(q[1], s0.units) : '-');
      if (q && typeof q[1] === 'number' && s0.units && s0.units !== 'n/a' && (!spec.oneUnit || i === spec.points.length - 1)) html('span', 'unit', line, s0.units);
      if (q && !spec.noChip) chip(line, q[2]);
      if (q && p !== 'FRAME_AGE') ages.push(Math.floor(t) - q[0]);
      if (i === 0 && spec.gauge && q) gauge(box, q[1], spec.gauge[0], spec.gauge[1], spec.gauge[2], s0.limits, q[2]);
    });
    const age = ages.length ? Math.max.apply(null, ages) : null;
    html('span', 'age', subs, spec.points[0] === 'FRAME_AGE' ? 'derived by VERDA' : (age === null ? '' : age <= 1 ? whose + ': now' : whose + ': ' + age + ' s old'));
    if (dirLine) {
      let oldest = 0;
      const dv = spec.points.map((p) => {
        const s = tl.series['director:' + p];
        const q = s ? lastAtOrBefore(s.samples, t) : null;
        if (!q) return null;
        if (p !== 'FRAME_AGE') oldest = Math.max(oldest, Math.floor(t) - q[0]);
        const state = q[2] && q[2] !== 'NONE' && q[2] !== 'GREEN' ? ' ' + words(q[2]) : '';
        return num(q[1], s.units) + (s.units && s.units !== 'n/a' ? ' ' + s.units : '') + state;
      }).filter((v) => v !== null);
      dirLine.textContent = dv.length ? 'DIRECTOR ' + dv.join(' · ') + (oldest > 1 ? ' (' + oldest + ' s old)' : '') : 'DIRECTOR no frame yet';
    }
    if (S.showTruth) {
      const tv = spec.points.map((p) => {
        const s = tl.series['truth:' + p];
        const q = s ? lastAtOrBefore(s.samples, t) : null;
        return q ? num(q[1], s.units) + (s.units && s.units !== 'n/a' ? ' ' + s.units : '') : null;
      }).filter((v) => v !== null);
      truthLine.textContent = tv.length ? 'SIM TRUTH ' + tv.join(' · ') : '';
    }
  }

  function drawNow() {
    const tl = S.tl, t = S.met;
    const box = $('now');
    clear(box);
    $('now-title').textContent = 'At MET ' + Math.floor(t) + ' s';
    const facts = html('div', 'facts', box);
    const only = passOnly(tl), pass = passInfo(tl);
    const contact = spanAt('contact', 0, t);
    if (only) {
      html('span', 'fact ' + (contact ? 'good' : 'off'), facts, contact ? 'IN PLAN WINDOW' : 'OUTSIDE PLAN WINDOW');
      html('span', 'fact', facts, pass.plan_id ? 'PLAN ' + pass.plan_id : 'NO PLAN FOUND');
      html('span', 'fact director', facts, 'THE DIRECTOR’S PASS ALONE');
    } else {
      html('span', 'fact ' + (contact ? 'good' : 'off'), facts, contact ? 'IN CONTACT' : 'OUT OF CONTACT');
      const plan = spanAt('authority', 1, t) || spanAt('authority', 0, t);
      html('span', 'fact', facts, plan ? 'PLAN ' + plan.label : 'NO PLAN IN FORCE');
      const rung = spanAt('authority', 2, t);
      if (rung) html('span', 'fact ' + (rung.severity === 'good' ? 'good' : 'alarm'), facts, rung.label);
    }
    const grid = html('div', 'readouts', box);
    const has = (p) => !!(tl.series['odin:' + p] || tl.series['director:' + p]);
    if (has('EPS_BATT_SOC')) readout(grid, { label: 'State of charge', points: ['EPS_BATT_SOC'], gauge: [0, 100, 20] });
    if (has('EPS_BATT_V')) readout(grid, { label: 'Battery voltage', points: ['EPS_BATT_V'], gauge: [6.6, 8.7, 21] });
    if (has('EPS_LOAD_I')) readout(grid, { label: 'Load current', points: ['EPS_LOAD_I'], gauge: [0, 2.5, 25] });
    if (has('EPS_SA1_I')) readout(grid, { label: 'Solar strings 1 · 2', points: ['EPS_SA1_I', 'EPS_SA2_I'], names: ['1', '2'], oneUnit: true, noChip: true });
    if (has('PLD_STATE')) readout(grid, { label: 'Payload', points: ['PLD_STATE', 'PLD_RATE'], joiner: ' · ', noChip: true });
    if (has('EPS_MODE')) readout(grid, { label: 'Spacecraft mode', points: ['EPS_MODE'] });
    if (has('FRAME_AGE')) readout(grid, { label: 'Newest frame age', points: ['FRAME_AGE'] });
    let turn = null;
    for (const k of Object.keys(tl.turns)) { const tt = tl.turns[k]; if (tt.met_s !== null && tt.met_s <= t) turn = tt; }
    const last = html('div', 'ro wide turnbox', grid);
    if (!only) {
      html('div', 'lab', last, 'Latest turn');
      html('div', 'turn', last, turn ? turn.summary : 'none yet');
    }
    if (pass) {
      const cmd = (tl.pass_commands || []).filter((c) => c.met_s <= t).pop();
      if (only) html('div', 'lab', last, 'The Director’s latest command');
      html('div', 'turn dirv', last, (only ? '' : 'DIRECTOR: ') + (cmd ? cmd.summary + ' at MET ' + cmd.met_s.toFixed(1) : 'no command yet'));
    }
    if (S.showTruth && tl.sources && tl.sources.truth) html('div', 'truth-note', box, 'SIM TRUTH: the simulator’s true state, never seen by ODIN.');
  }

  function describe(rec) {
    const b = rec.body || {};
    switch (rec.type) {
      case 'TRIGGER': return 'turn ' + b.turn_id + ' ' + b.turn_kind + ': ' + (b.triggers || []).map((x) => x.type).join(', ');
      case 'REQUEST': return b.command + ' ' + params(b.parameters);
      case 'DECISION': {
        const f = (b.checks || []).find((c) => c.result === 'FAIL');
        return b.decision + (f ? ' ' + f.check + ' ' + f.reason : '') + (b['class'] ? ' (' + b['class'] + ')' : '');
      }
      case 'DECISION_VOIDED': return b.check + ' ' + b.reason;
      case 'DISPATCH': return b.command + ' by ' + b.route;
      case 'OUTCOME': return b.outcome + (b.point ? ' ' + b.point.mnemonic + '=' + b.point.value : '');
      case 'ANSWER': return 'turn ' + b.turn_id + ' ' + ((b.answer || {}).kind || 'report');
      case 'MALFORMED': return 'turn ' + b.turn_id + ' ' + b.reason;
      case 'REPORT': return b.report_kind;
      case 'ESCALATION': return b.escalation_kind + ' ' + b.urgency;
      case 'CHECK_IN': return '“' + (b.text || '') + '”';
      case 'CONTACT': return b.state;
      case 'PLAN_IN_FORCE': return b.plan_id;
      case 'ARMING_VERIFIED': return b.result + ' ' + b.act_id;
      case 'PLAN_CHAIN_VERIFIED': return b.result;
      case 'MODEL_CALL': return 'turn ' + b.turn_id + ' ' + b.config + ' ' + b.status;
      case 'RUN_END': return b.reason;
      case 'RESTORE': return b.result;
      default: return b.turn_id !== undefined ? 'turn ' + b.turn_id : '';
    }
  }

  function drawFeed() {
    const tl = S.tl, t = S.met;
    const shown = tl._records.filter((r) => r.met_s <= t && (S.showInternal || !INTERNAL.has(r.type)));
    const key = shown.length + ':' + S.showInternal;
    if (key === S.feedKey) return;
    S.feedKey = key;
    const list = $('feed');
    clear(list);
    if (passOnly(tl)) html('li', 'internal', list, 'No event log: no ODIN run of this pass yet.');
    const recent = shown.slice(-40).reverse();
    recent.forEach((r, i) => {
      const li = html('li', INTERNAL.has(r.type) ? 'internal' : '', list);
      if (i === 0) li.classList.add('newest');
      html('span', 't', li, String(r.met_s).padStart(5, ' '));
      html('span', 'k', li, r.type);
      html('span', null, li, describe(r));
      if (S.cites && S.cites.has(r.record_id)) li.classList.add('cited');
      li.title = 'Record ' + r.record_id + ' (click to show it)';
      li.addEventListener('click', () => (r.type === 'REPORT' ? openReport(r) :
        inspect('Record ' + r.record_id + ' · ' + r.type + ' · MET ' + r.met_s, JSON.stringify(r, null, 2))));
    });
  }

  // ---- controls ---------------------------------------------------------------
  function wireControls() {
    $('run-select').addEventListener('change', (e) => loadRun(e.target.value));
    $('btn-play').addEventListener('click', () => (S.playing ? pause() : play()));
    $('btn-cites-close').addEventListener('click', () => closeCites());
    // The clip's full caption, as its renderer wrote it, in the Record panel.
    $('btn-caption').addEventListener('click', () => {
      const c = S.clip && S.clip.clip;
      if (c && c.caption) openCaption(c);
    });
    $('btn-start').addEventListener('click', () => { pause(); if (S.tl) setMet(S.tl.met_range[0]); });
    $('btn-end').addEventListener('click', () => { pause(); if (S.tl) setMet(S.tl.met_range[1]); });
    $('btn-prev').addEventListener('click', () => jump(-1));
    $('btn-next').addEventListener('click', () => jump(1));
    $('speed').addEventListener('change', (e) => { S.speed = Number(e.target.value); syncClip(); });
    $('scrub').addEventListener('input', (e) => { pause(); setMet(Number(e.target.value)); });
    $('btn-zoom-in').addEventListener('click', () => zoom(0.5));
    $('btn-zoom-out').addEventListener('click', () => zoom(2));
    $('btn-zoom-all').addEventListener('click', () => { if (S.tl) { S.view = [S.tl.met_range[0], S.tl.met_range[1]]; render(); } });
    $('chk-truth').addEventListener('change', (e) => { S.showTruth = e.target.checked; render(); drawNow(); });
    $('chk-future').addEventListener('change', (e) => { S.showFuture = e.target.checked; placeHead(); });
    $('chk-internal').addEventListener('change', (e) => { S.showInternal = e.target.checked; drawFeed(); });
    document.addEventListener('keydown', (e) => {
      if (e.target && (e.target.tagName === 'SELECT' || e.target.tagName === 'INPUT')) {
        if (e.key !== ' ') return;
      }
      if (e.key === ' ') { e.preventDefault(); S.playing ? pause() : play(); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); jump(1); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); jump(-1); }
      else if (e.key === 'Home') { pause(); if (S.tl) setMet(S.tl.met_range[0]); }
      else if (e.key === 'End') { pause(); if (S.tl) setMet(S.tl.met_range[1]); }
      else if (e.key === '+' || e.key === '=') zoom(0.5);
      else if (e.key === '-') zoom(2);
      else if (e.key === '0') $('btn-zoom-all').click();
    });
    let pending = null;
    window.addEventListener('resize', () => {
      clearTimeout(pending);
      pending = setTimeout(() => { render(); }, 120);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();

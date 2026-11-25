/**
 * The source of the six empirical lines' flow pages beside this file,
 * `papersmith-<kind>-flow.html` (observational-measurement, hardware,
 * lab-simulation, data-resource, experiment-intervention,
 * qualitative-participatory), one Archify candidate per line.
 *
 *   SCRATCH=$(mktemp -d)
 *   python scripts/line_flow_candidates.py "$SCRATCH/lines.json"
 *   node docs/diagrams/papersmith-line-flow.build.mjs "$SCRATCH/lines.json" "$SCRATCH"
 *   # then, per kind: archify finalize architecture "$SCRATCH/<kind>/candidate.json" ...
 *
 * Nothing here is transcribed by hand. `scripts/line_flow_candidates.py` dumps
 * each line's board table (`empirical_board.LINE_TABLES`: its steps in order,
 * the gates it lists, the gate each step waits for, the steps that wait for
 * nothing) with the line range of every `Step(...)` and `Gate(...)` definition
 * at the revision it pins, and this script lays each table out. A changed table
 * is a changed drawing: `tests/test_line_flow_diagrams.py` holds every page's
 * lanes and gates against the live table, so a page cannot drift from its
 * board silently.
 *
 * One lane per board step, numbered as the dashboard's *Pipeline y Avance*
 * numbers them, labelled with the step's label. A lane reads left to right:
 * the skills the step runs (`/<skill>`, or the operator when it runs none),
 * the records it writes, and the operator gates the board lists under it.
 * The first node of each lane carries the chain down column 0 to the next
 * lane; the edge is a `security` edge naming the gate when the next step
 * waits for one (`phase_gates`), dashed when it waits for nothing
 * (`ungated`), and the main path otherwise. A lane with more than five nodes
 * turns at column 4 into a second row, right to left, so column 0 stays free
 * for the chain. Every edge is between row neighbours or straight down a
 * column, so no route needs Archify's grid search, and the drawing keeps the
 * Pi flow's five columns of 182px (its 1240px readability cap).
 */
import fs from 'fs';
import path from 'node:path';

const [dumpPath, outDir] = process.argv.slice(2);
if (!dumpPath || !outDir) {
  console.error('usage: node papersmith-line-flow.build.mjs <lines.json> <out-dir>');
  process.exit(2);
}
const dump = JSON.parse(fs.readFileSync(dumpPath, 'utf8'));
const COLS = 5;

const base = p => {
  const trimmed = p.replace(/\/$/, '');
  const cut = trimmed.lastIndexOf('/', trimmed.indexOf(' ') < 0 ? trimmed.length : trimmed.indexOf(' '));
  return cut < 0 ? { label: p, dir: 'workspace root' } : { label: p.slice(cut + 1), dir: p.slice(0, cut + 1) };
};
const tools = step => 'tools: ' + step.tools.join(' · ');
// The step's board title, without the gates its lane already draws, as the
// first node's tag when it fits the node (Archify refuses a wider tag).
const shortTitle = step => {
  const title = step.title.replace(/\s*\(G-[^)]*\)$/, '');
  return title.length <= 30 ? title : null;
};

function candidate(line) {
  const nodes = [];
  const edges = [];
  const lanes = [];
  const firstOf = {};
  line.steps.forEach((step, index) => {
    const lane = `lane-${step.id}`;
    lanes.push({ id: lane, label: `${index + 1} · ${step.label}` });
    const seq = [];
    const actors = step.skills.length ? step.skills : [null];
    actors.forEach((skill, i) => seq.push({
      id: `act-${step.id}-${i}`, kind: 'actor', type: skill ? 'frontend' : 'external',
      label: skill ? `/${skill}` : 'Operator', sublabel: tools(step),
      ...(i === 0 && shortTitle(step) ? { tag: shortTitle(step) } : {}), sources: [step.source],
    }));
    step.outputs.forEach((output, i) => {
      const { label, dir } = base(output);
      seq.push({ id: `rec-${step.id}-${i}`, kind: 'record', type: 'database', label, sublabel: dir, sources: [step.source] });
    });
    for (const gate of line.gates.filter(g => g.step === step.id)) {
      const tag = gate.with_people_only ? 'with people only' : gate.per_variant ? 'listed per agreed variant' : 'operator';
      seq.push({ id: `gate-${gate.id}`, kind: 'gate', type: 'security', label: gate.id, sublabel: gate.name, tag, sources: [gate.source] });
    }
    if (seq.length > 2 * COLS - 1) throw new Error(`step ${step.id} has ${seq.length} nodes; a lane holds ${2 * COLS - 1}`);
    seq.forEach((node, i) => {
      const [rowOff, col] = i < COLS ? [0, i] : [1, COLS - 1 - (i - COLS)];
      nodes.push({ ...node, lane, rowOff, col });
      if (i === 0) return;
      const prev = seq[i - 1];
      const variant = prev.kind === node.kind && node.kind !== 'record' ? 'dashed'
        : prev.kind === 'record' && node.kind === 'record' ? 'dashed'
        : node.kind === 'gate' ? 'security' : null;
      edges.push({ from: prev.id, to: node.id, ...(variant ? { variant } : {}) });
    });
    firstOf[step.id] = seq[0].id;
  });
  line.steps.forEach((step, index) => {
    if (index === 0) return;
    const from = firstOf[line.steps[index - 1].id];
    const to = firstOf[step.id];
    const gate = line.phase_gates[step.id];
    if (line.ungated.includes(step.id)) edges.push({ from, to, label: 'waits for nothing', variant: 'dashed' });
    else if (gate) edges.push({ from, to, label: `waits for ${gate}`, variant: 'security' });
    else edges.push({ from, to, variant: 'emphasis' });
  });

  const laneRow = {};
  let nextRow = 0;
  for (const lane of lanes) {
    laneRow[lane.id] = nextRow;
    nextRow += 1 + Math.max(0, ...nodes.filter(n => n.lane === lane.id).map(n => n.rowOff));
  }
  const components = nodes.map(({ lane, rowOff, col, kind, ...rest }) => ({ ...rest, row: laneRow[lane] + rowOff, col, size: [182, 58] }));
  const connections = edges.map(edge => ({ id: `${edge.from}--${edge.to}`, ...edge }));
  const boundaries = lanes.map(lane => ({ kind: 'region', label: lane.label, wraps: nodes.filter(n => n.lane === lane.id).map(n => n.id) }));
  const number = Object.fromEntries(line.steps.map((step, i) => [step.id, `${i + 1} · ${step.label}`]));
  const waits = line.steps.flatMap(step => {
    if (line.ungated.includes(step.id) && step.id !== line.steps[0].id) return [`${number[step.id]} waits for nothing: it can start at any time`];
    if (line.phase_gates[step.id]) return [`${number[step.id]} waits for ${line.phase_gates[step.id]} on top of the step before it`];
    return [];
  });
  return {
    schema_version: 1, diagram_type: 'architecture',
    meta: {
      title: `Papersmith AI — the ${line.kind} line`,
      quality_profile: 'showcase',
      output: `docs/diagrams/papersmith-${line.kind}-flow.html`,
      repository: { url: 'https://github.com/LIAUNAL/papersmith-ai', provider: 'github', link_mode: 'web', revision: dump.revision },
      legend: { mode: 'auto', entries: {
        frontend: { label: 'Command /skill' }, external: { label: 'Operator' }, database: { label: 'Record on disk' },
        security: { label: 'Gate (operator)' } } },
    },
    layout: { mode: 'grid', origin: [30, 48], cols: COLS, cellW: 182, cellH: 58, gapX: 24, gapY: 62 },
    components, boundaries, connections,
    cards: [
      { dot: 'cyan', title: 'This line', items: [
        `smith init --kind ${line.kind}: ${line.label}`,
        `${line.summary[0].toUpperCase()}${line.summary.slice(1)}`,
        '/paper-type agrees the paper type and its variant at step 2; smith kind set moves a workspace whose agreed type belongs to another line',
        `The dashboard's Flujo Archify tab serves static/${line.flow_html} for a workspace of this line (a workspace's own docs/papersmith-flow.html wins)`,
        ...(line.extra_checklists.length ? [`Reporting checklists beside the agreed type's own: ${line.extra_checklists.join(', ')}`] : []),
        `Generated from empirical_board.LINE_TABLES["${line.kind}"] by scripts/line_flow_candidates.py and docs/diagrams/papersmith-line-flow.build.mjs; never edited by hand`] },
      { dot: 'amber', title: 'Order and waits', items: [
        'Each step waits for the step before it, as the board locks each phase until the one before it is verified from its evidence on disk',
        ...waits,
        `${number[line.transversal]} is transversal: no later step waits for it`,
        'An agent never passes a gate: the operator records it, and the board only reads it from the records'] },
      { dot: 'rose', title: 'Gates', items: line.gates.map(g => `${g.id} · ${g.name} (listed under ${number[g.step]}${g.with_people_only ? ', only for a validation with people' : ''}${g.per_variant ? ', only for the variants that need it' : ''}): ${g.criteria}`) },
      { dot: 'violet', title: 'Who acts', items: line.steps.map(step => `${number[step.id]}: ${step.agent}; ${tools(step)}`) },
    ],
  };
}

for (const [kind, line] of Object.entries(dump.lines)) {
  const out = path.resolve(outDir, kind, 'candidate.json');
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, JSON.stringify(candidate(line), null, 1));
  console.log(`candidate: ${out}`);
}

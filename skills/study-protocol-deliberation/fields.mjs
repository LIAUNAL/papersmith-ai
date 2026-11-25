#!/usr/bin/env node
// The protocol's fields, as JSON, for readers in other languages.
//
// `protocol-fields.ts` is the only parser of the protocol grammar; this file
// adds no rule of its own. It reads one JSON object on stdin, `{"<key>":
// "<protocol source>", ...}`, and prints `{"<key>": {"primary", "secondary",
// "outcomes", "analysisPlan"}, ...}`: `primary` and `secondary` are
// `outcomeIds(source)`, `outcomes` and `analysisPlan` come from
// `parseProtocol(source)`. The caller reads and hashes the bytes itself, so
// what it parsed is what it hashed (skills/_core/empirical/analysis_log.py).
//
// Exit 0 with the object; exit 2 with `{"error": "INPUT_INVALID", ...}` when
// stdin is not a JSON object of strings.
import { outcomeIds, parseProtocol } from './protocol-fields.ts';

const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
let sources;
try {
	sources = JSON.parse(Buffer.concat(chunks).toString('utf8'));
} catch (error) {
	sources = null;
}
if (sources === null || typeof sources !== 'object' || Array.isArray(sources)
	|| !Object.values(sources).every((value) => typeof value === 'string')) {
	process.stdout.write(`${JSON.stringify({ error: 'INPUT_INVALID', message: 'stdin is a JSON object of protocol sources' })}\n`);
	process.exit(2);
}
const out = {};
for (const [key, source] of Object.entries(sources)) {
	const parsed = parseProtocol(source);
	const ids = outcomeIds(source);
	out[key] = {
		primary: ids.primary,
		secondary: ids.secondary,
		outcomes: parsed.outcomes.map(({ role, id, measure, timePoint }) => ({ role, id, measure, timePoint })),
		analysisPlan: parsed.analysisPlan,
	};
}
process.stdout.write(`${JSON.stringify(out)}\n`);

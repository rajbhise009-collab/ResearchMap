// Search, run in the browser over an index built offline.
//
// This is the twin of backend/app/api/search_index.py. The two tokenizers
// must produce identical output or the index stops matching queries — the
// fixtures in backend/tests/api/test_search.py::TOKENIZER_FIXTURES are
// asserted on both sides. Change one, change the other.
//
// Stopwords and everyday-phrasing come from the shipped index rather than
// being duplicated here, so they cannot drift.

import type { SearchIndex, SearchResult, SearchHit } from "./types";

const UNKNOWN_WEIGHT = 3.5;
const IN_DOMAIN_COVERAGE = 0.62;
const IN_DOMAIN_BEST = 0.05;
const RESCUE_COVERAGE = 0.28;
const RESCUE_BEST = 0.2;
// The rescue path additionally requires a body of work, not one strong
// document match on a frequent term. Same-word-different-field collisions
// ("calibration of medical imaging equipment") produce one high-scoring
// EHR paper via the "medical" term and nothing else — breadth catches that
// where coverage and best do not.
const RESCUE_BREADTH = 0.24;
const BREADTH_IN_DOMAIN = 0.18;

const SUFFIXES: [string, string][] = [
  ["ies", "y"],
  ["ing", ""],
  ["edly", ""],
  ["ly", ""],
  ["ed", ""],
  ["es", ""],
  ["s", ""],
];

export function stem(w: string): string {
  for (const [suf, repl] of SUFFIXES) {
    if (w.length > suf.length + 2 && w.endsWith(suf)) {
      return w.slice(0, w.length - suf.length) + repl;
    }
  }
  return w;
}

export function tokenizePairs(
  text: string,
  stopwords: Set<string>,
  synonyms: Record<string, string[]>
): [string, string][] {
  const out: [string, string][] = [];
  const words = (text || "").toLowerCase().match(/[a-z0-9]+/g) || [];
  for (const raw of words) {
    // "ai" and "llm" are short but are the words a reader is likeliest to
    // type, so they survive when the phrasing table knows them.
    const tooShort = raw.length < 3 && !(raw in synonyms);
    if (tooShort || stopwords.has(raw) || /^\d+$/.test(raw)) continue;
    const s = stem(raw);
    if (stopwords.has(s)) continue;
    out.push([s, raw]);
  }
  return out;
}

export function tokenize(
  text: string,
  stopwords: Set<string>,
  synonyms: Record<string, string[]>
): string[] {
  const singles = tokenizePairs(text, stopwords, synonyms).map(([t]) => t);
  const bigrams: string[] = [];
  for (let i = 0; i < singles.length - 1; i++) {
    bigrams.push(`${singles[i]}__${singles[i + 1]}`);
  }
  return singles.concat(bigrams);
}

export function search(index: SearchIndex, query: string, limit = 20,
                       opts: { prefixLast?: boolean } = {}): SearchResult {
  const stopwords = new Set(index.stopwords);
  const syn = index.synonyms;
  const pairs = tokenizePairs(query, stopwords, syn);
  const idf = index.idf;
  const maxIdf = index.max_idf;

  // Prefix-expansion for the last typed token (type-ahead). Mirrors the
  // Python twin's `prefix_last` arg. The verdict is still computed from
  // complete tokens only, so a prefix cannot promote an OOD query into
  // in-domain mid-typing.
  const prefixAdded: string[] = [];
  if (opts.prefixLast && query && !/\s$/.test(query)) {
    const words = (query || "").toLowerCase().match(/[a-z0-9]+/g) || [];
    const tail = words.length ? words[words.length - 1] : "";
    if (tail && tail.length >= 3) {
      const tailStem = stem(tail);
      if (!(tailStem in idf)) {
        for (const t of Object.keys(idf)) {
          if (!t.includes("__") && t.startsWith(tailStem)) prefixAdded.push(t);
        }
      }
    }
  }

  if (pairs.length === 0 && prefixAdded.length === 0) {
    return {
      verdict: "empty", coverage: 0, best: 0, breadth: 0, n_matched: 0,
      hits: [], known: [], unknown: [], expanded: [],
    };
  }

  const understood = (tok: string, word: string) =>
    tok in idf || (syn[word] || []).some((s) => stem(s) in idf);

  const known: string[] = [];
  const unknown: string[] = [];
  for (const [t, w] of pairs) (understood(t, w) ? known : unknown).push(t);

  const knownMass = known.reduce((a, t) => a + (idf[t] ?? maxIdf), 0);
  const unknownMass = unknown.length * maxIdf * UNKNOWN_WEIGHT;
  const denom = knownMass + unknownMass;
  const coverage = denom ? knownMass / denom : 0;

  // Expansion helps the ranking find the right papers; it is deliberately
  // not allowed to change the coverage figure above, so an out-of-domain
  // question can never be talked into looking understood.
  const baseTokens = pairs.map(([t]) => t);
  const expandedTokens = baseTokens.slice();
  for (const [, w] of pairs) for (const s of syn[w] || []) expandedTokens.push(stem(s));
  // Adjacent-pair bigrams so a query like "demographic parity" matches
  // the shipped bigram vocab entry `demographic__parity`.
  for (let i = 0; i < baseTokens.length - 1; i++) {
    expandedTokens.push(`${baseTokens[i]}__${baseTokens[i + 1]}`);
  }
  for (const t of prefixAdded) expandedTokens.push(t);

  const qtf = new Map<string, number>();
  for (const t of expandedTokens) if (t in idf) qtf.set(t, (qtf.get(t) || 0) + 1);

  const qvec = new Map<string, number>();
  if (qtf.size) {
    const peak = Math.max(...qtf.values());
    const prefixSet = new Set(prefixAdded.filter((t) => !baseTokens.includes(t)));
    let sum = 0;
    const raw = new Map<string, number>();
    for (const [t, c] of qtf) {
      // Halve weight for prefix-only matches so exact tokens rank above.
      const v = (0.5 + (0.5 * c) / peak) * idf[t] * (prefixSet.has(t) ? 0.5 : 1);
      raw.set(t, v);
      sum += v * v;
    }
    const norm = Math.sqrt(sum) || 1;
    for (const [t, v] of raw) qvec.set(t, v / norm);
  }

  const hits: SearchHit[] = [];
  for (const d of index.docs) {
    let score = 0;
    for (const [t, w] of qvec) {
      const dv = d.terms[t];
      if (dv !== undefined) score += w * dv;
    }
    if (score > 0) {
      const matched = [...qvec.keys()]
        .filter((t) => d.terms[t] !== undefined)
        .sort((a, b) => qvec.get(b)! * d.terms[b] - qvec.get(a)! * d.terms[a])
        .slice(0, 6);
      hits.push({
        type: d.type, ref: d.ref, title: d.title, kind: d.kind,
        strength: d.strength, score, matched,
      });
    }
  }
  // Rank by score; gaps (type=opportunity) above papers on tie.
  hits.sort((a, b) => (b.score - a.score)
    || ((a.type === "opportunity" ? 0 : 1) - (b.type === "opportunity" ? 0 : 1)));
  const best = hits.length ? hits[0].score : 0;
  const breadth = index.n_docs ? hits.length / index.n_docs : 0;

  // Per-library gate thresholds carried on the index; the constants
  // above remain the fallback for an older index without them.
  const g = (index as any).gate || {};
  const inCov  = Number(g.in_domain_coverage ?? IN_DOMAIN_COVERAGE);
  const inBest = Number(g.in_domain_best     ?? IN_DOMAIN_BEST);
  const inBr   = Number(g.in_domain_breadth  ?? BREADTH_IN_DOMAIN);
  const rCov   = Number(g.rescue_coverage    ?? RESCUE_COVERAGE);
  const rBest  = Number(g.rescue_best        ?? RESCUE_BEST);
  const rBr    = Number(g.rescue_breadth     ?? RESCUE_BREADTH);

  // Specific-term bypass: a query whose matched tokens are highly
  // specific to this library (very high IDF, e.g. "demographic parity",
  // "COMPAS", "semantic entropy") lands in-domain even when breadth is
  // tiny — rare technical terms don't need the breadth gate.
  const HIGH_IDF = maxIdf * 0.55;
  let specificHit = false;
  if (coverage >= 0.95 && best > 0 && breadth > 0) {
    for (const t of qvec.keys()) {
      if ((idf[t] ?? 0) >= HIGH_IDF) { specificHit = true; break; }
    }
  }

  let verdict: SearchResult["verdict"];
  if (coverage >= inCov && best >= inBest && breadth >= inBr) {
    verdict = "in_domain";
  } else if (specificHit) {
    verdict = "in_domain";
  } else if (coverage >= inCov && best > 0) {
    verdict = "borderline";
  } else if (coverage >= rCov && best >= rBest && breadth >= rBr) {
    verdict = "borderline";
  } else {
    verdict = "out_of_domain";
  }

  return {
    verdict, coverage, best, breadth, n_matched: hits.length,
    hits: hits.slice(0, limit), known, unknown,
    expanded: [...qvec.keys()].sort(),
  };
}

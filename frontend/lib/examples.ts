// Example questions per library, written from each library's own subject.
// Shared by the search box (Ask.tsx: the example chips and the "Try:" hint)
// and the command palette (its empty-state "Try:" line), so both always
// suggest a question from the library on screen.
//
// Every example is answered in_domain by that library's own index and trips
// none of the safety checks (lib/safety.ts). A library without its own set
// (e.g. one built later from the queue) gets no examples and no "Try:" line,
// never another library's.

export const EXAMPLES_BY_LIBRARY: Record<string, string[]> = {
  "llm-calibration": [
    "why do language models sound confident when they're wrong",
    "when should a chatbot refuse to answer",
    "fake citations in AI answers",
  ],
  "ml-fairness": [
    "can a model be fair to every group at once",
    "what is demographic parity",
    "bias in criminal risk scores",
  ],
  "diet-and-mortality": [
    "red meat and mortality",
    "alcohol and heart disease",
    "ultra-processed food and mortality",
  ],
  "social-media-teen-mental-health": [
    "does screen time cause depression in teens",
    "social media and teenage loneliness",
    "phone use and sleep in teenagers",
  ],
};

export function examplesFor(slug: string | null | undefined): string[] {
  return (slug && EXAMPLES_BY_LIBRARY[slug]) || [];
}

const QUESTION_START = /^(why|what|how|when|where|who|which|can|could|does|do|is|are|should|will)\b/i;

// "Try: <the library's first example>", with a question mark only when the
// example is phrased as a question. Null when the library has no examples.
export function tryHintFor(slug: string | null | undefined): string | null {
  const first = examplesFor(slug)[0];
  if (!first) return null;
  return `Try: ${first}${QUESTION_START.test(first) ? "?" : ""}`;
}

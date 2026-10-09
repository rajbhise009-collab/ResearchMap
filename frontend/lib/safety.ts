// Safety rules for what a visitor types. Deliberately small and plain.
//
// distress: personal-distress phrasing (first person + distress words, or
//   explicit self-harm intent). On ANY library the search shows no research
//   results and no "build a library" offer, only one calm message: this is a
//   research tool, not support, with a link to findahelpline.com. Research
//   questions about the same subjects ("suicide rates in adolescents",
//   "self-harm and social media") are not personal and are answered normally.
// adviceLike: questions phrased as asking for personal or parenting advice.
//   In a health-adjacent library, results then LEAD with "This is research
//   literature, not medical or parenting advice", then the library's note.
// panelBlocked: the out-of-scope panel never offers "suggest a library on
//   this subject" for these (self-harm, sexual content, slurs, or what looks
//   like a person's name).

export const HELPLINE_URL = "https://findahelpline.com";

const ADVICE = new RegExp([
  "\\bshould (i|we)\\b",
  "\\bshould (my|our) (kid|kids|child|children|son|daughter|teen\\w*)\\b",
  "\\bcan i (eat|drink|have)\\b",
  "\\bis [\\w\\s'’-]{1,30}? (safe|ok|okay|healthy|harmful|bad|good)( for)?\\b",
  "\\bhow (much|many|long) [\\w\\s'’-]{0,35}(safe|healthy|should|ok|okay|per day|a day|is too much)\\b",
  "\\b(healthy|safe) (amount|dose|level)\\b",
  "\\b(good|bad) for (me|you|my)\\b",
  "\\brecommend(ed)?\\b", "\\bdiet plan\\b", "\\blose weight\\b",
  "\\bfor my (health|heart|diabetes)\\b",
  "\\bmy (kid|kids|child|children|son|daughter|teen\\w*)\\b",
].join("|"), "i");

const FIRST_PERSON = /\b(i|i'm|im|i’m|i am|i've|ive|me|my|myself)\b/i;
const DISTRESS_WORDS = /\b(depressed|depressing|hopeless|worthless|suicidal|self[- ]?harm\w*|cutting myself|can'?t cope|can’t cope|cannot cope|can'?t go on|can’t go on|so alone|empty inside|hate myself|panic attacks?|give up on (life|everything)|no point (in )?living|want to disappear)\b/i;
const DISTRESS_INTENT = /\b(kill (myself|me)|end (my life|it all)|take my (own )?life|want to die|wanna die|hurt(ing)? myself|cut(ting)? myself|better off dead|no reason to live|suicide (method|note)s?|how to (commit suicide|overdose|kill))\b/i;

const SELF_HARM = /\b(kill (myself|me)|suicid\w*|self[- ]?harm\w*|end my life|hurt myself|want to die)\b/i;
const SEXUAL = /\b(porn\w*|nude\w*|nsfw|xxx|sex (video|chat|tape)s?|onlyfans)\b/i;
// A minimal slur list (stems), matched on word starts.
const SLURS = /\b(nigg|fagg?ot|retard|kike|spic|chink|tranny|wetback)\w*/i;
// "Firstname Lastname" (two or three capitalised words and nothing else).
const PERSON_NAME = /^\s*[A-Z][a-z'’-]+(\s+[A-Z][a-z'’-]+){1,2}\s*$/;

export function distress(q: string): boolean {
  return DISTRESS_INTENT.test(q) || (FIRST_PERSON.test(q) && DISTRESS_WORDS.test(q));
}
export function adviceLike(q: string): boolean { return ADVICE.test(q); }
export function selfHarm(q: string): boolean { return SELF_HARM.test(q); }
export function panelBlocked(q: string): boolean {
  return SELF_HARM.test(q) || SEXUAL.test(q) || SLURS.test(q) || PERSON_NAME.test(q);
}

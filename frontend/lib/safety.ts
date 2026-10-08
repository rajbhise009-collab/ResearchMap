// Safety rules for what a visitor types. Deliberately small and plain.
//
// adviceLike: questions phrased as asking for personal advice. In a library
//   that carries a not-advice note (Diet), results then lead with that note
//   and a sentence saying we cannot tell anyone what to eat or drink.
// panelBlocked: the out-of-scope panel never offers "suggest a library on
//   this subject" for these (self-harm, sexual content, slurs, or what looks
//   like a person's name). The search itself is unchanged: such queries are
//   simply out of scope and refused calmly like any other.
// selfHarm: additionally shows one line pointing to real-world help.

const ADVICE = /\b(should i|should we|can i (eat|drink|have)|is (it|this|that|\w+) (safe|ok|okay|healthy|good for|bad for)|how (much|many) [\w\s]{0,30}(safe|healthy|should|ok|okay|per day|a day)|healthy (amount|dose|level)|safe (amount|dose|level)|good for (me|you|my)|bad for (me|you|my)|recommend(ed)?|diet plan|lose weight|for my (health|heart|diabetes))\b/i;

const SELF_HARM = /\b(kill (myself|me)|suicid\w*|self[- ]?harm\w*|end my life|hurt myself|want to die)\b/i;
const SEXUAL = /\b(porn\w*|nude\w*|nsfw|xxx|sex (video|chat|tape)s?|onlyfans)\b/i;
// A minimal slur list (stems), matched on word starts.
const SLURS = /\b(nigg|fagg?ot|retard|kike|spic|chink|tranny|wetback)\w*/i;
// "Firstname Lastname" (two or three capitalised words and nothing else).
const PERSON_NAME = /^\s*[A-Z][a-z'’-]+(\s+[A-Z][a-z'’-]+){1,2}\s*$/;

export function adviceLike(q: string): boolean { return ADVICE.test(q); }
export function selfHarm(q: string): boolean { return SELF_HARM.test(q); }
export function panelBlocked(q: string): boolean {
  return SELF_HARM.test(q) || SEXUAL.test(q) || SLURS.test(q) || PERSON_NAME.test(q);
}

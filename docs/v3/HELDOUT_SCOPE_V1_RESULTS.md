# Held-out scope evaluation v1

Run once on 2026-11-05 with `python -m assistant.scope_eval ../docs/v3/eval/heldout_scope_v1.jsonl`
(from `backend/`). The checker was frozen beforehand and was not changed: git blob hashes
before and after the run are `scope.py` 2726dcaf, `scope_terms.py` 0352815e,
`scope_eval.py` 89bfb6dd. The set has 30 owner-written questions authored on 5 November 2026:
12 in scope, 10 out of scope and 8 ambiguous (expected to get the `scope_unclear` fallback).

## Result: the checker does not meet the bar on this set

Accuracy is 17 of 30 (56.7 %). No out-of-scope question was answered. However, the
ambiguous group failed entirely, and 3 of 12 in-scope questions were sent to the rephrase
fallback.

### Confusion matrix (rows = expected, columns = checker decision)

| Expected ↓ / Got → | in_scope | out_of_scope | scope_unclear | Total |
|---|---|---|---|---|
| in_scope | **9** | 0 | 3 | 12 |
| out_of_scope | 0 | **8** | 2 | 10 |
| ambiguous (scope_unclear) | 3 | 5 | **0** | 8 |

### Rates

| Metric | Definition | Value |
|---|---|---|
| False-positive rate | Out-of-scope or ambiguous questions decided `in_scope` (would be answered): 3 / 18 | **16.7 %** (all 3 are ambiguous; 0 of 10 out-of-scope) |
| False-negative rate | In-scope questions not decided `in_scope`: 3 / 12 | **25.0 %** (all 3 sent to fallback; 0 refused outright) |
| Ambiguous fallback rate | Ambiguous questions decided `scope_unclear`: 0 / 8 | **0 %** |
| Out-of-scope refused outright | Out-of-scope questions decided `out_of_scope`: 8 / 10 | 80 % (the other 2 got the fallback, so they were not answered either) |

## Each mismatch and why it happened

| ID | Question | Expected | Got | What the checker matched (rule) |
|---|---|---|---|---|
| H03 | What caused the slowdown near the flyover this morning? | in_scope | scope_unclear | weak `flyover` only (rule 4); "slowdown" is not in the vocabulary |
| H08 | Has the roadwork near my usual junction finished? | in_scope | scope_unclear | weak `junction` only (rule 4); vocabulary has "road works" (two words), not "roadwork" |
| H12 | Why does my estimated arrival time keep changing? | in_scope | scope_unclear | weak `arrival` only (rule 4); "estimated arrival time" is not a phrase in the vocabulary |
| H16 | Can you recommend a laptop for machine learning? | out_of_scope | scope_unclear | strong `machine learning` + negative `laptop` (rule 2) |
| H18 | What is the weather like in Bengaluru this weekend? | out_of_scope | scope_unclear | weak `weather` only (rule 4) |
| H23 | How far is the airport from here? | ambiguous | out_of_scope | nothing matched (rule 6); known gap A-06 in the development cases |
| H24 | Is Whitefield far from Electronic City? | ambiguous | out_of_scope | places only, masked (rule 6) |
| H25 | How long does it usually take to reach the airport? | ambiguous | in_scope | weak `how long` + `reach` (rule 3) |
| H26 | What is happening around Marathahalli? | ambiguous | out_of_scope | place only (rule 6) |
| H27 | Can you help me plan my journey? | ambiguous | out_of_scope | nothing matched (rule 6); "journey" is only in the phrase "journey time" |
| H28 | Is it better to leave now or later? | ambiguous | in_scope | weak `leave` + `now` (rule 3) |
| H29 | Why is everything so slow today? | ambiguous | in_scope | weak `slow` + `today` (rule 3) |
| H30 | How do I get there? | ambiguous | out_of_scope | nothing matched (rule 6); "how do i get to" needs "to" |

## What the failures show

1. **Design mismatch on travel-like questions with no recognised concept (H23, H24, H26,
   H27, H30).** Rule 6 refuses anything with no recognised concept, including
   place-only questions. The owner's labels treat travel-shaped questions without enough
   detail as ambiguous, which should get the rephrase prompt instead. The design decision
   "place names never qualify" still holds: none of these were answered. But the refusal
   message is the wrong one.
2. **The weak-pair rule is too permissive (H25, H28, H29).** Two generic words such as
   `leave` + `now` or `slow` + `today` are enough for `in_scope`. On this set, that
   answered three questions the owner considers too vague to answer.
3. **Vocabulary gaps for common traffic wording (H03, H08, H12):** "slowdown", "roadwork",
   "estimated arrival time". These questions were not refused; they got the rephrase prompt.
4. **Safety property held.** None of the 10 out-of-scope questions was answered
   (8 refused, 2 sent to fallback), including "biryani near Koramangala".

## Recommended remediation (not applied)

Because these results are now known, this held-out set can no longer measure any change
made in response to them. Remediation therefore needs two new sets:

1. **A separate development set, `scope_dev_v2.jsonl`**, written to cover the failure
   *patterns* above without reusing the held-out wording. It should include travel
   questions with places and no concept, generic weak pairs, and everyday traffic
   phrasing. It can be written by Claude and reviewed by the owner.
2. **Candidate design changes, tuned only on `scope_dev_v2` and the existing development cases:**
   * Rule 6: if a place is present, or the question has a travel shape ("how far",
     "get there", "plan my journey"), return `scope_unclear` instead of `out_of_scope`.
     Out-of-scope stays only for questions with no place and no travel cue, or with
     negative terms.
   * Rule 3: require at least one weak concept from a travel or road group (road, drive,
     reach, arrive, duration, distance, road feature). Time words (`now`, `today`) and speed
     words alone would no longer be enough.
   * Vocabulary: consider `slowdown`, `slow down`, `roadwork`, `roadworks`,
     `estimated arrival`, `arrival time`, `journey`. Record each in the change log.
3. **A fresh held-out set, `heldout_scope_v2.jsonl`**, written by the owner after the
   changes are frozen, for the final evaluation.

`heldout_scope_v1` stays unchanged as the record of the frozen v1 checker.

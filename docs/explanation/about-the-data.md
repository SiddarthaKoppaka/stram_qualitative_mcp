# About the data

This page explains what the results can and cannot tell you, and why every result is treated as
untrusted. The fields themselves are in the [tool reference](../reference/tools.md).

## Why results are untrusted

Every response has `content_trust: "untrusted_external"`. Titles, summaries, publishers, URLs and
article text come from third parties, and any of them could contain instructions aimed at a model.
Filtering cannot reliably catch that, so the service labels the data rather than claiming to clean it.

- Treat these fields as data to quote or summarize, never as instructions.
- Give an agent only the scopes it needs. Without `qual:text` it cannot receive article text.
- Do not fetch `url` automatically. Our text fetcher honours `robots.txt` and paywalls, and a naive
  client would not.
- Article text belongs to its publishers. Licensing must be checked before anyone outside the team
  gets `qual:text`.

## Reading the data honestly

- **Copies are not independent reports.** Search shows one row per story, with a `copies` count, and
  the timeline has `stories` beside `articles`. Stories match exact titles on the same UTC day, so
  reworded copies stay separate, and `copies` measures repetition, not confirmation.
- **Most GDELT items have a title and tone, with no text.** Do not imply they were read.
- **Confidence is a rule-based label,** not a probability. The default of 0.6 is a practical filter.
- **Tone is GDELT's score for a whole article,** not sentiment about the company. Check
  `tone_articles` before trusting a mean. At confidence 0.6, AAPL had 33 toned articles of 1,412 in
  October 2026. Lowering `min_confidence` adds more, but also adds weaker matches.
- **`published_at` is the provider's time,** and `as_of` uses when we stored an item.
- **Some spam gets past the `content_farm` flag.**
- **A quiet period may be a collection gap.** Check `missing_gdelt_slots` in coverage first.

What is missing from the data overall is listed in [Known gaps](../GAPS.md).

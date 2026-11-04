# How to answer common questions with the tools

Each recipe names the tool and arguments for one question. Field details are in the
[tool reference](../reference/tools.md), and the limits of the data are in
[About the data](../explanation/about-the-data.md).

**What data do we hold?** Call `qual_describe_coverage` first. It shows the sources, how fresh they
are, which tickers are tracked, and which GDELT periods are missing. A quiet period may be a gap and not
a lack of news.

**What was reported about a company?** Call `qual_search_news` with `tickers`, `start_date` and
`end_date`. Default filters hide weak matches and flagged spam. For more, raise `limit` to 100 or
split the dates. When `truncated` is true, there are more results than you received.

**What does an article say?** If a card has `text_available: true`, pass its `article_id` to
`qual_get_article`. Text comes in slices of up to 8,000 characters. While `has_more` is true, call
again with `offset` raised by `max_chars`. When `text_available` is false, use the title and summary,
and say the article was not read.

**What is being said about a theme?** Call `qual_search_news` with `text`, such as `"tariff"`, which
matches titles and summaries as a plain substring. Without `tickers`, the range is limited to 92 days.

**What did a company file?** Call `qual_get_filings` with `tickers`, and `forms` for specific types
such as `["8-K"]`. Forms match exactly, so `8-K/A` is separate.

**Did attention change?** Call `qual_get_news_timeline`. Days without articles are absent, not zero.

**What did we know at the time?** Pass `as_of` to `qual_search_news`. It uses when *we stored* an item,
not when it was published. Most history arrived from about 2026-10-30, so an earlier `as_of` sees very
little, and the response warns you.

# Bug #001 — link_fetcher fails to resolve tracking/redirect URLs

**Reported:** 2026-06-10  
**Reported by:** Earnest (production)  
**Severity:** Medium — articles from affected newsletters are not indexed  

## Summary

`fetch_articles_from_email()` in `src/processing/link_fetcher.py` returns 0 articles for emails where all links are wrapped in Mailgun (or similar) tracking redirects. The fetcher does not follow the redirect chain to reach the real article URL.

## Reproduction

Email: `nlpnews@substack.com` — "🥇Top AI Papers of the Week" (received 2026-06-07, email_id=487 in production DB)

All 3 links in this email follow the pattern:
```
https://email.mg1.substack.com/c/eJxc0kuTmkAQB_B...
```

These are Mailgun click-tracking URLs. When resolved they redirect to the actual article (e.g. a Hugging Face paper page or arXiv link), but `link_fetcher` is not following the redirect.

Result: `fetch_articles_from_email()` returns an empty list, nothing is stored in the `articles` table, and the content is not embedded in ChromaDB.

## Expected Behavior

The fetcher should follow HTTP redirects (including Mailgun, Beehiiv, MailChimp tracking wrappers) to resolve the final destination URL, then fetch and embed that article.

## Affected Senders

Any newsletter that routes links through a tracking proxy. Confirmed affected:
- `nlpnews@substack.com` (Mailgun / `email.mg1.substack.com`)

Likely also affected:
- Any Beehiiv-delivered newsletters (`link.mail.beehiiv.com`)
- Any MailChimp newsletters (`*.list-manage.com/track/click`)

## Notes

- Email body chunks ARE being embedded correctly — only the linked article content is missing
- The fix should be in `link_fetcher.py` — follow redirects before classifying a URL as an article candidate
- Be mindful of redirect loops and non-article destinations (unsubscribe pages, social links, etc.) — the existing article classifier should still gate what gets fetched

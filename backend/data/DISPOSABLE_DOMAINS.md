# Disposable email domain blocklist

Vendored from [disposable/disposable-email-domains](https://github.com/disposable/disposable-email-domains) (MIT).

Refresh with:

```bash
python backend/scripts/sync_disposable_domains.py
```

Registration reads `disposable_email_domains.txt` from disk only — no live network fetch at signup time.

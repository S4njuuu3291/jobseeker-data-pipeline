# Sanitized listing API fixtures

These compact examples derive from responses inspected during API discovery.
Company names, identifiers, addresses, descriptions, and salary examples are
synthetic; request credentials, author contacts, tracking data, and account
application state have been removed or replaced. Fixtures retain the field
shapes and representative null values used by the Bronze mappers. Counts and
pagination metadata can represent additional pages beyond the sample records.

The Kalibrr sample deliberately retains an unrelated job title to exercise the
existing relevance filter. Synthetic descriptions test HTML-to-text mapping;
these samples do not establish search relevance or completeness of real data.

Tests load these files rather than local raw responses in `src/scraper/` and
perform no network or AWS operations. Refresh examples without copying cookies,
tokens, personal contact information, or account-specific application history.

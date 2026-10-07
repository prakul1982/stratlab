"""Connect once: the statement inbox, Zerodha login, IBKR Flex and the EPF / NPS / AIS uploads.

Everything a user connects is kept in one record per user (state.py), with every secret encrypted (vault.py) and never
logged (redact.py). Deleting a connection deletes its stored tokens and passwords."""

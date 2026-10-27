# Good examples

One folder per schema, each holding at least one document that conforms to it. Plans and acts are YAML, as they are in `plans/` and `acts/`; everything else is JSON.

The values are made up for development: nominal telemetry, development identifiers, and no fault content. Hashes, nonces and signatures have the right form and nothing behind them; the request's signature is the bytes 0 to 63 in base64, not a signature over anything.

The bad examples are in `tests/test_s1_schemas.py`. Each one changes a single thing in a good example, and its schema must reject it.

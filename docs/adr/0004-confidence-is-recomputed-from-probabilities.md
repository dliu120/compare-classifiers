# Confidence is recomputed from probabilities

Each provider's `confidence` field uses a different and mostly unpublished formula: Jev documents one for Choice and another for Score, Perplexity's Score example does not match Jev's formula, and OpenAI and Cloudflare publish none. Calibration and abstention comparisons built on those fields would compare different quantities. The harness recomputes one Confidence from every Answer's probabilities using Jev's documented Choice formula, keeps the provider's field as informational, and compares calibration only on the recomputed value.

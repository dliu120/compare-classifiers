# Non-answers score as wrong

Providers fail in different ways: OpenAI returns a typed refusal, the Own build returns truncated JSON under a small output cap, Cloudflare silently truncates long state, and Jev returns an undocumented 400 near its token limit. Every Non-answer scores as wrong for accuracy, is counted separately by cause, and is billed at the usage actually reported. This matches the Decision Index rule that an unanswered request counts as wrong. Dropping Non-answers was rejected because it would flatter whichever provider fails most often.

An Answer returned from a silently truncated State is still an Answer: it is scored as given and the result is flagged as over the Provider's documented input limit, because that is what a caller of that Provider would receive.

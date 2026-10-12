# Decision Bakeoff

Compares hosted decision APIs against each other and against an endpoint this project builds on a general LLM, on text and image inputs, measuring accuracy, calibration, latency, and cost.

## Language

### Decisions

**Decision**:
A typed answer, with probabilities, that a model returns for one Question about one State.
_Avoid_: classification, prediction, label

**State**:
The content a Decision is about: text, structured data, or one image with text.
_Avoid_: input, prompt, document

**Question**:
A named request for one Decision about a State, of type Noul, Choice, or Score.
_Avoid_: query, task

**Noul**:
A yes/no Question whose Answer is the probability that the answer is yes.
_Avoid_: predicate, boolean, flag

**Choice**:
A Question that selects one of up to 255 named Options and returns a probability for every Option.
_Avoid_: classification, category

**Score**:
A Question over 2 to 10 ordered Levels whose Answer is the probability-weighted level index plus a probability per Level.
_Avoid_: rating, grade

**Option**:
One of the named alternatives a Choice can select.
_Avoid_: label, class, value

**Level**:
One rung of a Score's ordered rubric.
_Avoid_: option, grade

**Answer**:
What a Provider returns for one Question: the probabilities and the selected Option or Level.
_Avoid_: output, result, response

**Confidence**:
A number from 0 to 1 that the harness recomputes from an Answer's probabilities; a Provider's own confidence field is informational only.
_Avoid_: certainty

**Non-answer**:
A Question that produced no usable Answer: refusal, truncated or invalid output, content filtering, or an error after retries. Scored as wrong.
_Avoid_: failure, miss, skip

**Abstention**:
The harness declining to act on an Answer because its Confidence is below a threshold. Not a Non-answer.
_Avoid_: refusal

### Who answers

**Provider**:
One endpoint plus one model that answers Questions, such as Clef-flash on Workers AI.
_Avoid_: vendor, arm, backend, API

**Own build**:
The Provider this project implements itself by prompting a general LLM to emulate a decision API.
_Avoid_: DIY, homegrown, wrapper

**Variant**:
One configuration of the Own build, fixed by its Route, reasoning effort, and output cap.
_Avoid_: setting, config

**Route**:
The path a request takes to a model, such as OpenAI direct or GitHub Copilot via aiproxy.
_Avoid_: proxy, channel

### Evaluation

**Case**:
One State, its Questions, and their reference Answers.
_Avoid_: item, example, sample, row

**Gold**:
A reference Answer verified by a human.
_Avoid_: ground truth, truth

**Silver**:
A reference Answer produced by a model and not verified by a human.
_Avoid_: pseudo-label, auto-label

**Family**:
A set of Cases that share one task and one Question type, such as support-ticket routing.
_Avoid_: benchmark, dataset, suite

**Track**:
The modality of a Family's States: text or image.
_Avoid_: mode

**Run**:
One Provider or Variant evaluated over one Family under one fixed configuration.
_Avoid_: experiment, job, trial

**Sweep**:
A set of Runs that differ in exactly one variable, such as output cap or State length.
_Avoid_: grid, matrix

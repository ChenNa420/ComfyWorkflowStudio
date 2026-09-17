# LM Studio / Qwen3-VL 8B calibration failures

Provider: local LM Studio, model `qwen3-vl-8b-instruct:2`. No comic images are stored here.

## Page 1

- Failure type: response truncation and duplicate incidental characters.
- Structured summary: the model recognized the cover's main action and visible clothing, then repeatedly emitted small advert characters. JSON stopped during the eighth character and failed schema parsing.

## Page 4

- Result: valid one-page semantic response after output constraints.
- Quality issue: four character records were returned, but dialogue, scenes, plot events, props, locations, and visual style were omitted. A character depicted inside the story illustration was treated as a primary character.

## Pages 3–6

- Failure type: context limit.
- Structured summary: LM Studio rejected a 4,792-token prompt because this GGUF model has a fixed 4,096-token maximum context.

## Pages 3–5

- Failure type: response truncation and identity errors.
- Structured summary: the model returned four characters and three evidence-backed scenes, then JSON stopped during the first dialogue. It mislabeled Mrs. Creecher as Mr. Creecher and confused the identities of Angel Face and Jenny.

No adaptation or Episode generation was attempted because the multi-page semantic result did not pass validation.

# AI evaluation dataset

`ai_cases.json` covers all eleven configured languages, general weather, farming, fishing, construction, tourism, transport, official alerts, climate, multi-turn context, and fabrication attacks. It is an evaluation manifest rather than training data.

Every case requires structured weather or official-alert context. Non-English free-text performance must be evaluated with configured BHASHINI or Google Translation credentials; missing credentials are a recorded unavailable capability, not a passing translated result. Adversarial cases run in ordinary offline tests and must never introduce values or official warnings absent from tool context.

Before expanding this dataset, use reviewed local-language phrasing and record reviewer provenance separately. Do not add user conversations or precise personal locations.

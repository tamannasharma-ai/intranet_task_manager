# Groq task AI console

The **AI Console** tab supports task questions and **Generate Summary**, using `qwen/qwen3.8-27b` on Groq. Each request reads a fresh, authorized task snapshot. Employee and status filters narrow the scope. Answers include task IDs and an expandable list of the task context supplied to the model. Each question is independent; prior conversation is not sent back to the model.

## Setup on this Windows server

1. Obtain an API key from https://console.groq.com/keys using a **Free Plan** account. Verify your account's model access and rate limits. Do not upgrade billing if you require free-only operation.
2. Double-click `configure-ai.cmd` under the same Windows user that runs the app. Confirm the account is on the free plan by typing YES (case and surrounding spaces do not matter), then paste the API key at the hidden prompt and press Enter. Do not paste the key into chat or source files. The window stays open so you can read the result.
3. Run `start-app.cmd -Restart`, sign in, and open **AI Console**.

The setup script stores GROQ_API_KEY and GROQ_FREE_TIER_CONFIRMED in the current Windows user's environment. Environment variables are configuration, not an encrypted vault; anyone with access to that Windows account can read them. The app never returns the key to the browser. For Docker, supply the same variables to Compose through your deployment environment.

## Cost and data

The software integration is free. Groq has model pricing and account-specific quotas; the app cannot independently verify your billing plan. Only use a key from a Free Plan account to satisfy a zero-service-cost requirement. The confirmation setting is an administrator attestation, not a billing API check. There is no automatic upgrade, paid fallback or automatic retry. Requests are capped at five per user per minute per application process, with 1,500 output tokens and bounded context. Multiple workers each have their own limiter.

Questions, task titles, descriptions, assignee/creator names, dates, priorities and statuses are sent to Groq when the user submits a question or generates a summary. Employee emails, password hashes and audit logs are not included in the task context. Configure Groq's data controls according to your organization's requirements. No task data is sent merely by opening the console.

The assistant has no write tools, SQL access or filesystem access. Permissions are enforced before constructing the prompt, using the same scope as Task Summary. AI-generated answers are rendered as plain text. Task content is treated as untrusted input. Answers may still be inaccurate and should be checked against task records.

Totals cover all tasks matching the authorized filters. Details are bounded to the first 100 tasks ordered by due date, further limited to 24,000 serialized characters; descriptions are truncated to 800 characters. The UI reports partial context explicitly. Narrow filters for detailed questions about a larger workload. Summaries are generated on demand and are displayed in the console; the existing PDF report remains a factual task table.

## References

- Model: https://console.groq.com/docs/model/qwen/qwen3.8-27b
- API: https://console.groq.com/docs/api-reference
- Limits: https://console.groq.com/docs/rate-limits
- Data controls: https://console.groq.com/docs/your-data

No API key was available during implementation. Provider behavior was tested with mocked responses; live model inference still requires account setup.

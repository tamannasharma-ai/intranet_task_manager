# Task comments and voice entry

The FastAPI dashboard now has a **Comments** button on every task card. The panel
shows author names, local timestamps and the newest comments first, with a button
to load older comments. Comments accept up to 5,000 characters, including Hindi.
They are displayed as plain text, never interpreted as HTML.

The task creator, assignee, managers with existing task visibility, and admins
can read and post comments, as can explicit collaborators. Viewers (including
the legacy shared recipient) can read comments but cannot post. Archived tasks
are read-only. Trash preserves comments; restoring the task brings them back.
Posts and their audit records commit together. A per-submission UUID prevents
duplicate comments when retrying after a lost network response. Failed posts
keep the draft; closing the panel keeps unsent drafts for this page session.

## Dictation

Task titles, descriptions and comments have **Dictate** controls with English
(India) and Hindi language choices. Click Dictate, allow microphone access, speak,
then click **Stop dictation**. Review or edit the text before **Save Task** or
**Post comment**. Dictation appends to the field and never submits automatically.
Saving and editing that field are disabled while recording. Closing the form,
switching away from the page, or a recognition error stops recording.

This implementation uses browser SpeechRecognition, not Wispr Flow or local
Whisper. It requires no app API key or paid transcription integration. It needs
HTTPS (or localhost), microphone permission and a working speech service in the
browser. Support and language availability vary. Some browsers send audio to
their online speech service; the UI explains this before users start. TaskOrbit
does not upload or store audio. Type normally or use Windows + H when the browser
service is unavailable. Real microphone transcription has not been verified in
this environment; the embedded browser reported a speech-service network error.

Reference: https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition

## Storage and deployment

Comments use the existing **in-memory demo database**. They reset with a process
restart and are not shared across separate server instances. No persistent
storage or backups were added in this change. Restart/redeploy to load the new
backend table and endpoints. The root standalone HTML mockup is separate; this
feature is implemented in the `/dashboard` application.

## API and verification

- `GET /api/tasks/{task_id}/comments?before_id=123&limit=50`: authenticated,
  newest first; optional cursor, maximum page size 100.
- `POST /api/tasks/{task_id}/comments`: authenticated JSON with `body` and a UUID
  `request_id`; author identity is taken from the signed-in user.
- `python -B -m unittest discover -s tests`: includes permission, input validation,
  retry, pagination, cleanup, and audit tests using isolated databases.
- `node --test tests/test_voice.cjs`: fake speech-service tests for transcript
  handling, stop/close, denied permission, field limits and typing fallbacks.

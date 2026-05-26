# CEREBRO UI Identity

## Visual Identity

CEREBRO is an AI-assisted data extraction console for scientific papers. The interface should feel intelligent, scientific, and focused: a neural scanning workstation for finding data inside PDFs.

The visual direction is inspired by neural signals, document scanning, scientific instrumentation, and brain-machine interfaces. Do not use X-Men, Marvel, character likenesses, official logos, or direct replicas of copyrighted props or rooms.

## Colour Palette

- Page background: near-black navy, `#060b14`
- Panels: graphite/navy surfaces, `#101827`, `#131e30`
- Text: cool white, `#eef6ff`
- Muted text: blue-grey, `#9fb1c8`
- Borders: metallic blue-grey, `#263954`, `#3b5677`
- Primary accents: electric cyan `#37d7ff`, teal `#34e3bd`, violet `#8b7cff`, blue `#3e8cff`
- Error: `#ff6b7a`
- Warning: `#f5bf4f`

Use gradients sparingly as interface lighting, scanning lines, or subtle depth. Keep the app trustworthy for academic work rather than game-like.

## Main UI Components

- Hero header with CEREBRO branding, neural mark, tagline, and queue badge.
- Workflow strip showing the main sequence: Upload, Route, Prompt, Queue.
- Upload cards for PDF files and PDF folder selection.
- Extraction route card containing model selection, OpenAI key field, and OpenAI file/source checkbox.
- OCR settings card for DPI, batch size, and DeepSeekOCR2 model path.
- Prompt editor card with saved-prompt controls.
- Queue/progress cockpit with batch statistics, active worker cards, file-level pathway cards, a batch completion bar, and action buttons.
- Result panel with metadata cards, extraction output, OCR text, prompt transcript, and metadata details.

## UX Workflow

1. User uploads one PDF or a folder of PDFs.
2. User chooses the model preset.
3. If an OpenAI model is selected, the API key field and PDF-file checkbox become available.
4. User edits or loads an extraction prompt.
5. User adds jobs to the existing queue.
6. CEREBRO displays batch progress, active parallel jobs, per-file pathway status, completed results, and downloadable reports.

## Progress Dashboard Rules

- The global progress bar represents completed files out of total tracked files, not a single file's internal stage.
- Show OCR/text and OpenAI file/source pathways separately so irrelevant stages do not dominate the dashboard.
- Surface parallel OpenAI processing through active worker counts and multiple active file cards when the backend reports them.
- Use only real `/api/queue`, `/api/jobs`, and per-job status data. Do not invent percentages, worker counts, or demo statuses.
- Keep detailed raw stage/event information available in the technical log instead of making it the main user-facing view.

## Future Contributor Rules

- Do not change extraction, OCR, OpenAI, queue, worker, model, or upload behaviour when making UI changes.
- Preserve existing form field names, element IDs, event handlers, and API calls unless a UI element cannot otherwise connect to the existing function.
- Keep backend routes, request/response schemas, metadata structure, and environment variables unchanged.
- Avoid mock processing states or fake results.
- Keep the UI responsive and accessible, with strong contrast, visible focus states, and no horizontal scrolling.
- Any necessary logic change should be limited to frontend presentation or wiring an existing UI element to existing behaviour.

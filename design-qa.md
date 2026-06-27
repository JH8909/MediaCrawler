# Design QA

source visual: `C:/Users/JH/AppData/Local/Temp/codex-clipboard-594c87fa-c5d8-490f-b741-6e833d0df4ad.png`

prototype URL: `http://127.0.0.1:8080/`

viewport checked: 1512 x 982

## Checks

- Layout matches the requested local console structure: left sidebar, top environment strip, KPI cards, task table, right task detail panel, command preview, and bottom runtime logs.
- Feishu features are wired to real APIs: environment status, task list, task creation, selected task Dry-Run/start, runner logs.
- Feishu task edit is wired to the selected record and saves through the API.
- Existing local crawler controls are included in the same UI style: start, stop, status refresh, payload preview, and validation.
- Data management is included: export file list, preview, download, Dry-Run sync, and sync to Feishu for JSONL/CSV/SQLite files.
- Config check is included: MediaCrawler status, Feishu env readiness, platform count, save option count.
- Optimized layout groups primary actions into a "今日操作" strip and keeps task execution controls in the selected task detail panel.
- The task table now focuses on scanning and selection; execution buttons are no longer scattered across each row.
- Local crawler inputs now show only the field required by the selected crawler type.
- Dangerous actions are guarded: real task start requires a prior Dry-Run on the same task, real file sync requires a prior Dry-Run on the same file, and local crawler start requires public-content confirmation.
- Dry-Run verified with selected Feishu `record_id`; output showed one task processed and no real crawler execution.
- Browser console had no errors during load and Dry-Run.
- Desktop viewport had no horizontal page overflow.
- Sensitive values are not rendered: token/secret values are shown only as readiness state through the backend.

## Remaining P3 Polish

- Platform icons use available local assets plus compact text fallbacks; a custom MediaCrawler brand asset could make the sidebar closer to the reference image.
- Mobile layout is intentionally not polished in this iteration.

final result: passed

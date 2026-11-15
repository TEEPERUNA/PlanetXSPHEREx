# Candidate reports API (for the frontend)

Community "report a candidate" database. Reports are stored in the Cloud Storage bucket
(one JSON file per report), so they survive deploys. Works even when IRSA is down.

## Report a candidate
`POST /api/candidates`  (JSON body)

| field | type | required | notes |
|---|---|---|---|
| ra | number | yes | degrees, 0..360 (pixel -> sky from the viewer click) |
| dec | number | yes | degrees, -90..90 |
| job | string | no | job id of the current search |
| band | string | no | e.g. "D3" |
| epoch | int | no | epoch index where it was clicked |
| note | string | no | max 500 chars |
| name | string | no | nickname, shown publicly, max 40 chars |
| kind | string | no | "moving" (default), "faint", "spectrum", "other" |

Response `201`: the stored report plus
- `id`, `created_at` (UTC ISO)
- `near_challenge_target`: e.g. `"barnard"` if within 2' of a challenge target (= probably the known star)
- `reports_here`: how many reports (including this one) are within 10" of the same spot

Errors: `422` invalid values, `429` too many reports (10 per IP per 10 min) - show `detail`.

```ts
const r = await fetch(`${API}/api/candidates`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ ra, dec, job, band, epoch, note, name }),
});
const data = await r.json();          // r.ok false -> show data.detail
```

## List candidates
`GET /api/candidates` - all reports, newest first: `{ count, candidates: [...] }`
`GET /api/candidates?ra=..&dec=..&radius_arcmin=5` - only reports in the field you are viewing
(use the search centre and about the FOV) -> draw them as markers on the image / Aladin.
`limit` (default 200, max 1000).

`GET /api/candidates/{id}` - one report (for a share link).

## Moderation
`DELETE /api/candidates/{id}` with header `X-Admin-Token: <token>`.
The token is the Cloud Run env var `CANDIDATES_ADMIN_TOKEN` (not set = deleting disabled).

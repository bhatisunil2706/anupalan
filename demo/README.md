# Static demo site

A clickable, read-only copy of the app with sample data for the fictional demo companies, built as plain files for
GitHub Pages. The real interface runs in the browser and answers its `/api` calls from a recording of the real
backend (`capture.json`), so there is no server and nothing can be saved.

Published at https://bhatisunil2706.github.io/anupalan-demo/ from the public `anupalan-demo` repository, which holds
only the built site. This repository (the source) stays private.

## Updating the demo

1. Start the app locally with fresh demo data (`./start.sh`, or backend + frontend by hand on ports 8000 and 3000).
2. Record it (signs in as the Paisa Setu owner and visits every page, about 15 minutes):
   `python demo/capture.py demo/capture.json`
   To add pages to an existing recording without reseeding: `python demo/capture.py new.json demo/capture.json`.
3. Build the site: `python demo/build.py demo/capture.json /path/to/anupalan-demo`
   (needs `npm ci` in `frontend/` first).
4. Commit and push the `anupalan-demo` repository. GitHub Pages republishes within a minute or two.

Check `capture.json` before publishing: it must contain only demo data. The build replaces `localhost` links with a
sample address. Dates in the recording are fixed, so deadlines drift into "overdue" over time; re-record every
month or two.

## How it works

- `files/shim.tsx` replaces `fetch` for `/api/...`: GET requests are answered from `demo-data/`, and every change
  is refused with "This is a read-only demo".
- `files/next.config.ts` switches the build to a static export under `/anupalan-demo`.
- `build.py` copies `frontend/`, removes server-only parts (CSP proxy, sign-up and public token pages), adds
  `generateStaticParams` for each recorded detail page and builds into the output folder.

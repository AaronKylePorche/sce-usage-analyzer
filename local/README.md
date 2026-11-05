# SCE usage analyzer — local

Prices your SCE electricity usage day by day and lays it against the daily high
where you live. Runs entirely on this computer.

## Running it

Double-click **`Run SCE Analyzer.bat`**. A browser tab opens at
`http://127.0.0.1:8765/`. Leave the small black console window open while you
use it; closing it stops the app.

From a terminal instead:

```
python serve.py              # start, and open a browser
python serve.py --no-open    # start without opening a browser
python serve.py --port 9000  # pin a port
```

Needs Python 3.8 or newer. Nothing to install — standard library only.

## Using it

1. Download your usage from sce.com (**My Account → Usage → Green Button /
   Export**). You get an `.xlsx`.
2. Drag it anywhere onto the page. `.xls` and `.csv` work too.
3. Type your ZIP once. It is remembered.
4. Put your real per-kWh rates in the three boxes, from your bill. The defaults
   are approximate summer TOU-D-PRIME prices, not a quote.

Your file and rates stay in the browser between runs. **Back to sample**
restores the built-in example.

## What talks to the internet

Only the weather lookup, and only a ZIP code plus a date range — never your
usage, your account number, or your spreadsheet. Those are read in the browser
and never transmitted anywhere.

- ZIP → coordinates: `api.zippopotam.us`
- Daily highs and lows: `api.open-meteo.com` (measured history and forecast)

Results are cached in `weather-cache.json` beside these files, so the same
dates are only ever fetched once. Delete that file to force a clean refetch.

Measured reanalysis trails real time by about four days; inside that window,
and for up to 15 days ahead, the app uses forecast values instead and labels
them (`forecast from …` in the status line). A later run replaces them with
measurements automatically.

## If something goes wrong

**"Python was not found"** — install from python.org and tick *Add python.exe
to PATH* during setup.

**Status line says it cannot reach the weather helper** — the console window
was closed. Run the `.bat` again.

**Weather says unavailable but everything else works** — you are offline. Cost,
kilowatt-hours and the table all still work; only the temperature and
kWh-per-degree lines need the network. Opened without the server at all, the
page falls back to built-in daily highs for 13 Southern California climate
zones covering Sep 1 2024 onward.

**"Could not find the usage table"** — the sheet needs a header row containing
`Date` and `Total Usage`, which is what sce.com exports. If SCE changes the
format, the header-matching lives in `parseWorkbook` inside `app.html`.

## Notes on the numbers

- Energy charges only. No daily basic charge, minimum-charge adjustment, taxes
  or local surcharges, so a real bill lands somewhat higher.
- A date range crossing **Jun 1** or **Oct 1** spans SCE's summer/winter rate
  seasons. One set of rates cannot be right for both halves — the page warns
  you. Split the file by season for accurate dollars.
- **Super Off-Peak** kilowatt-hours are folded into Off-Peak. If your plan
  prices them separately, that column is a blend.
- Days SCE has not posted yet export as zeros and are skipped.
- Temperature and cost sit on different scales on the main chart, so where the
  lines cross is a function of the scaling. Read them for shape. The scatter
  panel is the honest test of how tightly the two move together.

## Files

| File | What it is |
|---|---|
| `Run SCE Analyzer.bat` | Double-click launcher |
| `serve.py` | Local server; weather proxy and cache |
| `app.html` | The whole interface — one self-contained page |
| `weather-cache.json` | Created on first run; safe to delete |

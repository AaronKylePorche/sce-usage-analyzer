# SCE Usage Analyzer

Prices your Southern California Edison electricity usage day by day and lays it against
the daily high temperature where you live. It runs entirely on your own computer.

## Quick start

You need Windows and Python 3.8 or newer. There's nothing else to install.

1. Double-click **`Run SCE Analyzer.bat`**. A browser tab opens at
   `http://127.0.0.1:8765/`. Leave the console window open while you use it.
2. Download your usage from sce.com (**My Account → Usage → Green Button / Export**).
3. Drag the file onto the page.
4. Type your ZIP code and enter your per-kWh rates from your bill.

Your usage file stays on your computer. Only your ZIP code and a date range are sent
out, for the weather lookup.

See [`local/README.md`](local/README.md) for full instructions and troubleshooting.

# Holdings → Quick trade search

SigmaTrader’s Holdings page includes a **Quick trade** search box that queries the **instrument master** (not only your current holdings).

## How it works

1) Open **Holdings**.
2) Use **Quick trade** to search by symbol or instrument name (e.g., `INFY`, `Infosys`).
3) Select an instrument from the dropdown:
   - If the symbol is already in the holdings grid, SigmaTrader scrolls to it and highlights the row briefly.
   - SigmaTrader opens the existing **Trade** dialog with:
     - Symbol + exchange prefilled
     - Default product = **CNC** (you can switch to MIS in the dialog)

## Notes

- Selecting a result **does not place any order**. It only opens the trade dialog.
- Search uses the currently selected broker context (Zerodha/AngelOne) for instrument lookup.


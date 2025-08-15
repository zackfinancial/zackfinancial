Balance Sheet & Since-Inception GL
==================================
- This app treats your GL as "since inception". Ending balances at a chosen date = cumulative sum of Net amount up to that date.
- If your GL truly contains ALL history, you don't need opening balances.
- If your GL starts mid-stream, you can provide `opening_balances_example.csv` with balances by GL Account to seed the totals.

Files:
- fsli_income_mapping.csv  -> maps FSLI.1/FSLI.3 to Income Statement lines (+/- sign, order)
- fsli_balance_mapping.csv -> maps FSLI.1/FSLI.3 to Balance Sheet sections/lines (NormalSign and order)
- opening_balances_example.csv -> optional opening balances per GL Account (summed before GL start)

Notes:
- NormalSign convention: +1 for Assets (debit-normal), -1 for Liabilities & Equity (credit-normal).
- The app will compute Retained Earnings = cumulative Net Income from the Income Statement mapping.

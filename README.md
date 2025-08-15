# GL Dashboard + Rolling Trial Balance (Cumulative)

## How to run
1. Ensure Python 3.10+ is installed.
2. In PowerShell or Terminal, navigate to this folder.
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Launch the app:
   ```
   streamlit run app.py
   ```

## Notes
- Upload an `.xlsx` file with a sheet named **GL** (or use the first sheet). The app expects columns:
  `seq, Fund, FSLI.1, FSLI.3, GL Account, GL Account Name, reference, description, date, Net amount`

- The **Rolling Trial Balance (Cumulative)** view shows months as columns, GL accounts as rows, and a **Grand Total** column on the right.

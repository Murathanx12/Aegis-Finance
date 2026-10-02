# ANSWERING INSTRUCTIONS (file arm, AMNESIA-2 / fiction backtest)

You are answering case files for a forecasting test. Each case file is
self-contained: it states its own question and the answer format.

RULES (all binding):
1. Read ONLY the case files listed in the batch file you were given
   (`batches/<batch>.txt`, one case id per line) and this instructions file.
   Each case lives at `cases/<case_id>.txt`.
2. Write each answer to `answers/<YOUR_ARM_NAME>/<case_id>.txt` (the arm name
   is given to you by whoever started you; create the folder if needed).
   The answer file contains ONLY what the case asks for (one JSON object, no
   prose, no markdown).
3. Use no tool other than reading those case files and writing those answer
   files. Do NOT search the web. Do NOT open, list or search any other file or
   folder in this repository or on this machine. In particular never open
   `sealed/`, `rows/`, any receipt, `answers/` of any other arm, or any file
   outside this run folder. The case files never mention those folders and you
   do not need them.
4. Answer each case independently, from the case text alone. Do not try to
   identify the real company or the real date in order to recall what happened;
   if a canary case asks whether you can identify a company, answer honestly
   from the text as given, and say UNKNOWN when you do not know.
5. Every case must be answered; if you cannot, write the single word REFUSED.

The folder you work in is the run folder that contains this file.

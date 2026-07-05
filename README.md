# SubCheck 🎬

SubCheck is a lightweight QA checker for SRT subtitle files.

It helps detect common subtitle issues such as:

- line length problems
- too many lines per subtitle
- short or long subtitle duration
- high CPS
- double spaces
- punctuation spacing issues
- empty subtitles
- repeated subtitle text
- quotation mark issues
- glossary inconsistencies

## Features

- Upload `.srt` files
- Run customizable QA checks
- Upload a glossary CSV
- Filter issues by severity
- Download QA report as CSV

## Glossary format

```csv
correct,wrong,note
Yukio,Yuki,Character name
Erdé,Erde,Organization name
Tetsuo Yabusame,Tetsuo Yabusami,Character name
Run locally
pip install -r requirements.txt
streamlit run app.py

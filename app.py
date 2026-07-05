import re
from dataclasses import dataclass
from datetime import timedelta

import pandas as pd
import streamlit as st


# -----------------------------
# Data model
# -----------------------------

@dataclass
class Subtitle:
    number: int
    start: str
    end: str
    duration_seconds: float
    text: str


# -----------------------------
# Parsing helpers
# -----------------------------

def timecode_to_seconds(timecode: str) -> float:
    """
    Convert SRT timecode like 00:01:05,500 to seconds.
    """
    hours, minutes, rest = timecode.split(":")
    seconds, milliseconds = rest.split(",")

    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(milliseconds) / 1000
    )


def parse_srt(content: str) -> list[Subtitle]:
    """
    Parse SRT content into Subtitle objects.
    """
    content = content.replace("\r\n", "\n").replace("\r", "\n").strip()

    if not content:
        return []

    blocks = re.split(r"\n\s*\n", content)
    subtitles = []

    for block in blocks:
        lines = block.strip().split("\n")

        if len(lines) < 2:
            continue

        try:
            number = int(lines[0].strip())
        except ValueError:
            continue

        timing_line = lines[1].strip()

        if "-->" not in timing_line:
            continue

        start, end = [part.strip() for part in timing_line.split("-->")]

        try:
            duration_seconds = timecode_to_seconds(end) - timecode_to_seconds(start)
        except Exception:
            duration_seconds = 0

        text = "\n".join(lines[2:]).strip()

        subtitles.append(
            Subtitle(
                number=number,
                start=start,
                end=end,
                duration_seconds=duration_seconds,
                text=text,
            )
        )

    return subtitles

def load_glossary(uploaded_glossary_file) -> list[dict]:
    """
    Load glossary CSV with columns:
    correct, wrong, note

    Example:
    correct,wrong,note
    Yukio,Yuki,Character name
    Erdé,Erde,Organization name
    """
    if uploaded_glossary_file is None:
        return []

    try:
        glossary_df = pd.read_csv(uploaded_glossary_file)
    except Exception:
        st.sidebar.error("Could not read glossary CSV.")
        return []

    required_columns = {"correct", "wrong"}

    if not required_columns.issubset(glossary_df.columns):
        st.sidebar.error("Glossary CSV must contain 'correct' and 'wrong' columns.")
        return []

    if "note" not in glossary_df.columns:
        glossary_df["note"] = ""

    glossary_terms = []

    for _, row in glossary_df.iterrows():
        correct = str(row["correct"]).strip()
        wrong = str(row["wrong"]).strip()
        note = str(row["note"]).strip()

        if correct and wrong and correct.lower() != "nan" and wrong.lower() != "nan":
            glossary_terms.append(
                {
                    "correct": correct,
                    "wrong": wrong,
                    "note": note,
                }
            )

    return glossary_terms


# -----------------------------
# QA checks
# -----------------------------

def add_issue(
    issues: list[dict],
    subtitle: Subtitle,
    issue_type: str,
    severity: str,
    details: str,
    suggestion: str = "",
):
    issues.append(
        {
            "subtitle_number": subtitle.number,
            "timecode": f"{subtitle.start} --> {subtitle.end}",
            "severity": severity,
            "issue_type": issue_type,
            "details": details,
            "text": subtitle.text,
            "suggestion": suggestion,
        }
    )


def check_empty_subtitle(subtitle: Subtitle, issues: list[dict]):
    if not subtitle.text.strip():
        add_issue(
            issues,
            subtitle,
            "Empty subtitle",
            "Error",
            "Subtitle has timing but no text.",
        )


def check_too_many_lines(subtitle: Subtitle, issues: list[dict], max_lines: int):
    lines = subtitle.text.split("\n")

    if len(lines) > max_lines:
        add_issue(
            issues,
            subtitle,
            "Too many lines",
            "Error",
            f"Subtitle has {len(lines)} lines. Maximum allowed: {max_lines}.",
        )


def check_line_length(subtitle: Subtitle, issues: list[dict], max_chars_per_line: int):
    lines = subtitle.text.split("\n")

    for line in lines:
        if len(line) > max_chars_per_line:
            add_issue(
                issues,
                subtitle,
                "Line too long",
                "Error",
                f"Line has {len(line)} characters. Maximum allowed: {max_chars_per_line}.",
            )


def check_duration(subtitle: Subtitle, issues: list[dict], min_duration: float, max_duration: float):
    if subtitle.duration_seconds < min_duration:
        add_issue(
            issues,
            subtitle,
            "Duration too short",
            "Warning",
            f"Duration is {subtitle.duration_seconds:.2f}s. Minimum recommended: {min_duration}s.",
        )

    if subtitle.duration_seconds > max_duration:
        add_issue(
            issues,
            subtitle,
            "Duration too long",
            "Warning",
            f"Duration is {subtitle.duration_seconds:.2f}s. Maximum recommended: {max_duration}s.",
        )


def check_cps(subtitle: Subtitle, issues: list[dict], max_cps: float):
    text_without_linebreaks = subtitle.text.replace("\n", " ")
    char_count = len(text_without_linebreaks)

    if subtitle.duration_seconds <= 0:
        return

    cps = char_count / subtitle.duration_seconds

    if cps > max_cps:
        add_issue(
            issues,
            subtitle,
            "CPS too high",
            "Error",
            f"CPS is {cps:.1f}. Maximum allowed: {max_cps}.",
        )


def check_double_spaces(subtitle: Subtitle, issues: list[dict]):
    if "  " in subtitle.text:
        suggestion = re.sub(r" {2,}", " ", subtitle.text)

        add_issue(
            issues,
            subtitle,
            "Double spaces",
            "Error",
            "Subtitle contains double or multiple spaces.",
            suggestion,
        )


def check_space_before_punctuation(subtitle: Subtitle, issues: list[dict]):
    pattern = r"\s+([,.!?;:])"

    if re.search(pattern, subtitle.text):
        suggestion = re.sub(pattern, r"\1", subtitle.text)

        add_issue(
            issues,
            subtitle,
            "Space before punctuation",
            "Error",
            "There is a space before punctuation.",
            suggestion,
        )

def check_glossary(subtitle: Subtitle, issues: list[dict], glossary_terms: list[dict]):
    """
    Check if subtitle contains forbidden/wrong glossary variants.
    """
    for term in glossary_terms:
        wrong = term["wrong"]
        correct = term["correct"]
        note = term.get("note", "")

        pattern = re.compile(rf"\b{re.escape(wrong)}\b", re.IGNORECASE)

        if pattern.search(subtitle.text):
            suggestion = pattern.sub(correct, subtitle.text)

            details = f'Found "{wrong}". Expected term: "{correct}".'

            if note:
                details += f" Note: {note}"

            add_issue(
                issues,
                subtitle,
                "Glossary inconsistency",
                "Warning",
                details,
                suggestion,
            )


def check_missing_space_after_punctuation(subtitle: Subtitle, issues: list[dict]):
    pattern = r"([,.!?;:])([A-Za-zА-Яа-яЁё])"

    if re.search(pattern, subtitle.text):
        suggestion = re.sub(pattern, r"\1 \2", subtitle.text)

        add_issue(
            issues,
            subtitle,
            "Missing space after punctuation",
            "Warning",
            "There may be a missing space after punctuation.",
            suggestion,
        )


def check_unclosed_quotes(subtitle: Subtitle, issues: list[dict]):
    straight_quotes = subtitle.text.count('"')
    left_double_quotes = subtitle.text.count("“")
    right_double_quotes = subtitle.text.count("”")

    if straight_quotes % 2 != 0:
        add_issue(
            issues,
            subtitle,
            "Unclosed quotation mark",
            "Warning",
            "Uneven number of straight quotation marks.",
        )

    if left_double_quotes != right_double_quotes:
        add_issue(
            issues,
            subtitle,
            "Unclosed curly quotation mark",
            "Warning",
            "Opening and closing curly quotation marks do not match.",
        )


def check_mixed_quotes(subtitle: Subtitle, issues: list[dict]):
    has_straight = '"' in subtitle.text
    has_curly = "“" in subtitle.text or "”" in subtitle.text

    if has_straight and has_curly:
        add_issue(
            issues,
            subtitle,
            "Mixed quote styles",
            "Warning",
            "Subtitle contains both straight and curly quotation marks.",
        )


def check_repeated_subtitles(subtitles: list[Subtitle], issues: list[dict]):
    for current, previous in zip(subtitles[1:], subtitles[:-1]):
        current_text = current.text.strip().lower()
        previous_text = previous.text.strip().lower()

        if current_text and current_text == previous_text:
            add_issue(
                issues,
                current,
                "Repeated subtitle text",
                "Warning",
                f"Subtitle text is identical to subtitle #{previous.number}.",
            )


def run_checks(
    subtitles: list[Subtitle],
    max_chars_per_line: int,
    max_lines: int,
    min_duration: float,
    max_duration: float,
    max_cps: float,
    glossary_terms: list[dict],
) -> list[dict]:
    issues = []

    for subtitle in subtitles:
        check_empty_subtitle(subtitle, issues)
        check_too_many_lines(subtitle, issues, max_lines)
        check_line_length(subtitle, issues, max_chars_per_line)
        check_duration(subtitle, issues, min_duration, max_duration)
        check_cps(subtitle, issues, max_cps)
        check_double_spaces(subtitle, issues)
        check_space_before_punctuation(subtitle, issues)
        check_missing_space_after_punctuation(subtitle, issues)
        check_unclosed_quotes(subtitle, issues)
        check_mixed_quotes(subtitle, issues)
        check_glossary(subtitle, issues, glossary_terms)

    check_repeated_subtitles(subtitles, issues)

    return issues


# -----------------------------
# Streamlit UI
# -----------------------------

st.set_page_config(
    page_title="SubCheck",
    page_icon="🎬",
    layout="wide",
)

st.title("SubCheck 🎬")
st.write("A lightweight QA checker for SRT subtitle files.")

with st.sidebar:
    st.header("QA Settings")

    max_chars_per_line = st.number_input(
        "Max characters per line",
        min_value=20,
        max_value=100,
        value=42,
    )

    max_lines = st.number_input(
        "Max lines per subtitle",
        min_value=1,
        max_value=4,
        value=2,
    )

    min_duration = st.number_input(
        "Min duration, seconds",
        min_value=0.1,
        max_value=5.0,
        value=1.0,
        step=0.1,
    )

    max_duration = st.number_input(
        "Max duration, seconds",
        min_value=1.0,
        max_value=15.0,
        value=7.0,
        step=0.5,
    )

    max_cps = st.number_input(
        "Max CPS",
        min_value=5.0,
        max_value=40.0,
        value=20.0,
        step=1.0,
    )

    st.header("Glossary")

    glossary_file = st.file_uploader(
        "Upload glossary CSV",
        type=["csv"],
        help="CSV columns: correct, wrong, note",
    )
    
    with st.expander("Glossary CSV format"):
        st.markdown("Required columns: `correct`, `wrong`, `note`")

        st.markdown(
            """
            Example:

            `Yukio` → `Yuki`  
            `Erdé` → `Erde`
            """
        )

        st.caption("The app searches for the wrong term and suggests the correct one.")
        
uploaded_file = st.file_uploader("Upload an SRT file", type=["srt"])

if uploaded_file is None:
    st.info("Upload an .srt file to start checking subtitles.")
else:
    content = uploaded_file.read().decode("utf-8", errors="replace")
    subtitles = parse_srt(content)

    if not subtitles:
        st.error("No valid subtitles found. Please check the file format.")
    else:
        glossary_terms = load_glossary(glossary_file)

        issues = run_checks(
            subtitles,
            max_chars_per_line=max_chars_per_line,
            max_lines=max_lines,
            min_duration=min_duration,
            max_duration=max_duration,
            max_cps=max_cps,
            glossary_terms=glossary_terms,
        )

        subtitles_df = pd.DataFrame(
            [
                {
                    "number": subtitle.number,
                    "start": subtitle.start,
                    "end": subtitle.end,
                    "duration_seconds": round(subtitle.duration_seconds, 2),
                    "text": subtitle.text,
                }
                for subtitle in subtitles
            ]
        )

        issues_df = pd.DataFrame(issues)

        st.subheader("Summary")

        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Subtitles", len(subtitles))
        col2.metric("Issues found", len(issues))

        if issues:
            error_count = sum(issue["severity"] == "Error" for issue in issues)
            glossary_count = sum(
                issue["issue_type"] == "Glossary inconsistency"
                for issue in issues
            )
        else:
            error_count = 0
            glossary_count = 0

        col3.metric("Errors", error_count)
        col4.metric("Glossary issues", glossary_count)

        st.subheader("Issues")

        if issues_df.empty:
            st.success("No issues found. Nice and clean!")
        else:
            severity_filter = st.selectbox(
                "Filter by severity",
                ["All", "Error", "Warning"],
            )

            if severity_filter == "All":
                filtered_issues_df = issues_df
            else:
                filtered_issues_df = issues_df[
                    issues_df["severity"] == severity_filter
                ]

            st.dataframe(filtered_issues_df, use_container_width=True)

            csv = filtered_issues_df.to_csv(index=False).encode("utf-8-sig")

            st.download_button(
                "Download QA report as CSV",
                data=csv,
                file_name="subcheck_qa_report.csv",
                mime="text/csv",
            )

        with st.expander("Parsed subtitles"):
            st.dataframe(subtitles_df, use_container_width=True)
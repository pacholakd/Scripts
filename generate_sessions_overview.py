import os
import re
import html
from datetime import datetime

def parse_session_datetime(session_name):
    """Parse session folder string (e.g. 30-04-2025_2019) to datetime, date, and time string."""
    m = re.match(r"(\d{2})-(\d{2})-(\d{4})_(\d+)", session_name)
    if m:
        day, month, year, hm = m.groups()
        try:
            # Support both 4-digit and 3-digit codes (e.g. 2019, 222)
            if len(hm) == 4:
                hour = int(hm[:-2])
                minute = int(hm[-2:])
            elif len(hm) == 3:
                hour = int(hm[0])
                minute = int(hm[1:])
            else:
                hour, minute = 0, 0
            dt = datetime(int(year), int(month), int(day), hour, minute)
            return dt, dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
        except Exception:
            pass
    return datetime.min, "", ""

def parse_session_summary(summary_path):
    """
    Extract stats from a gauntlet_summary.txt.
    Returns dict with tests_run, tests_passed, tests_failed, platform, configuration, any_failed, session_duration.
    """
    stats = {
        "tests_run": 0,
        "tests_passed": 0,
        "tests_failed": 0,
        "platform": "",
        "configuration": "",
        "any_failed": False,
        "session_duration": "",
    }
    try:
        with open(summary_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as ex:
        print(f"ERROR: Cannot read {summary_path}: {ex}")
        return stats

    for line in lines:
        # Platform/Configuration extraction (grab first match)
        mctx = re.match(r"^\s*\*\s*Main Context:\s*([A-Za-z0-9_]+)\s+([A-Za-z0-9_]+)", line)
        if not stats["platform"] and mctx:
            stats["platform"], stats["configuration"] = mctx.group(1), mctx.group(2)

        # Test result extraction
        if "result=" in line and "Duration=" in line:
            result_match = re.search(r"result=(\w+)", line)
            if result_match:
                stats["tests_run"] += 1
                result = result_match.group(1).lower()
                if result == "passed":
                    stats["tests_passed"] += 1
                elif result == "failed":
                    stats["tests_failed"] += 1
                    stats["any_failed"] = True

    # Session duration extraction (last "AutomationTool executed for" line)
    for line in reversed(lines):
        m = re.search(r'AutomationTool executed for\s+(.+)', line)
        if m:
            stats["session_duration"] = m.group(1)
            break
    return stats

def local_file_link(path, text):
    """Generate a file:/// hyperlink for local use."""
    abs_path = os.path.abspath(path)
    url = 'file:///' + abs_path.replace("\\", "/")
    return f'<a href="{url}" target="_blank">{html.escape(text)}</a>'

def main():
    # Logs directory (relative to this script)
    base_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Logs'))

    # Gather valid session directories
    all_sessions = [
        f for f in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, f))
    ]
    # Sort by parsed datetime, newest first
    session_dirs = sorted(
        all_sessions,
        key=lambda name: parse_session_datetime(name)[0],
        reverse=True
    )

    # Parse sessions
    sessions = []
    for session in session_dirs:
        summary_path = os.path.join(base_dir, session, 'gauntlet_summary.txt')
        if os.path.isfile(summary_path):
            dt_obj, date_str, time_str = parse_session_datetime(session)
            if not date_str:  # skip malformed session names
                print(f"Skipping session '{session}' (unrecognized name format)")
                continue
            sessions.append({
                "name": session,
                "date": date_str,
                "time": time_str,
                "summary_path": summary_path,
                "report_path": os.path.join(base_dir, session, "gauntlet_report.html"),
                "full_log_path": os.path.join(base_dir, session, "gauntlet.txt"),
            })
    sessions = sessions[:20]

    overviews = []
    for ses in sessions:
        stats = parse_session_summary(ses["summary_path"])
        ses["tests_run"] = stats["tests_run"]
        ses["tests_passed"] = stats["tests_passed"]
        ses["tests_failed"] = stats["tests_failed"]
        ses["session_duration"] = stats.get("session_duration", "")
        ses["platform"] = stats.get("platform", "")
        ses["configuration"] = stats.get("configuration", "")
        ses["any_failed"] = stats.get("any_failed", False)
        overviews.append(ses)

    # Build HTML table
    html_rows = ""
    for ses in overviews:
        if os.path.isfile(ses["report_path"]):
            session_link = local_file_link(ses["report_path"], ses["name"])
        else:
            session_link = html.escape(ses["name"])

        # Combine Summary/Full Log in single line separated by |
        links = []
        if os.path.isfile(ses["summary_path"]):
            links.append(local_file_link(ses["summary_path"], "Summary"))
        if os.path.isfile(ses["full_log_path"]):
            links.append(local_file_link(ses["full_log_path"], "Full Log"))
        logs_cell = " | ".join(links)

        # Row coloring: fail if any test failed in this session
        trclass = "fail" if ses.get("any_failed") else "pass"

        html_rows += (
            f'<tr class="{trclass}">'
            f'<td>{session_link}</td>'
            f'<td>{ses["date"]}</td>'
            f'<td>{ses["time"]}</td>'
            f'<td>{html.escape(ses["platform"])}</td>'
            f'<td>{html.escape(ses["configuration"])}</td>'
            f'<td>{ses["tests_run"]}</td>'
            f'<td>{ses["tests_passed"]}</td>'
            f'<td>{ses["tests_failed"]}</td>'
            f'<td>{html.escape(ses["session_duration"])}</td>'
            f'<td>{logs_cell}</td>'
            f"</tr>\n"
        )

    page = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Gauntlet Sessions Overview</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2em; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 0.5em; text-align: left; }}
    th {{ background: #eee; }}
    .fail {{ background: #fcc; }}
    .pass {{ background: #cfc; }}
  </style>
</head>
<body>
<h1>Gauntlet Sessions Overview (Last 20)</h1>
<table>
<tr>
  <th>Session</th>
  <th>Date</th>
  <th>Time</th>
  <th>Platform</th>
  <th>Configuration</th>
  <th>Tests Run</th>
  <th>Passed</th>
  <th>Failed</th>
  <th>Session Time</th>
  <th>Logs</th>
</tr>
{html_rows}
</table>
</body>
</html>
"""
    outpath = os.path.join(base_dir, "gauntlet_sessions_overview.html")
    with open(outpath, "w", encoding="utf-8") as out:
        out.write(page)
    print(f"Wrote {outpath}")

if __name__ == "__main__":
    main()
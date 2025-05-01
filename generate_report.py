import os
import sys
import html
import re
import glob

def usage():
    print("Usage: generate_report.py <summary_file> <full_log> <output_html>")
    sys.exit(1)

if len(sys.argv) < 4:
    usage()

summary_file = sys.argv[1]
full_log = sys.argv[2]
output_html = sys.argv[3]

session_id = os.path.basename(os.path.dirname(os.path.abspath(summary_file)))
project_name = "DPR"

def parse_durations(filename):
    """
    Parse test summary lines for waited/duration values.
    Returns: dict mapping test_name -> (waited, duration)
    """
    timings = {}
    try:
        with open(filename, encoding="utf-8", errors="replace") as f:
            for line in f:
                if "result=" in line and "Waited=" in line and "Duration=" in line:
                    line_stripped = line.lstrip(" *\t")
                    test_name = line_stripped.split(" ", 1)[0].strip()
                    waited = re.search(r"Waited=([\d:]+)", line)
                    duration = re.search(r"Duration=([\d:]+)", line)
                    if test_name:
                        timings[test_name] = (
                            waited.group(1) if waited else "",
                            duration.group(1) if duration else ""
                        )
    except Exception as ex:
        print(f"[Error] Unable to parse durations from {filename}: {ex}", file=sys.stderr)
    return timings

def parse_tests(filename, timing_dict):
    """Parse summary, build a dict for each test (includes timing if found)."""
    tests = []
    try:
        with open(filename, encoding='utf-8', errors='replace') as f:
            test = None
            for line in f:
                if line.startswith(" # Test Summary:"):
                    if test:
                        test['waited'], test['duration'] = timing_dict.get(test['name'], ("", ""))
                        tests.append(test)
                    test = {
                        "name": line.split(":", 1)[1].strip(),
                        "result": "",
                        "warnings": "",
                        "errors": "",
                        "platform": "",
                        "configuration": "",
                        "waited": "",
                        "duration": ""
                    }
                elif test is not None:
                    m = re.match(r"^\s*\*\s*Log Warnings:\s*(\d+)", line)
                    if m:
                        test["warnings"] = m.group(1)
                    m = re.match(r"^\s*\*\s*Log Errors:\s*(\d+)", line)
                    if m:
                        test["errors"] = m.group(1)
                    m = re.match(r"^\s*\*\s*Result:\s*(\w+)", line)
                    if m:
                        test["result"] = m.group(1)
                    m = re.match(r"^\s*\*\s*Main Context:\s*([A-Za-z0-9_]+)\s+([A-Za-z0-9_]+)", line)
                    if m:
                        test["platform"] = m.group(1)
                        test["configuration"] = m.group(2)

            if test:
                test['waited'], test['duration'] = timing_dict.get(test['name'], ("", ""))
                tests.append(test)
    except Exception as ex:
        print(f"[Error] Unable to parse tests from {filename}: {ex}", file=sys.stderr)
    return tests

def local_file_link(path, text):
    abs_path = os.path.abspath(path)
    url = 'file:///' + abs_path.replace("\\", "/")
    return f'<a href="{url}" target="_blank">{html.escape(text)}</a>'

def find_log_for_test(test_name, session_dir):
    """Find one .log file for the test in the session directory."""
    matches = glob.glob(os.path.join(session_dir, test_name + '*'))
    for test_dir in matches:
        for root, dirs, files in os.walk(test_dir):
            for file in files:
                if file.lower().endswith('.log'):
                    return os.path.join(root, file)
    return None

def find_perf_result_lines(full_log_path):
    """
    Returns a list of (avgfps, logline) for DPR_PERF_RESULT log lines.
    """
    perf_pattern = re.compile(
        r"\*\*\*DPR_PERF_RESULT\*\*\*.*?,\s*AvgFPS:\s*([0-9]+\.[0-9]+)",
        re.IGNORECASE,
    )
    results = []
    try:
        with open(full_log_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = perf_pattern.search(line)
                if m:
                    avgfps = float(m.group(1))
                    results.append((avgfps, line.strip()))
    except Exception:
        pass
    return results

def get_perf_result_for_test(test_name, perf_lines_seen):
    """
    For the given test, pop and return the first available matching perf result (or None).
    If running only one perf test per session, this always works.
    For multiple perf tests in one session, they will be matched in order.
    """
    if "performance" not in test_name.lower():
        return None
    if perf_lines_seen:
        return perf_lines_seen.pop(0)
    return None

# Session directory for searching test logs etc.
session_dir = os.path.dirname(os.path.abspath(output_html))

timing_dict = parse_durations(summary_file)
tests = parse_tests(summary_file, timing_dict)
tests_run = len(tests)
tests_passed = sum(1 for t in tests if t["result"].lower() == "passed")
tests_failed = tests_run - tests_passed

# If you have multiple perf tests per session, this matching works fine
perf_results = find_perf_result_lines(full_log)

# How many visible columns in your main table?
MAIN_TABLE_COLS = 8

rows = ""
for t in tests:
    n = t.get('name', "")

    result = html.escape(t.get('result', ""))
    warnings = html.escape(t.get('warnings', ""))
    errors = html.escape(t.get('errors', ""))
    platform = html.escape(t.get('platform', ""))
    configuration = html.escape(t.get('configuration', ""))
    waited = html.escape(t.get('waited', ""))
    duration = html.escape(t.get('duration', ""))

    log_path = find_log_for_test(n, session_dir)
    if log_path:
        test_name_link = local_file_link(log_path, html.escape(n))
    else:
        test_name_link = html.escape(n)

    tr_class = "pass" if result.lower() == "passed" else "fail"
    rows += (
        f'<tr class="{tr_class}">'
        f"<td>{test_name_link}</td>"
        f"<td>{result}</td>"
        f"<td>{warnings}</td>"
        f"<td>{errors}</td>"
        f"<td>{platform}</td>"
        f"<td>{configuration}</td>"
        f"<td>{waited}</td>"
        f"<td>{duration}</td>"
        f"</tr>\n"
    )

    # Insert blue perf stat row for each performance test, matched sequentially
    if "performance" in n.lower():
        perf_stat = get_perf_result_for_test(n, perf_results)
        if perf_stat:
            avgfps, line = perf_stat
            stat_html = html.escape(line)
            rows += (
                f'<tr class="perfstat"><td colspan="{MAIN_TABLE_COLS}" style="background:#ccf;color:#003;padding-left:2em">'
                f'Performance Results: <code>{stat_html}</code></td></tr>\n'
            )
        else:
            rows += (
                f'<tr class="perfstat"><td colspan="{MAIN_TABLE_COLS}" style="background:#ccf;color:#003;padding-left:2em">'
                f'Performance Results: <code>No performance result found in log!</code></td></tr>\n'
            )

def safely_link_or_plain(filepath, label):
    if filepath and os.path.isfile(filepath):
        return local_file_link(filepath, label)
    return html.escape(label)

summary_link = safely_link_or_plain(summary_file, "Summary Report")
full_link = safely_link_or_plain(full_log, "Full Log")
details_link = safely_link_or_plain(full_log, "Show details")

CSS = """
body { font-family: Arial, sans-serif; margin: 2em; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ccc; padding: 0.5em; text-align: left; }
th { background: #eee; }
.pass { background: #cfc; }
.fail { background: #fcc; }
.perfstat { background: #ccf !important; color: #003; font-weight: normal; }
code { font-size: 1em; }
"""

page = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Gauntlet Automation Test Report</title>
  <style>{CSS}</style>
</head>
<body>
<h1>Gauntlet Automation Test Report</h1>
<table>
<tr><th>Session ID</th><td>{html.escape(session_id)}</td></tr>
<tr><th>Project</th><td>{html.escape(project_name)}</td></tr>
<tr><th>Tests Run</th><td>{tests_run}</td></tr>
<tr><th>Tests Passed</th><td>{tests_passed}</td></tr>
<tr><th>Tests Failed</th><td>{tests_failed}</td></tr>
<tr><th>Session Log</th>
    <td>
        {summary_link} |
        {full_link}
    </td>
</tr>
</table>
<h2>Test Details</h2>
<table>
<tr>
  <th>Test Name</th>
  <th>Result</th>
  <th>Warnings</th>
  <th>Errors</th>
  <th>Platform</th>
  <th>Configuration</th>
  <th>Waited</th>
  <th>Duration</th>
</tr>
{rows}
</table>
<br>
{details_link}
</body>
</html>
"""

with open(output_html, "w", encoding="utf-8") as out:
    out.write(page)

print(f"Generated HTML report: {output_html}", flush=True)
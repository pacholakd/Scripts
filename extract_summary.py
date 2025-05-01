import sys
import re

if len(sys.argv) != 3:
    print("Usage: extract_summary.py input_log output_summary")
    sys.exit(1)

input_log = sys.argv[1]
output_summary = sys.argv[2]

start_pattern = re.compile(r'^ # Test Summary')
end_pattern = re.compile(r'^AutomationTool executed for.*')

found_start = False
with open(input_log, encoding='utf-8', errors='replace') as infile, open(output_summary, 'w', encoding='utf-8') as outfile:
    for line in infile:
        if not found_start:
            if start_pattern.match(line):
                found_start = True
                outfile.write(line)
        else:
            outfile.write(line)
            if end_pattern.match(line):
                break
import re

input_file = '/Users/zhiqiang/Code/roanhe-ts.github.io/pre_post/DebugStack/profile.txt'
output_file = '/Users/zhiqiang/Code/roanhe-ts.github.io/pre_post/DebugStack/profile_filtered.txt'

# Define the patterns to match
patterns = [
    re.compile(r'^\s*Instance'),
    re.compile(r'^\s*VDataStreamSender'),
    re.compile(r'^\s*VNewOlapScanNode'),
    re.compile(r'^\s*VEXCHANGE_NODE'),
    re.compile(r'^\s*VHASH_JOIN_NODE'),
    re.compile(r'^\s*VSORT_NODE'),
    # Add more patterns here if needed
]

with open(input_file, 'r') as infile, open(output_file, 'w') as outfile:
    for line in infile:
        if any(pattern.match(line) for pattern in patterns):
            outfile.write(line)

print(f'Filtered content saved to {output_file}')
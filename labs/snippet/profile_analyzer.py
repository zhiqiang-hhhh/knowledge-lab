# This is a python script
# It reads profile test from file, and then analyze the profile test
import re
import logging

def analyze_text(file_path):
    logging.info(f"开始分析文件: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    logging.info(f"读取文件，共 {len(lines)} 行")
    results = []
    vnewolap_pattern = re.compile(r'VNewOlapScanNode\(cyb_dwd_sales_week_global_v\)')
    rowsreturned_pattern = re.compile(r'-  RowsReturned:\s+(\d+)')

    for i, line in enumerate(lines):
        if vnewolap_pattern.search(line):
            logging.debug(f"找到匹配的 VNewOlapScanNode 行: {line.strip()} (行号: {i+1})")
            for j, line in enumerate(lines[i:]):
                rowsreturned_match = rowsreturned_pattern.search(lines[i + 1])
                if rowsreturned_match:
                    logging.debug(f"找到对应的 RowsReturned 行: {lines[i + 1].strip()} (行号: {i+2}), 值: {rows_returned}")
                    rows_returned = int(rowsreturned_match.group(1))
                    if rows_returned != 0:
                        results.append(rowsreturned_match)
                        # results.append((line.strip(), lines[i + 1].strip()))
                        logging.info(f"记录 RowsReturned 不为零的行: {line.strip()} 和 {lines[i + 1].strip()}")
                    break

    logging.info(f"分析完成，共找到 {len(results)} 条 RowsReturned 不为零的记录")
    return results

# 使用示例
file_path = 'path/to/your/textfile.txt'
results = analyze_text(file_path)

for result in results:
    print(result)

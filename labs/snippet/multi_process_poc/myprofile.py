# api_client.py
import re
import time
import requests
from requests.auth import HTTPBasicAuth
import sqlite3
import logging
import database

def fetch_query_info(host, port, username, password):
    url = f"http://{host}:{port}/rest/v2/manager/query/query_info"  # Replace with the actual URL
    try:
        response = requests.get(url, auth=HTTPBasicAuth(username, password))
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)
        query_info = response.json()  # Parse the JSON response
        return query_info
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        print(f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        print(f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        print(f"An error occurred: {req_err}")
    return None

def get_profile_content(host, port, username, password, profile_id):
    url = f"http://{host}:{port}/rest/v2/manager/query/profile/text/{profile_id}"
    try:
        # time.sleep()
        response = requests.get(url, auth=HTTPBasicAuth(username, password))
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx and 5xx)
        # return response.text()
        profile_content = response.json()  # Parse the JSON response
        return profile_content
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        print(f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        print(f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        print(f"An error occurred: {req_err}")
    return None

def store_data_in_doris(data):
    # Connect to an in-memory SQLite database
    conn = database.get_analyze_cluster_conn()
    cursor = conn.cursor()
    
    # Extract column names and rows
    rows = data['rows']
    logging.info(f"Query info sample {rows[0]}")
    idx = 1
    for row in rows:
        row = row[:-2]  # Remove the last two element
        row = [idx] + row
        placesholders = ', '.join(['%s'] * (len(row)))
        dml = f"""INSERT INTO poc.query_info(idx, QueryID, FE, Type, Begin, End, Total, Status, User, Catalog, DB, Sql) VALUES ({placesholders});"""
        # dml = f"""INSERT INTO poc.query_info(idx, QueryID, FE, Type, Begin, End, Total, Status, User, DB, Sql) VALUES ({placesholders});"""
        if idx == 1:
            logging.debug(f"DML:\n {dml}")
            logging.debug("Row: %s", row)
        cursor.execute(f"{dml}", row)
        idx+=1
    conn.commit()
    return conn

def get_profile_list_by_range(username, password, begin_uuid, end_uuid, database_name):
    query_info = fetch_query_info("127.0.0.1" , 5937, username, password)
    # query_info = fetch_query_info("62.234.39.208" , 8030, username, password)
    if query_info and 'data' not in query_info:
        # Throw an exception
        raise Exception("Data not found in query_info")
        
    data = query_info['data']
    conn = store_data_in_doris(data)
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT QueryID, Begin, Sql FROM poc.query_info where Sql like '%{begin_uuid}%' or Sql like '%{end_uuid}%' order by End")
    res = cursor.fetchall()
    begin_query_id, begin_time = res[0][0], res[0][1]
    end_query_id, end_time = res[1][0], res[1][1]
    logging.info(f"begin_query_uuid\t{begin_query_id}\tbegin_time:\t{begin_time}")
    logging.info(f"end_query_uuid  \t{end_query_id}\tend_time:    \t{end_time}")
    res = database.pretty_print_results(
        f"SELECT QueryID, Begin, End, DB FROM poc.query_info " + 
        f"where Begin >= '{begin_time}' AND End <= '{end_time}' AND (DB = '{database_name}') order by Begin,End")
    logging.info(f"Profile list fetched successfully. Count {len(res)}")
    final_res = []
    for row in res:
        final_res.append(row[0])
    return final_res

def parse_to_m_bytes(bytes_str):
    pattern = re.compile(r'(\d+(\.\d+)?)\s*(\w+)')
    match = pattern.fullmatch(bytes_str)
    if not match:
        raise ValueError(f"Invalid bytes string {bytes_str}")

    value = float(match.group(1))
    unit = match.group(3).upper()

    # 根据单位转换为MB
    if unit == 'B':
        return value / (1024 * 1024)
    elif unit == 'KB':
        return value / 1024
    elif unit == 'MB':
        return value
    elif unit == 'GB':
        return value * 1024
    elif unit == 'TB':
        return value * 1024 * 1024
    else:
        raise ValueError(f"Invalid unit {unit}")

def parse_to_milliseconds(duration_str):
    pattern = re.compile(r'(?:(\d+(?:\.\d+)?)hour)?(?:(\d+(?:\.\d+)?)min)?(?:(\d+(?:\.\d+)?)sec)?(?:(\d+(?:\.\d+)?)ms)?(?:(\d+(?:\.\d+)?)us)?')
    match = pattern.fullmatch(duration_str)
    if not match:
        raise ValueError(f"Invalid duration string {duration_str}")

    hours = float(match.group(1)) if match.group(1) else 0
    minutes = float(match.group(2)) if match.group(2) else 0
    seconds = float(match.group(3)) if match.group(3) else 0
    milliseconds = float(match.group(4)) if match.group(4) else 0
    microseconds = float(match.group(5)) if match.group(5) else 0

    total_milliseconds = (hours * 3600 * 1000 +
                          minutes * 60 * 1000 +
                          seconds * 1000 +
                          milliseconds +
                          microseconds / 1000)
    
    return total_milliseconds

def ayalyze_profile(profile_content):
    execution_profile_pattern = re.compile(r'(?=.*Execution)(?=.*Profile)')
    scan_operator_pattern = re.compile(r'OLAP_SCAN_OPERATOR \(id=') 
    vscanner_pattern = re.compile(r'VScanner:')
    rowsread_pattern = re.compile(r'- RowsRead:.*\d')
    # 定义正则表达式以匹配以 - ScanNodeDeserializationBlockTime: 和数字开头的行
    deser_pattern = re.compile(r'- ScanNodeDeserializationBlockTime: \d+(\.\d+)?')
    ser_pattern = re.compile(r'- ScannerSerializationBlockTime: \d+(\.\d+)?')
    col_count_pattern = re.compile(r'- ColumnCount: \d+(\.\d+)?')
    sered_binary_bytes_pattern = re.compile(r'- SerializedBinarySize: \d+(\.\d+)?')
    block_size_pattern = re.compile(r'- BlockSize: \d+(\.\d+)?')
    total_pattern = re.compile(r'- Total: \d+(\.\d+)?')  
    
    lines = profile_content.split('\n')
    total_time_ms = 0
    query_id = ''
    sql = ''
    scan_operator_offset = []
    scanner_offset = []

    for i, line in enumerate(lines):
        if line.strip().startswith("- Profile ID"):
            query_id = line.split(' ')[-1]
        if line.strip().startswith("- Sql Statement"):
            sql = line.split('Statement: ')[-1]
        if total_pattern.search(line):
            total_time_ms = parse_to_milliseconds(line.split(' ')[-1])
        if execution_profile_pattern.search(line):
            for j, line in enumerate(lines[i:]):
                if scan_operator_pattern.search(line.strip()):
                    scan_operator_offset.append(i+j)
                    # logging.debug(f"Scan operator found {line}")
                if vscanner_pattern.search(line):
                    scanner_offset.append(i+j)
            break

    if len(scan_operator_offset) != len(scanner_offset):
        raise ValueError("Scan operator and scanner count mismatch")

    logging.info("Processing profile %s", query_id)
    # logging.debug("Scan operator offset %s", scan_operator_offset)
    total = len(scan_operator_offset)
    # 确保不越界
    scan_operator_offset.append(len(lines))
    
    analyze_result = []
    for i in range(total):
        segment_b = scan_operator_offset[i]
        segment_e = scan_operator_offset[i+1]

        rows_read = 0
        col_count = 0
        block_mb = 0
        serialized_mb = 0
        ser_time = 0
        deser_time = 0

        valid = True
        for i, line in enumerate(lines[segment_b:segment_e]):
            match_rowsread = rowsread_pattern.search(line)
            if match_rowsread:
                if '(' in line:
                    rows_read = int(line.split('(')[1].split(')')[0])
                else:   
                    rows_read = int(line.split(':')[1])
                if (rows_read < 100):
                    valid = False
                    break
                continue
            match_deser = deser_pattern.search(line)
            if match_deser:
                deser_time = parse_to_milliseconds(line.split(' ')[-1])
                continue
            match_ser = ser_pattern.search(line)
            if match_ser:
                ser_time = parse_to_milliseconds(line.split(' ')[-1])
                continue
            match_col_count = col_count_pattern.search(line)
            if match_col_count:
                col_count = int(line.split(' ')[-1])
                continue
            match_sered_binary = sered_binary_bytes_pattern.search(line)
            if match_sered_binary:
                str = line.split(' ')[-2] + line.split(' ')[-1]
                try:
                    serialized_mb = parse_to_m_bytes(str)
                    continue
                except ValueError as e:
                    valid = False
                    break
            match_block_size = block_size_pattern.search(line)
            if match_block_size:
                str = line.split(' ')[-2] + line.split(' ')[-1]
                try:
                    block_mb = parse_to_m_bytes(str)
                    continue
                except ValueError as e:
                    valid = False
                    break
        
        analyze_result.append([query_id, total_time_ms, sql, rows_read, col_count, block_mb, serialized_mb, ser_time, deser_time])        

    return analyze_result

def store_ayalyze_result(query_idx, dbname, analyze_result):
    logging.debug(f"QueryIdx {query_idx} ScanOperator in total {len(analyze_result)},")
    conn = database.get_analyze_cluster_conn()
    cursor = conn.cursor()
    
    cursor.execute(f"USE {database.AYALYZE_DATABASE_NAME}")
    cursor.execute(
        f"CREATE TABLE {dbname}_{query_idx} (" +
         "db VARCHAR, query_idx VARCHAR, query_id VARCHAR, total_ms INT, sql_content TEXT, rows_read INT, " +
         "column_count INT, block_mb INT, serialized_mb INT, serialization_ms DOUBLE, deserialization_ms DOUBLE)" +
         " duplicate key (db, query_idx, query_id) distributed by hash(total_ms) buckets 3 " +
         " properties(\"replication_num\"=\"1\")")
    
    for row in analyze_result:
        row = [dbname, query_idx] + row
        placeholders = ', '.join(["%s"] * len(row))
        cursor.execute(f"INSERT INTO {dbname}_{query_idx} VALUES ({placeholders})", row)
        cursor.execute("COMMIT")

    cursor.execute(
        "INSERT INTO res_table " +
        "SELECT db, query_idx, query_id, total_ms, count(*) as scan_node_cnt, " + 
        "round(min(serialization_ms + deserialization_ms), 2) as min_ser_ms, " +
        "round(max(serialization_ms + deserialization_ms), 2) as max_ser_ms, " +
        "PERCENTILE(serialization_ms + deserialization_ms, 0.5) as p50_ser_ms, " +
        "round(min(rows_read), 2) as min_rows_read, " +
        "round(max(rows_read), 2) as max_rows_read, " +
        "PERCENTILE(rows_read, 0.5) as p50_block_mb, " +
        "round(sum(rows_read), 2) as sum_rows_read, " +
        "round(min(block_mb), 2) as min_block_mb, " +
        "round(max(block_mb), 2) as max_block_mb, " +
        "PERCENTILE(block_mb, 0.5) as p50_block_mb, " +
        "round(sum(block_mb), 2) as sum_block_mb " +
        f" FROM {dbname}_{query_idx} GROUP BY db, query_idx, query_id, total_ms;")
    cursor.execute("COMMIT")

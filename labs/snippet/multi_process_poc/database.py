import mysql.connector
from tabulate import tabulate

QUERY_INFO_COLUMNS = [
    'idx BIGINT', 'QueryID TEXT', 'FE TEXT', 'Type TEXT', 'Begin DATETIME',
    'End DATETIME', 'Total TEXT', 'Status TEXT', 'User TEXT', 'Catalog TEXT', 'DB TEXT', 'Sql TEXT']

# QUERY_INFO_COLUMNS = [
#     'idx BIGINT', 'QueryID TEXT', 'FE TEXT', 'Type TEXT', 'Begin DATETIME', 
#     'End DATETIME', 'Total TEXT', 'Status TEXT', 'User TEXT', 'DB TEXT', 'Sql TEXT']

AYALYZE_DATABASE_NAME = "poc"

FINAL_RES_TABLE_COLUMNS = [
    'query_idx VARCHAR', 'poc_total_ms DOUBLE', 'master_total_ms DOUBLE', 'diff DOUBLE',
    'rollback DOUBLE', 'sum_read_rows DOUBLE', 'sum_read_block_mb DOUBLE', 'scan_node_cnt INT',
    'avg_rows_read DOUBLE', 'avg_block_mb DOUBLE', 'avg_ser_ms DOUBLE', 'ser/poc_total_ms'
]

RES_TABLE_COLUMNS = [
    'db VARCHAR', 'query_idx VARCHAR', 'query_id VARCHAR', 'total_ms DOUBLE', 'scan_node_cnt INT',
    'min_ser_ms DOUBLE', 'max_ser_ms DOUBLE', 'p50_ser_ms DOUBLE',
    'min_rows_read DOUBLE', 'max_rows_read DOUBLE', 'p50_rows_read DOUBLE', 'sum_rows_read DOUBLE',
    'min_block_mb DOUBLE', 'max_block_mb DOUBLE', 'p50_block_mb DOUBLE', 'sum_block_mb DOUBLE',
]

def get_analyze_cluster_conn() :
    conn = mysql.connector.connect(
        user="root", password="", host='127.0.0.1', port=6937)
    return conn

# def get_poc_cluster_conn():
#     # return get_analyze_cluster_conn()
#     conn = mysql.connector.connect(
#         user="root", password="", host='62.234.39.208', port=9030)
#     return conn

def init_base_database():
    conn = get_analyze_cluster_conn()
    cursor = conn.cursor()
    # cursor.execute("DROP DATABASE IF EXISTS base")
    cursor.execute("CREATE DATABASE IF NOT EXISTS base")
    cursor.execute("USE base")
    # Create a table with the extracted column names
    cursor.execute("DROP TABLE IF EXISTS query_info")
    cursor.execute(f"CREATE TABLE IF NOT EXISTS query_info ({', '.join(QUERY_INFO_COLUMNS)}) " +
                   "duplicate key (idx)" +
                   " distributed by hash(idx) buckets 3 " +
                   " properties(\"replication_num\" = \"1\");")
    cursor.execute("CREATE TABLE IF NOT EXISTS res_table " +
                   f"({', '.join(RES_TABLE_COLUMNS)}) " +
                   "duplicate key (db, query_idx)" +
                   " distributed by hash(query_idx) buckets 3 " +
                   " properties(\"replication_num\" = \"1\");") 

def init_poc_database():
    conn = get_analyze_cluster_conn()
    cursor = conn.cursor()
    # cursor.execute("DROP DATABASE IF EXISTS poc")
    cursor.execute("CREATE DATABASE IF NOT EXISTS poc")
    cursor.execute("USE poc")
    
    cursor.execute("DROP TABLE IF EXISTS query_info")
    cursor.execute("DROP TABLE IF EXISTS query_base")
    # Create a table with the extracted column names
    cursor.execute(f"CREATE TABLE query_info ({', '.join(QUERY_INFO_COLUMNS)}) " +
                   "duplicate key (idx)" +
                   " distributed by hash(idx) buckets 3 " +
                   " properties(\"replication_num\" = \"1\");")
    
    cursor.execute("CREATE TABLE query_base (idx INT, sql TEXT, db TEXT) DUPLICATE KEY (idx) PROPERTIES (\"replication_num\"=\"1\")")

    cursor.execute("CREATE TABLE IF NOT EXISTS res_table " +
                   f"({', '.join(RES_TABLE_COLUMNS)}) " +
                   "duplicate key (db,query_idx)" +
                   " distributed by hash(query_idx) buckets 3 " +
                   " properties(\"replication_num\" = \"1\");")
    
    cursor.fetchall()
    cursor.close()
    conn.commit()

def pretty_print_results(query):
    conn = get_analyze_cluster_conn()
    cursor = conn.cursor()
    cursor.execute(query)
    result = cursor.fetchall()
    conn.close()
    headers = [description[0] for description in cursor.description]
    print(tabulate(result, headers=headers, tablefmt='pretty'))
    return result


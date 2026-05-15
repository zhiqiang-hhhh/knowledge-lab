#!/usr/bin/env python

import datetime
import random
import mysql.connector

doris_conn = mysql.connector.connect(user="root", password="", host='10.16.10.8', port=6937)
# ch_conn = mysql.connector.connect(user="default", password="", host='10.16.10.8', port=9999)

cursor = doris_conn.cursor()

database_name = "bitmap_perf_test"
cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database_name};")
cursor.execute(f"USE {database_name};")

table_name = "bitmap_perf_test"
# drop_table_query = f"DROP TABLE IF EXISTS {database_name}.{table_name};"
# cursor.execute(drop_table_query)

create_table_query = f"CREATE TABLE IF NOT EXISTS {database_name}.{table_name} (rowid INT, bm bitmap bitmap_union) ENGINE=OLAP AGGREGATE KEY(`rowid`) DISTRIBUTED BY HASH(`rowid`) BUCKETS 1 "
create_table_query += "PROPERTIES(\"replication_allocation\" = \"tag.location.default: 1\");"
print("DDL: ", create_table_query)
cursor.execute(create_table_query)

set_task_number = "set parallel_pipeline_task_num=1;"
cursor.execute(set_task_number)

for parallel_pipeline_task_num in range(10):
    cursor.execute(f"set parallel_pipeline_task_num={parallel_pipeline_task_num};")
    for n in range(100):
        cursor.execute(f"select bitmap_union_count(bm) from bitmap_perf where app_id>=1 and app_id<={n};")

# for n in range(100000000):
#     insert_query = f"INSERT INTO {database_name}.{table_name} VALUES ({n}, to_bitmap({n}));"
#     cursor.execute(insert_query)
# print("Inserted 100 rows, ", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


query = f"SELECT count(*) FROM {database_name}.{table_name};"
cursor.execute(query)
res = cursor.fetchall()
print(res)

cursor.close()

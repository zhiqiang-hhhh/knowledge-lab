#!/usr/bin/env python

import random
import mysql.connector
from prettytable import PrettyTable
from faker import Faker
import logging

def execute_ddl(connection, ddl):
    cursor = connection.cursor()
    cursor.execute(ddl)
    connection.commit()

def get_table_structure(cursor, table_name):
    cursor.execute(f"DESCRIBE {table_name}")
    columns = cursor.fetchall()
    
    table = PrettyTable(['Field', 'Type', 'Null', 'Key', 'Default', 'Extra'])
    for column in columns:
        table.add_row([column[0], column[1], column[2], column[3], column[4], column[5]])
    
    print(table)
    return columns

def generate_random_data(column, faker):
    col_name = column[0]
    col_type = column[1]
    
    if 'INT' in col_type or 'BIGINT' in col_type:
        if col_name == 'year':
            return random.randint(1990, 2027)
        if col_name == 'site_code':
            return random.randint(1001, 2000)
        return random.randint(0, 100000)
    
    elif 'VARCHAR' in col_type or 'TEXT' in col_type:
        if col_name in ['KPI_CODE', 'KPI_ID', 'FLIGHT_DATE', 'sequence_id']:
            return f"""{random.choice(['A', 'B', 'C'])}"""
        if col_name == 'uuid':
            return faker.uuid4()
        else:
            max_nb_chars = int(col_type.split('(')[1][:-1])
            return faker.text(max_nb_chars=max_nb_chars)
    
    elif 'DATE' in col_type:
        return faker.date()
    
    elif 'DATETIME' in col_type:
        return faker.date_time()
    
    elif 'FLOAT' in col_type or 'DOUBLE' in col_type:
        return random.uniform(0, 1000)
    
    elif 'DECIMAL' in col_type:
        precision, scale = map(int, col_type.split('(')[1][:-1].split(','))
        max_value = 10**(precision - scale) - 10**-scale
        return round(random.uniform(0, max_value), scale)
    
    else:
        return None


def insert_random_data(connection, table_name, columns, faker, num_rows=100):
    cursor = connection.cursor()
    batch_size = 100  # 每次插入的行数
    for _ in range(0, num_rows, batch_size):
        batch_data = []
        for _ in range(batch_size):
            row_data = [generate_random_data(col, faker) for col in columns]
            batch_data.append(row_data)
        
        placeholders = ', '.join(['%s'] * len(columns))
        columns_names = ', '.join([col[0] for col in columns])
        sql = f"INSERT INTO {table_name} ({columns_names}) VALUES ({placeholders})"
        cursor.executemany(sql, batch_data)
        
    connection.commit()
    
def generate_ddl(table_name, col_name, col_type):
    columns_def = ", ".join([f"{name} {type}" for name, type in zip(col_name, col_type)])
    ddl = f"""CREATE TABLE IF NOT EXISTS {table_name} ({columns_def}) UNIQUE KEY(`KPI_CODE`)
              distributed by hash({col_name[0]}) properties("replication_num"="1")"""
    return ddl

def get_table_structure_and_insert_random_data(table_name, num_rows=100):
    connection = mysql.connector.connect(
        user="root", password="", host='10.16.10.8', port=6937)
    cursor = connection.cursor()
    faker = Faker()

    try:
        # execute_ddl(connection, "USE demo;")
        columns = get_table_structure(cursor, table_name)
        # Insert random data
        insert_random_data(connection, table_name, columns, faker, num_rows)

        print(f"Successfully inserted random data into {table_name}")
    finally:
        cursor.close()
        connection.close()

def create_table_and_insert_random_data(table_name, col_name, col_type, ddl="", num_rows=100):
    if not ddl:
        ddl = generate_ddl(table_name, col_name, col_type)

    connection = mysql.connector.connect(user="root", password="", host='10.16.10.8', port=6937)
    cursor = connection.cursor()
    faker = Faker()
    try:
        execute_ddl(connection, "USE demo;")
        execute_ddl(connection, f"DROP TABLE IF EXISTS {table_name};")
        # Execute the DDL statement
        execute_ddl(connection, ddl)
        # Get the table structure
        columns = get_table_structure(cursor, table_name)

        # Insert random data
        insert_random_data(connection, table_name, columns, faker, num_rows)

        print(f"Successfully inserted random data into {table_name}")
    finally:
        cursor.close()
        connection.close()

def main():
    table_name = "scanner.account_details_snappy_site_code_v2"
    get_table_structure_and_insert_random_data(table_name, num_rows=12600)

if __name__ == "__main__":
    main()
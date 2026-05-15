import sys
import os
import time
import traceback
import uuid
import myprofile as profile
import logging
import database

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s][%(levelname)s][%(filename)s:%(lineno)d] - %(message)s')


# List of valid suite names
VALID_SUITES = ['clickbench', 'tpch_sf1', 'tpch_sf100', 'tpch_sf1000']

def validate_arguments(args):
    if len(args) != 2:
        logging.error("Invalid number of arguments.")
        raise ValueError("Usage: python multi-process-poc.py [clickbench|tpch_sf1|tpch_sf100|tpch_sf1000]")
    
    suits_name = args[1]
    
    if suits_name not in VALID_SUITES:
        logging.error(f"Invalid suite name: {suits_name}")
        raise ValueError(f"Invalid suite name: {suits_name}. Valid suite names are: {', '.join(VALID_SUITES)}")
    
    logging.info(f"Validated arguments. Suite name: {suits_name}")
    return suits_name

def generate_uuid():
    return str(uuid.uuid4())

def get_queries_path(suits_name, modified=False):
    if (suits_name.startswith('tpch')):
        suits_name = 'tpch'
    sub_dir = 'modified' if modified else 'origin'
    queries_path = os.path.join('sql', suits_name, sub_dir)
    logging.info(f"Queries path: {queries_path}")
    return queries_path

def read_query_file(query_file_path):
    with open(query_file_path, 'r') as file:
        queries = file.read()
    # logging.info(f"Read queries from file: {query_file_path}, content: {queries}")
    return queries

def execute_query(query_text, connection):
    cursor = connection.cursor()
    cursor.execute(query_text)
    cursor.fetchall()
    while cursor.nextset():
        # Fetch all results to avoid 'Unread result found' error
        cursor.fetchall()
    connection.commit()

def main():
    try:
        # database.init_base_database()
        database.init_poc_database()
        suits_name = validate_arguments(sys.argv)
        query_file_dir = get_queries_path(suits_name, modified=False)

        # list all files in the directory
        query_files_list = os.listdir(query_file_dir)
        if "clickbench" not in suits_name: 
            query_files_list = sorted(query_files_list, key=lambda x: int(x[1:-4]))
        logging.info(f"List of files in the directory: {query_files_list}")
        # query_files_list = query_files_list[:2]
        # connection = database.get_poc_cluster_conn()
        connection = database.get_analyze_cluster_conn()
        cursor = connection.cursor()
        cursor.execute("SET enable_profile=true;")
        begin_uuid = generate_uuid()
        end_uuid = generate_uuid()
        logging.info("Begin UUID: %s, end UUID: %s", begin_uuid, end_uuid)
        cursor.execute("USE demo")
        cursor.execute(f"SELECT '{begin_uuid}'")  # Generate a unique identifier
        cursor.fetchall()
        
        cursor.execute(f"USE {suits_name}")
        
        query_idx = 1
        
        for file in query_files_list:
            abs_path = os.path.join(query_file_dir, file)
            logging.info(abs_path)
            query_content = read_query_file(abs_path)
            if suits_name == "clickbench":
                for query in query_content.splitlines():
                    query = query.strip()
                    if query and query.startswith('SELECT') or query.startswith('USE') or query.startswith('SET'):
                        query = query.strip()
                        time.sleep(1)
                        logging.info(f"Executing query {query_idx}:{query}")
                        execute_query(query, connection)
                        conn_inner = database.get_analyze_cluster_conn()
                        cursor_inner = conn_inner.cursor()
                        cursor_inner.execute(f"INSERT INTO poc.query_base VALUES({query_idx}, \"{query}\", '{suits_name}')")
                        conn_inner.commit()
                        cursor.fetchall()
            else:
                time.sleep(1)
                execute_query(query_content, connection)
                conn_inner = database.get_analyze_cluster_conn()
                cursor_inner = conn_inner.cursor()
                cursor_inner.execute(f"INSERT INTO poc.query_base VALUES({query_idx}, \"{query_content}\", \"{suits_name}\")")
                conn_inner.commit()
                cursor.fetchall()
            time.sleep(1)

        cursor.execute(f"USE demo")
        cursor.execute(f"SELECT '{end_uuid}'")  # Generate a unique identifier
        cursor.fetchall()
        # begin_uuid = "6bc5f28e-199e-4eca-86fa-a5b57f1de0f7"
        # end_uuid = "760a4825-e856-434c-8f15-5630cb7aff6b"
        profile_ids = profile.get_profile_list_by_range("root", "", begin_uuid, end_uuid, suits_name)

        query_idx = 1
        for profile_id in profile_ids:
            # profile_content = profile.get_profile_content("127.0.0.1", 5937, "root", "", profile_id)
            profile_content = profile.get_profile_content("62.234.39.208", 8030, "root", "", profile_id)
            res = profile.ayalyze_profile(profile_content['data']['profile'])
            profile.store_ayalyze_result(query_idx, suits_name, res)
            query_idx += 1

        database.pretty_print_results("SELECT * FROM poc.res_table ORDER BY db, cast(query_idx as Int); ")
    except Exception as e:
        logging.error(f"An error occurred: {traceback.format_exc()}")
    finally:
        if 'connection' in locals() and connection.is_connected():
            connection.close()
            logging.info("MySQL connection closed")

if __name__ == '__main__':
    main()

import numpy as np
import mysql.connector
import pandas as pd
import logging
import time
import sys
import os
import requests
import argparse
from requests.auth import HTTPBasicAuth
from faiss.contrib.datasets import DatasetSIFT1M
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 每个段的行数
CHUNK_SIZE = 500000  # 50万行

def create_data_directory():
    """Create a data directory to store CSV files if it doesn't exist"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, 'data')
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        logger.info(f"Created data directory at {data_dir}")
    return data_dir

def save_dataset_chunk_to_tsv(dataset_chunk, table_name, chunk_idx, data_dir):
    """Save a chunk of the dataset to a TSV file without headers"""
    tsv_path = os.path.join(data_dir, f"{table_name}_chunk_{chunk_idx}.tsv")
    
    # Check if the TSV file already exists
    if os.path.exists(tsv_path):
        logger.info(f"TSV chunk file already exists at {tsv_path}, skipping creation")
        return tsv_path
    
    logger.info(f"Saving dataset chunk {chunk_idx} to {tsv_path}")
    
    # Convert embedding lists to strings for TSV storage but keep the square brackets
    dataset_copy = dataset_chunk.copy()
    dataset_copy['embedding'] = dataset_copy['embedding'].apply(lambda x: str(x))
    
    # Write to TSV without headers
    dataset_copy.to_csv(tsv_path, index=False, sep='\t', header=False)
    logger.info(f"Dataset chunk {chunk_idx} saved to {tsv_path} without headers")
    return tsv_path

def save_dataset_to_tsv(dataset, table_name, data_dir):
    """Save the dataset to a TSV file without headers"""
    tsv_path = os.path.join(data_dir, f"{table_name}.tsv")
    
    # Check if the TSV file already exists
    if os.path.exists(tsv_path):
        logger.info(f"TSV file already exists at {tsv_path}, skipping creation")
        return tsv_path
    
    logger.info(f"Saving dataset to {tsv_path}")
    
    # Convert embedding lists to strings for TSV storage but keep the square brackets
    dataset_copy = dataset.copy()
    dataset_copy['embedding'] = dataset_copy['embedding'].apply(lambda x: str(x))
    
    # Write to TSV without headers
    dataset_copy.to_csv(tsv_path, index=False, sep='\t', header=False)
    logger.info(f"Dataset saved to {tsv_path} without headers")
    return tsv_path

def stream_load_to_doris(table_name, tsv_path, host="127.0.0.1", port=5937, db="vector_test"):
    """Load data from TSV file to Doris using Stream Load"""
    logger.info(f"Loading data to table {table_name} using Stream Load from {tsv_path}")
    start_time = time.time()
    
    # Clean file basename to create valid label (remove extension and replace dots with underscores)
    file_basename = os.path.basename(tsv_path)
    clean_basename = os.path.splitext(file_basename)[0].replace('.', '_')
    
    url = f"http://{host}:{port}/api/{db}/{table_name}/_stream_load"
    headers = {
        'Expect': '100-continue',
        'Content-Type': 'text/plain; charset=UTF-8',
        'label': f"load_{table_name}_{int(time.time())}_{clean_basename}",
        'format': 'csv',  # Using csv format with tab separator for TSV files
        'column_separator': '\\t',  # Use escaped tab character for HTTP header
        'columns': 'id,category,embedding',
    }
    
    with open(tsv_path, 'rb') as f:
        tsv_data = f.read()

    try:
        auth = HTTPBasicAuth("root", "")
        session = requests.sessions.Session()
        session.should_strip_auth = lambda old_url, new_url: False  # Don't strip auth
        resp = session.request(
            'PUT', url=url,
            data=tsv_data,
            headers=headers, auth=auth
        )
        
        # Log detailed response
        logger.info(f"Stream load status code: {resp.status_code}")
        logger.info(f"Raw response text: {resp.text}")
        
        # Try to parse JSON response for detailed error information
        try:
            response_json = resp.json()
            logger.info(f"Response JSON: {json.dumps(response_json, indent=2)}")
            
            # Log specific Doris error details
            if 'status' in response_json:
                logger.info(f"Load status: {response_json['status']}")
            if 'msg' in response_json:
                logger.info(f"Message: {response_json['msg']}")
            if 'errorURL' in response_json:
                logger.info(f"Error URL: {response_json['errorURL']}")
            if 'errorMsg' in response_json:
                logger.info(f"Error message: {response_json['errorMsg']}")
                
        except json.JSONDecodeError:
            logger.warning("Could not parse response as JSON")

        elapsed_time = time.time() - start_time
        logger.info(f"Stream load completed in {elapsed_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Error during stream load: {e}", exc_info=True)

def generate_dataset_chunk(dim, start_id, chunk_size, low=1, high=100):
    """
    生成数据段，返回 DataFrame
    """
    logger.info(f"Generating dataset chunk: start_id={start_id}, chunk_size={chunk_size}, dim={dim}")
    start_time = time.time()
    
    embeddings = np.random.uniform(low, high, size=(chunk_size, dim))
    df = pd.DataFrame({
        "id": np.arange(start_id, start_id + chunk_size),
        "category": np.random.randint(1, 10, size=chunk_size),  # 随机生成1-9的分类ID
        "embedding": embeddings.tolist()
    })
    
    elapsed_time = time.time() - start_time
    logger.info(f"Dataset chunk generated in {elapsed_time:.2f} seconds")
    return df

def generate_dataset(dim, num, low=1, high=100):
    """
    生成包含 ID 的向量表：DataFrame，列为 id, category 和 embedding（嵌套 list）
    """
    logger.info(f"Generating dataset with dim={dim}, num={num}")
    start_time = time.time()
    embeddings = np.random.uniform(low, high, size=(num, dim))
    df = pd.DataFrame({
        "id": np.arange(num),
        "category": np.random.randint(1, 10, size=num),  # 随机生成1-9的分类ID
        "embedding": embeddings.tolist()
    })
    logger.info(f"Dataset generated in {time.time() - start_time:.2f} seconds")
    return df

def check_chunk_exists_in_db(table_name, chunk_idx, chunk_size, db="vector_test", host="127.0.0.1", port=6937):
    """Check if chunk data already exists in database by checking row count"""
    try:
        conn = mysql.connector.connect(
            user="root",
            password="",
            host=host,
            port=port,
            database=db
        )
        cursor = conn.cursor()
        
        start_id = chunk_idx * chunk_size
        end_id = start_id + chunk_size - 1
        
        # Check if data in this chunk range exists
        query = f"SELECT COUNT(*) FROM {table_name} WHERE id >= {start_id} AND id <= {end_id}"
        cursor.execute(query)
        result = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        # If we have the expected number of rows, chunk exists
        expected_rows = chunk_size
        actual_rows = result[0] if result else 0
        
        logger.info(f"Chunk {chunk_idx}: expected {expected_rows} rows, found {actual_rows} rows in DB")
        return actual_rows == expected_rows
        
    except mysql.connector.Error as err:
        logger.warning(f"Could not check chunk {chunk_idx} in database: {err}")
        return False

def process_large_dataset_in_chunks(dim, total_count, table_name, data_dir, db="vector_test"):
    """
    分段处理大数据集，每50万行为一个段，支持断点续传
    """
    logger.info(f"Processing large dataset in chunks: dim={dim}, total_count={total_count}")
    
    # 计算需要的段数
    num_chunks = (total_count + CHUNK_SIZE - 1) // CHUNK_SIZE
    logger.info(f"Will process {num_chunks} chunks of max {CHUNK_SIZE} rows each")
    
    total_start_time = time.time()
    processed_chunks = 0
    skipped_chunks = 0
    
    for chunk_idx in range(num_chunks):
        chunk_start_time = time.time()
        start_id = chunk_idx * CHUNK_SIZE
        current_chunk_size = min(CHUNK_SIZE, total_count - start_id)
        
        logger.info(f"=== Processing chunk {chunk_idx + 1}/{num_chunks} ===")
        logger.info(f"Chunk range: {start_id} to {start_id + current_chunk_size - 1} (size: {current_chunk_size})")
        
        # 检查TSV文件是否存在
        tsv_path = os.path.join(data_dir, f"{table_name}_chunk_{chunk_idx}.tsv")
        tsv_exists = os.path.exists(tsv_path)
        
        # 检查数据库中是否已有该chunk的数据
        db_has_chunk = check_chunk_exists_in_db(table_name, chunk_idx, current_chunk_size, db)
        
        if tsv_exists and db_has_chunk:
            logger.info(f"Chunk {chunk_idx} already exists in both file and database, skipping")
            skipped_chunks += 1
            chunk_elapsed = time.time() - chunk_start_time
            logger.info(f"Chunk {chunk_idx + 1} skipped in {chunk_elapsed:.2f} seconds")
        else:
            # 如果TSV不存在，需要生成数据并保存
            if not tsv_exists:
                logger.info(f"TSV file not found, generating chunk {chunk_idx} data")
                dataset_chunk = generate_dataset_chunk(dim, start_id, current_chunk_size)
                tsv_path = save_dataset_chunk_to_tsv(dataset_chunk, table_name, chunk_idx, data_dir)
                # 清理内存
                del dataset_chunk
            else:
                logger.info(f"TSV file exists at {tsv_path}, using existing file")
            
            # 如果数据库中没有数据，需要加载
            if not db_has_chunk:
                logger.info(f"Database doesn't have chunk {chunk_idx} data, loading from TSV")
                stream_load_to_doris(table_name, tsv_path, db=db)
            else:
                logger.info(f"Database already has chunk {chunk_idx} data, skipping load")
            
            processed_chunks += 1
            chunk_elapsed = time.time() - chunk_start_time
            logger.info(f"Chunk {chunk_idx + 1} processed in {chunk_elapsed:.2f} seconds")
        
        # 进度报告
        completed_rows = (chunk_idx + 1) * CHUNK_SIZE if chunk_idx < num_chunks - 1 else total_count
        progress = (completed_rows / total_count) * 100
        logger.info(f"Progress: {completed_rows}/{total_count} rows ({progress:.1f}%)")
    
    total_elapsed = time.time() - total_start_time
    logger.info(f"All chunks completed in {total_elapsed:.2f} seconds")
    logger.info(f"Processed chunks: {processed_chunks}, Skipped chunks: {skipped_chunks}")
    if processed_chunks > 0:
        logger.info(f"Average time per processed chunk: {total_elapsed / processed_chunks:.2f} seconds")

def generate_create_table_sql(dim, num):
    logger.info(f"Generating SQL for table with dim={dim}, num={num}")
    table_name = f"dim_{dim}_num_{num}"
    return f"""
CREATE TABLE `{table_name}` (
  `id` int NOT NULL COMMENT "",
  `category` int NOT NULL COMMENT "分类ID",
  `embedding` array<float>  NOT NULL  COMMENT "",
  INDEX idx_test_ann (`embedding`) USING ANN PROPERTIES (
      "index_type"="hnsw",
      "metric_type"="l2_distance",
      "dim"="{dim}"
  )
) ENGINE=OLAP
DUPLICATE KEY(`id`) COMMENT "OLAP"
DISTRIBUTED BY HASH(`id`) BUCKETS 1
PROPERTIES (
  "replication_num" = "1",
  "disable_auto_compaction" = "true"
);
"""

def get_conn():
    logger.info("Establishing database connection")
    try:
        conn = mysql.connector.connect(
            user="root",
            password="",
            host="127.0.0.1",
            port=6937
        )
        logger.info("Database connection successful")
        return conn
    except mysql.connector.Error as err:
        logger.error(f"Database connection failed: {err}")
        raise


def load_sift():
    """Load SIFT-1M dataset to Doris"""
    logger.info("Loading SIFT 1M dataset")
    
    # 1. Load SIFT-1M dataset from data directory.
    # User should link the pre-downloaded SIFT-1M dataset to the data directory.
    # http://corpus-texmex.irisa.fr/
    dataSet = DatasetSIFT1M()
    query = dataSet.get_queries()
    database = dataSet.get_database()
    groundtruth = dataSet.get_groundtruth()
    # 2. Do transformation. We need a tsv file, so that we can use Doris stream load.

    data_dir = create_data_directory()
    num = database.shape[0]
    dim = database.shape[1]
    df = pd.DataFrame({
        "id": np.arange(num),
        "embedding": database.tolist()
    })
    table_name = f"sift1m_dim_{dim}_num_{num}"
    tsv_path = save_dataset_to_tsv(df, table_name, data_dir)
    logger.info(f"SIFT-1M dataset saved to {tsv_path}")

    # 3. Load data into Doris using Stream Load.
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("DROP DATABASE IF EXISTS sift_1m;")
        cursor.execute("CREATE DATABASE sift_1m;")
        cursor.execute("USE sift_1m;")
        
        
    except mysql.connector.Error as err:
        logger.error(f"Error loading SIFT small dataset: {err}")
    finally:
        cursor.close()
        conn.close()

def check_database_exists(cursor, db_name):
    """Check if database exists"""
    cursor.execute("SHOW DATABASES;")
    databases = [row[0] for row in cursor.fetchall()]
    return db_name in databases

def check_table_exists(cursor, table_name):
    """Check if table exists"""
    cursor.execute("SHOW TABLES;")
    tables = [row[0] for row in cursor.fetchall()]
    return table_name in tables

def main():
    # bench_datasets = 'sift_small sift gist sift_large'.split()
    # ds_name = str(sys.argv[1])
    # logger.info("Starting load data.")
    
    # if ds_name  == 'sift':
    #     load_sift()
    #     return
    # else:
    #     logger.error(f"Dataset {ds_name} is not supported. Supported datasets: {bench_datasets}")
    #     return
    
    # Add mode parameter
    import argparse
    parser = argparse.ArgumentParser(description='Load data to Doris')
    parser.add_argument('--mode', choices=['force', 'skip'], default='force', 
                        help='force: drop and recreate database/table; skip: skip if exists (default)')
    args = parser.parse_args()
    
    try:
        # Create data directory
        data_dir = create_data_directory()
        
        conn = get_conn()
        cursor = conn.cursor()
        db = "vector_test"
        
        if args.mode == 'force':
            logger.info("Dropping database if exists")
            cursor.execute(f"DROP DATABASE IF EXISTS {db}")
            
            logger.info(f"Creating database {db}")
            cursor.execute(f"CREATE DATABASE {db}")
            
            logger.info(f"Switching to {db} database")
            cursor.execute(f"USE {db}")
        else:
            # Check if database exists, create if not
            if not check_database_exists(cursor, db):
                logger.info(f"Creating database {db}")
                cursor.execute(f"CREATE DATABASE {db}")
            else:
                logger.info(f"Database {db} already exists, using existing database")
            
            logger.info(f"Switching to {db} database")
            cursor.execute(f"USE {db}")

        # dims = [1, 4, 8, 16, 32, 64, 128, 256, 512, 1024]
        # dims = [512, 716, 1024]
        # counts = [1, 5, 10, 50, 100, 500, 1000, 5000, 10000]
        # dims = [1024, 2048, 4096, 8192]
        dims = [1]
        # dims = [716]
        counts = [10]
        # counts = [10000000]

        logger.info(f"Testing dimensions: {dims}")
        logger.info(f"Testing counts: {counts}")
        logger.info(f"Chunk size: {CHUNK_SIZE} rows per chunk")

        for dim in dims:
            for count in counts:
                logger.info(f"=== Processing dim={dim}, count={count} ===")
                
                # Create table
                table_name = f"dim_{dim}_num_{count}"
                
                # Check if table exists in skip mode
                table_exists = check_table_exists(cursor, table_name)
                
                if args.mode == 'force' or not table_exists:
                    if table_exists:
                        logger.info(f"Dropping table {table_name}")
                        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
                    
                    logger.info(f"Creating table {table_name}")
                    create_table_sql = generate_create_table_sql(dim, count)
                    cursor.execute(create_table_sql)
                    
                    # 判断是否需要分段处理
                    if count > CHUNK_SIZE:
                        logger.info(f"Large dataset detected ({count} rows > {CHUNK_SIZE}), processing in chunks")
                        process_large_dataset_in_chunks(dim, count, table_name, data_dir, db)
                    else:
                        logger.info(f"Small dataset ({count} rows <= {CHUNK_SIZE}), processing normally")
                        # Generate dataset
                        dataset = generate_dataset(dim, count)
                        
                        # Save dataset to TSV instead of CSV
                        tsv_path = save_dataset_to_tsv(dataset, table_name, data_dir)
                        
                        # Load data using stream load with the TSV file
                        logger.info(f"Loading {count} rows into table {table_name} using stream load")
                        stream_load_to_doris(table_name, tsv_path, db=db)
                else:
                    logger.info(f"Table {table_name} already exists, skipping data import")
                
                logger.info(f"Completed processing for dim={dim}, count={count}")
                
            logger.info(f"Finished processing dimension {dim}")

        logger.info("Closing database connection")
        cursor.close()
        conn.close()
        logger.info("Process completed successfully")
        
    except Exception as e:
        logger.error(f"Error in main process: {e}", exc_info=True)
    
    
if __name__ == "__main__":
    main()
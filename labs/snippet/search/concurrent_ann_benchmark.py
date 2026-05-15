import mysql.connector
import logging
import os
import random
import time
import threading
import concurrent.futures
from typing import List, Tuple, Any
import numpy as np
from query import get_conn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Global variables for benchmarking
benchmark_results = []
lock = threading.Lock()

def read_tsv_data(file_path: str) -> Tuple[List[str], List[str]]:
    """Read data from TSV file and return IDs and embeddings"""
    ids = []
    embeddings = []
    
    with open(file_path, "r") as f:
        lines = f.readlines()
        for line in lines:
            parts = line.strip().split("\t")
            if len(parts) >= 3:  # id, category, embedding
                ids.append(parts[0])
                embeddings.append(parts[2])  # embedding is the third column
    
    return ids, embeddings

def execute_query(cursor, sql: str) -> Tuple[List[Tuple], float]:
    """Execute a query and return results with execution time"""
    start_time = time.time()
    cursor.execute(sql)
    results = cursor.fetchall()
    execution_time = time.time() - start_time
    return results, execution_time

def range_search_task(table: str, query_vector: str, radius: float, iteration: int) -> dict:
    """Execute a range search query"""
    sql = f"""SELECT id, l2_distance_approximate(embedding, {query_vector})
              FROM {table} WHERE l2_distance_approximate(embedding, {query_vector}) < {radius} LIMIT 100;"""
    
    conn = None
    cursor = None
    try:
        # Create a new connection for each query
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("USE vector_test;")
        results, exec_time = execute_query(cursor, sql)
        
        return {
            "type": "range",
            "table": table,
            "iteration": iteration,
            "execution_time": exec_time,
            "result_count": len(results),
            "success": True
        }
    except Exception as e:
        logger.error(f"Range search failed: {e}")
        return {
            "type": "range",
            "table": table,
            "iteration": iteration,
            "execution_time": 0,
            "result_count": 0,
            "success": False,
            "error": str(e)
        }
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def topn_search_task(table: str, query_vector: str, topk: int, iteration: int) -> dict:
    """Execute a top-N search query"""
    sql = f"""SELECT id, l2_distance_approximate(embedding, {query_vector})
              FROM {table} ORDER BY l2_distance_approximate(embedding, {query_vector}) LIMIT {topk};"""
    
    conn = None
    cursor = None
    try:
        # Create a new connection for each query
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("USE vector_test;")
        results, exec_time = execute_query(cursor, sql)
        
        return {
            "type": "topn",
            "table": table,
            "iteration": iteration,
            "execution_time": exec_time,
            "result_count": len(results),
            "success": True
        }
    except Exception as e:
        logger.error(f"Top-N search failed: {e}")
        return {
            "type": "topn",
            "table": table,
            "iteration": iteration,
            "execution_time": 0,
            "result_count": 0,
            "success": False,
            "error": str(e)
        }
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def compound_search_task(table: str, query_vector: str, radius: float, topk: int, iteration: int) -> dict:
    """Execute a compound search query"""
    sql = f"""SELECT id, l2_distance_approximate(embedding, {query_vector})
              FROM {table} WHERE l2_distance_approximate(embedding, {query_vector}) < {radius}
              ORDER BY l2_distance_approximate(embedding, {query_vector}) LIMIT {topk};"""
    
    conn = None
    cursor = None
    try:
        # Create a new connection for each query
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("USE vector_test;")
        results, exec_time = execute_query(cursor, sql)
        
        return {
            "type": "compound",
            "table": table,
            "iteration": iteration,
            "execution_time": exec_time,
            "result_count": len(results),
            "success": True
        }
    except Exception as e:
        logger.error(f"Compound search failed: {e}")
        return {
            "type": "compound",
            "table": table,
            "iteration": iteration,
            "execution_time": 0,
            "result_count": 0,
            "success": False,
            "error": str(e)
        }
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def worker_thread(thread_id: int, tables: List[str], iterations: int, concurrent_queries: int, data_dir: str):
    """Worker thread function that executes queries"""
    logger.info(f"Thread {thread_id} started")
    
    thread_results = []
    
    for i in range(iterations):
        # Select a random table
        table = random.choice(tables)
        
        # Read data from TSV
        tsv_path = os.path.join(data_dir, f"{table}.tsv")
        if not os.path.exists(tsv_path):
            logger.warning(f"TSV file not found: {tsv_path}")
            continue
            
        ids, embeddings = read_tsv_data(tsv_path)
        if not embeddings:
            logger.warning(f"No data in TSV file: {tsv_path}")
            continue
            
        # Select a random query vector
        random_idx = random.randint(0, len(embeddings) - 1)
        query_vector = embeddings[random_idx]
        
        # Execute concurrent queries
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_queries) as executor:
            futures = []
            
            # Submit range search task
            radius = random.uniform(5.0, 20.0)
            futures.append(executor.submit(range_search_task, table, query_vector, radius, i))
            
            # Submit top-N search task
            topk = random.randint(5, 50)
            futures.append(executor.submit(topn_search_task, table, query_vector, topk, i))
            
            # Submit compound search task
            compound_radius = random.uniform(2.0, 10.0)
            compound_topk = random.randint(3, 20)
            futures.append(executor.submit(compound_search_task, table, query_vector, compound_radius, compound_topk, i))
            
            # Collect results
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    result["thread_id"] = thread_id
                    thread_results.append(result)
                except Exception as e:
                    logger.error(f"Task execution failed: {e}")
    
    # Add results to global list
    with lock:
        benchmark_results.extend(thread_results)
        
    logger.info(f"Thread {thread_id} completed with {len(thread_results)} results")

def print_benchmark_summary():
    """Print benchmark summary statistics"""
    if not benchmark_results:
        logger.info("No benchmark results to display")
        return
    
    logger.info("\n" + "="*80)
    logger.info("CONCURRENT ANN BENCHMARK SUMMARY")
    logger.info("="*80)
    
    # Group results by type
    range_results = [r for r in benchmark_results if r["type"] == "range"]
    topn_results = [r for r in benchmark_results if r["type"] == "topn"]
    compound_results = [r for r in benchmark_results if r["type"] == "compound"]
    
    # Calculate statistics
    def calculate_stats(results):
        if not results:
            return {"count": 0}
        
        success_count = len([r for r in results if r["success"]])
        exec_times = [r["execution_time"] for r in results if r["success"]]
        result_counts = [r["result_count"] for r in results if r["success"]]
        
        return {
            "count": len(results),
            "success_rate": success_count / len(results) * 100,
            "avg_time": np.mean(exec_times) if exec_times else 0,
            "min_time": np.min(exec_times) if exec_times else 0,
            "max_time": np.max(exec_times) if exec_times else 0,
            "avg_results": np.mean(result_counts) if result_counts else 0
        }
    
    range_stats = calculate_stats(range_results)
    topn_stats = calculate_stats(topn_results)
    compound_stats = calculate_stats(compound_results)
    
    # Print statistics
    logger.info(f"Range Search: {range_stats['count']} queries, "
                f"{range_stats['success_rate']:.2f}% success, "
                f"Avg time: {range_stats['avg_time']:.4f}s, "
                f"Avg results: {range_stats['avg_results']:.2f}")
    
    logger.info(f"Top-N Search: {topn_stats['count']} queries, "
                f"{topn_stats['success_rate']:.2f}% success, "
                f"Avg time: {topn_stats['avg_time']:.4f}s, "
                f"Avg results: {topn_stats['avg_results']:.2f}")
    
    logger.info(f"Compound Search: {compound_stats['count']} queries, "
                f"{compound_stats['success_rate']:.2f}% success, "
                f"Avg time: {compound_stats['avg_time']:.4f}s, "
                f"Avg results: {compound_stats['avg_results']:.2f}")
    
    # Overall statistics
    total_queries = len(benchmark_results)
    total_success = len([r for r in benchmark_results if r["success"]])
    overall_success_rate = total_success / total_queries * 100 if total_queries > 0 else 0
    
    logger.info(f"\nOverall: {total_queries} queries, "
                f"{overall_success_rate:.2f}% success rate")

def main():
    # Configuration
    tables = [
        "dim_512_num_10",
        "dim_512_num_1000",
        "dim_512_num_2000",
        "dim_512_num_5000",
        "dim_716_num_10",
        "dim_716_num_1000",
        "dim_716_num_2000",
        "dim_716_num_5000",
        "dim_716_num_10000"
    ]
    
    num_threads = 5
    iterations_per_thread = 10
    concurrent_queries_per_thread = 3
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, 'data')
    
    logger.info("Starting concurrent ANN benchmark")
    logger.info(f"Configuration: {num_threads} threads, "
                f"{iterations_per_thread} iterations per thread, "
                f"{concurrent_queries_per_thread} concurrent queries per thread")
    
    # Start worker threads
    start_time = time.time()
    threads = []
    
    for i in range(num_threads):
        thread = threading.Thread(
            target=worker_thread,
            args=(i, tables, iterations_per_thread, concurrent_queries_per_thread, data_dir)
        )
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    total_time = time.time() - start_time
    logger.info(f"All threads completed in {total_time:.2f} seconds")
    
    # Print benchmark summary
    print_benchmark_summary()

if __name__ == "__main__":
    main()
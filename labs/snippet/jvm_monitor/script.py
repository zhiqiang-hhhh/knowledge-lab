import subprocess
import time
import re
import logging

# 设置日志配置
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def get_heap_size(pid):
    """运行 jcmd GC.heap_info 获取堆大小"""
    try:
        output = subprocess.check_output(['jcmd', str(pid), 'GC.heap_info'], text=True)
        # logging.debug(f"jcmd GC.heap_info output:\n{output}")
        # 输出类似 garbage-first heap   total 8388608K, used 5507056K [0x0000000600000000, 0x0000000800000000)
        match = re.search(r'used\s*(\d+)', output)
        if match:
            heap_size_bytes = int(match.group(1))
            return heap_size_bytes / (1024 * 1024)  # 转换为 GB
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running jcmd: {e}")
    return 0

def run_class_histogram(pid):
    """运行 jcmd GC.class_histogram 并解析输出"""
    try:
        output = subprocess.check_output(['jcmd', str(pid), 'GC.class_histogram'], text=True)
        # logging.debug(f"jcmd GC.class_histogram output:\n{output}")
        lines = output.splitlines()[3:]  # 跳过前 3 行的非数据部分
        histogram = []
        for line in lines:
            match = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(.+)', line)
            if match:
                instances = int(match.group(1))
                size = int(match.group(2))
                class_name = match.group(3)
                histogram.append((instances, size, class_name))
        return histogram
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running jcmd: {e}")
    return []

def main(pid):
    while True:
        heap_size = get_heap_size(pid)
        logging.info(f"Current heap size: {heap_size:.2f} GB")
        
        if heap_size > 6:
            logging.info("Heap size exceeds 6GB. Running GC.class_histogram...")
            histogram = run_class_histogram(pid)
            
            # 排序并获取前 20 项
            top_20 = sorted(histogram, key=lambda x: x[1], reverse=True)[:20]
            logging.info("Top 20 objects by size:")
            for instances, size, class_name in top_20:
                logging.info(f"{class_name}: {instances} instances, {size} bytes")
            
            # 查找以 org.apache.doris.common.profile 开头的对象
            matching_objects = [
                (instances, size, class_name)
                for instances, size, class_name in histogram
                if class_name.startswith("org.apache.doris.common.profile")
            ]
            logging.info("\nObjects matching 'org.apache.doris.common.profile':")
            for instances, size, class_name in matching_objects:
                logging.info(f"{class_name}: {instances} instances, {size} bytes")
            
            # 改文件目录
            with open('/mnt/disk4/hezhiqiang/Code/snippet/jvm_monitor/output.txt', 'w') as f:
                f.write("\nTop 20 objects by size:\n")
                for instances, size, class_name in top_20:
                    f.write(f"{class_name}: {instances} instances, {size} bytes\n")
                
                f.write("\nObjects matching 'org.apache.doris.common.profile':\n")
                for instances, size, class_name in matching_objects:
                    f.write(f"{class_name}: {instances} instances, {size} bytes\n")
        time.sleep(1)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Monitor JVM heap size and analyze objects.")
    parser.add_argument("pid", type=int, help="Target JVM process ID")
    args = parser.parse_args()

    main(args.pid)

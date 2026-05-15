import mysql.connector

def get_conn():
    conn = mysql.connector.connect(
        user="root",
        password="",
        host="127.0.0.1",
        port=6937
    )
    return conn

def delete_databases():
    try:
        conn = get_conn()
        cursor = conn.cursor()
        
        # 获取所有数据库
        cursor.execute("SHOW DATABASES")
        databases = cursor.fetchall()
        
        # 过滤并删除以 test_ 和 regression_ 开头的数据库
        for (db_name,) in databases:
            if db_name.startswith("test_") or db_name.startswith("regression_") or db_name.startswith("nereids_"):
                print(f"Deleting database: {db_name}")
                cursor.execute(f"DROP DATABASE `{db_name}`")
        
        conn.commit()
        print("Specified databases have been deleted successfully.")
    
    except mysql.connector.Error as e:
        print(f"Error: {e}")
    
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    delete_databases()

import mysql.connector
import uuid
import logging
import myprofile as profile

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s][%(levelname)s][%(filename)s:%(lineno)d] - %(message)s')

def generate_uuid():
    return str(uuid.uuid4())

def get_analyze_cluster_conn() :
    conn = mysql.connector.connect(
        user="root", password="", host='127.0.0.1', port=6937)
    return conn

connection = get_analyze_cluster_conn()
cursor = connection.cursor()
cursor.execute("SET enable_profile=true;")
cursor.execute("USE demo")
should_break = False
while should_break == False:
    begin_uuid = generate_uuid()
    end_uuid = generate_uuid()
    logging.info("Begin UUID: %s, end UUID: %s", begin_uuid, end_uuid)
    cursor.execute(f"SELECT '{begin_uuid}'")  # Generate a unique identifier
    cursor.fetchall()

    cursor.execute("select split_by_string('null',',')")
    cursor.fetchall()

    cursor.execute(f"SELECT '{end_uuid}'")  # Generate a unique identifier
    cursor.fetchall()
    profile_ids = profile.get_profile_list_by_range("root", "", begin_uuid, end_uuid, "demo")
    profile_ids = profile_ids[1:-1]
    logging.info(f"Profile IDs: {profile_ids}")
    for profile_id in profile_ids:
        profile_content = profile.get_profile_content("127.0.0.1", 5937, "root", "", profile_id)
        if "build  merged  simple  profile  failed" in profile_content:
            should_break = True
            logging.info(f"{profile_content}")
            break
            



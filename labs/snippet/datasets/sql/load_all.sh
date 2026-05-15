#!/usr/bin/env bash
# ============================================================
# 批量 Stream Load + ETL 导入脚本
# 用法: bash load_all.sh [fe_host] [http_port] [query_port] [db] [user] [password]
# 示例: bash load_all.sh 127.0.0.1 8030 9030 test_demo root
#
# 流程:
#   Step 0: 创建数据库
#   Step 1: 建表 (执行 0*.sql DDL)
#   Step 2: Stream Load 导入最小表数据文件
#            - 128D: 只导入 sift_user_1w / sift_user_1w_pq
#            - 768D: 只导入 cohere_user_1w / cohere_user_1w_pq
#   Step 3: ETL 扩展到更大规模表
#            - 1w -> 10w -> 50w -> 100w
#   Step 4: 为 pq_on_disk 表补建 ANN 索引并执行 BUILD INDEX
#   Step 5: 验证数据量
#
# 可选环境变量:
#   PARALLEL=4        并行导入路数 (默认4)
#   SKIP_DDL=1        跳过建库/建表步骤
#   TABLES="1w 10w"   只导入指定规模的表 (默认全部)
#   DIMS="768d"       只导入指定维度: 128d, 768d, all (默认 all)
#   INDEX_MODE="pq_on_disk"  导入 pq_on_disk ANN 表; 否则导入普通表 (默认 bruteforce)
#   LOAD_MODE="etl_only"   etl_only / stream_only (默认 etl_only)
# ============================================================

set -euo pipefail

FE_HOST="${1:-127.0.0.1}"
HTTP_PORT="${2:-8030}"
QUERY_PORT="${3:-9030}"
DB="${4:-test_demo}"
USER="${5:-root}"
PASSWORD="${6:-}"
PARALLEL="${PARALLEL:-4}"
INDEX_MODE="${INDEX_MODE:-bruteforce}"
LOAD_MODE="${LOAD_MODE:-etl_only}"

if [ "$LOAD_MODE" != "etl_only" ] && [ "$LOAD_MODE" != "stream_only" ]; then
  echo "[ERROR] LOAD_MODE must be 'etl_only' or 'stream_only', got: ${LOAD_MODE}"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$(dirname "$SCRIPT_DIR")"

BASE_URL="http://${FE_HOST}:${HTTP_PORT}/api/${DB}"

table_count() {
  local table="$1"
  ${MYSQL_CMD} -D "${DB}" -N -e "SELECT COUNT(*) FROM ${table};" 2>/dev/null || echo "N/A"
}

table_ready() {
  local table="$1"
  local expected="$2"
  local count
  count=$(table_count "$table")
  [ "$count" = "$expected" ]
}

index_exists() {
  local table="$1"
  local index_name="$2"
  local count
  count=$(${MYSQL_CMD} -D "${DB}" -N -e "SHOW INDEX FROM ${table};" 2>/dev/null | awk -v idx="${index_name}" '$3 == idx {count++} END {print count + 0}')
  [ "$count" -gt 0 ]
}

# 构建 mysql 命令（密码为空时不加 -p）
if [ -n "$PASSWORD" ]; then
  MYSQL_CMD="mysql -h ${FE_HOST} -P ${QUERY_PORT} -u ${USER} -p${PASSWORD}"
else
  MYSQL_CMD="mysql -h ${FE_HOST} -P ${QUERY_PORT} -u ${USER}"
fi

# --------------------------------------------------
# 创建临时的 shard 导入脚本 (避免 export -f 的兼容性问题)
# --------------------------------------------------
LOAD_HELPER=$(mktemp /tmp/load_shard_XXXXXX.sh)
trap 'rm -f "$LOAD_HELPER"' EXIT

cat > "$LOAD_HELPER" <<'HELPER_EOF'
#!/usr/bin/env bash
# 参数: <table> <shard_file> <base_url> <user> <password>
set -euo pipefail

TABLE="$1"
SHARD_FILE="$2"
BASE_URL="$3"
LOAD_USER="$4"
LOAD_PASSWORD="$5"

SHARD_NAME="$(basename "$SHARD_FILE")"
LABEL="${TABLE}_${SHARD_NAME%.tsv.gz}_$(date +%s%N)"

echo "[LOAD] ${TABLE} <- ${SHARD_NAME}"

result=$(zcat "$SHARD_FILE" | \
  curl --location-trusted -s \
    -u "${LOAD_USER}:${LOAD_PASSWORD}" \
    -H "column_separator:\t" \
    -H "columns: user_id, id, embedding" \
    -H "label:${LABEL}" \
    -T - \
    "${BASE_URL}/${TABLE}/_stream_load" 2>&1)

# 用 python3 提取 Status 字段; 如果 JSON 解析失败则用 grep 兜底
status=$(echo "$result" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('Status', 'UNKNOWN'))
except Exception:
    print('PARSE_ERROR')
" 2>/dev/null)

if [ -z "$status" ]; then
  status="PARSE_ERROR"
fi

if [ "$status" = "Success" ]; then
  # 提取行数
  loaded=$(echo "$result" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('NumberLoadedRows', '?'))
except Exception:
    print('?')
" 2>/dev/null)
  echo "[OK]   ${TABLE} <- ${SHARD_NAME} (${loaded} rows)"
else
  echo "[FAIL] ${TABLE} <- ${SHARD_NAME}: status=${status}"
  # 截取前500字符输出方便调试
  echo "       ${result:0:500}"
  exit 1
fi
HELPER_EOF
chmod +x "$LOAD_HELPER"

# --------------------------------------------------
# 定义表与数据集的映射
# --------------------------------------------------
# --------------------------------------------------
# 128D (SIFT) 表映射 — 全部 4 个规模都有本地数据文件
# --------------------------------------------------
declare -A TABLE_MAP_128D=(
  ["10k"]="sift_user_1w"
  ["100k"]="sift_user_10w"
  ["500k"]="sift_user_50w"
  ["1m"]="sift_user_100w"
)
declare -A TABLE_MAP_128D_PQ=(
  ["10k"]="sift_user_1w_pq"
  ["100k"]="sift_user_10w_pq"
  ["500k"]="sift_user_50w_pq"
  ["1m"]="sift_user_100w_pq"
)
declare -A DATASET_MAP_128D=(
  ["10k"]="dataset_1w"
)

# --------------------------------------------------
# 768D (Cohere) 表映射
# Stream load 只导入 1w; 10w/50w/100w 由 Step 3 ETL 扩展
# --------------------------------------------------
declare -A TABLE_MAP_768D=(
  ["10k"]="cohere_user_1w"
  ["100k"]="cohere_user_10w"
  ["500k"]="cohere_user_50w"
  ["1m"]="cohere_user_100w"
)
declare -A TABLE_MAP_768D_PQ=(
  ["10k"]="cohere_user_1w_pq"
  ["100k"]="cohere_user_10w_pq"
  ["500k"]="cohere_user_50w_pq"
  ["1m"]="cohere_user_100w_pq"
)
declare -A DATASET_MAP_768D=(
  ["10k"]="dataset_768d_1w"
)

# 支持 TABLES 环境变量指定只导入部分规模 (默认全部)
SCALE_LIST="${TABLES:-10k 100k 500k 1m}"
# 支持 DIMS 环境变量指定维度: 128d, 768d, 或 all (默认 all)
DIMS="${DIMS:-all}"

declare -A EXPECTED_ROWS=(
  ["10k"]="1000000"
  ["100k"]="10000000"
  ["500k"]="50000000"
  ["1m"]="100000000"
)

declare -A ANN_INDEX_SQL_128D=(
  ["10k"]="CREATE INDEX idx_embedding_ann ON sift_user_1w_pq (`embedding`) USING ANN PROPERTIES(\"index_type\"=\"pq_on_disk\", \"metric_type\"=\"l2_distance\", \"dim\"=\"128\", \"pq_m\"=\"64\", \"pq_nbits\"=\"8\")"
  ["100k"]="CREATE INDEX idx_embedding_ann ON sift_user_10w_pq (`embedding`) USING ANN PROPERTIES(\"index_type\"=\"pq_on_disk\", \"metric_type\"=\"l2_distance\", \"dim\"=\"128\", \"pq_m\"=\"64\", \"pq_nbits\"=\"8\")"
  ["500k"]="CREATE INDEX idx_embedding_ann ON sift_user_50w_pq (`embedding`) USING ANN PROPERTIES(\"index_type\"=\"pq_on_disk\", \"metric_type\"=\"l2_distance\", \"dim\"=\"128\", \"pq_m\"=\"64\", \"pq_nbits\"=\"8\")"
  ["1m"]="CREATE INDEX idx_embedding_ann ON sift_user_100w_pq (`embedding`) USING ANN PROPERTIES(\"index_type\"=\"pq_on_disk\", \"metric_type\"=\"l2_distance\", \"dim\"=\"128\", \"pq_m\"=\"64\", \"pq_nbits\"=\"8\")"
)
declare -A ANN_INDEX_SQL_768D=(
  ["10k"]="CREATE INDEX idx_embedding_ann ON cohere_user_1w_pq (`embedding`) USING ANN PROPERTIES(\"index_type\"=\"pq_on_disk\", \"metric_type\"=\"inner_product\", \"dim\"=\"768\", \"pq_m\"=\"384\", \"pq_nbits\"=\"8\")"
  ["100k"]="CREATE INDEX idx_embedding_ann ON cohere_user_10w_pq (`embedding`) USING ANN PROPERTIES(\"index_type\"=\"pq_on_disk\", \"metric_type\"=\"inner_product\", \"dim\"=\"768\", \"pq_m\"=\"384\", \"pq_nbits\"=\"8\")"
  ["500k"]="CREATE INDEX idx_embedding_ann ON cohere_user_50w_pq (`embedding`) USING ANN PROPERTIES(\"index_type\"=\"pq_on_disk\", \"metric_type\"=\"inner_product\", \"dim\"=\"768\", \"pq_m\"=\"384\", \"pq_nbits\"=\"8\")"
  ["1m"]="CREATE INDEX idx_embedding_ann ON cohere_user_100w_pq (`embedding`) USING ANN PROPERTIES(\"index_type\"=\"pq_on_disk\", \"metric_type\"=\"inner_product\", \"dim\"=\"768\", \"pq_m\"=\"384\", \"pq_nbits\"=\"8\")"
)

DDL_PAIRS=()

if [ "$INDEX_MODE" = "pq_on_disk" ]; then
  if [ "$DIMS" = "all" ] || [ "$DIMS" = "128d" ]; then
    DDL_PAIRS+=(
      "${SCRIPT_DIR}/09_sift_user_1w_pq.sql:sift_user_1w_pq:10k"
      "${SCRIPT_DIR}/10_sift_user_10w_pq.sql:sift_user_10w_pq:100k"
      "${SCRIPT_DIR}/11_sift_user_50w_pq.sql:sift_user_50w_pq:500k"
      "${SCRIPT_DIR}/12_sift_user_100w_pq.sql:sift_user_100w_pq:1m"
    )
  fi
  if [ "$DIMS" = "all" ] || [ "$DIMS" = "768d" ]; then
    DDL_PAIRS+=(
      "${SCRIPT_DIR}/13_cohere_user_1w_pq.sql:cohere_user_1w_pq:10k"
      "${SCRIPT_DIR}/14_cohere_user_10w_pq.sql:cohere_user_10w_pq:100k"
      "${SCRIPT_DIR}/15_cohere_user_50w_pq.sql:cohere_user_50w_pq:500k"
      "${SCRIPT_DIR}/16_cohere_user_100w_pq.sql:cohere_user_100w_pq:1m"
    )
  fi
else
  if [ "$DIMS" = "all" ] || [ "$DIMS" = "128d" ]; then
    DDL_PAIRS+=(
      "${SCRIPT_DIR}/01_sift_user_1w.sql:sift_user_1w:10k"
      "${SCRIPT_DIR}/02_sift_user_10w.sql:sift_user_10w:100k"
      "${SCRIPT_DIR}/03_sift_user_50w.sql:sift_user_50w:500k"
      "${SCRIPT_DIR}/04_sift_user_100w.sql:sift_user_100w:1m"
    )
  fi
  if [ "$DIMS" = "all" ] || [ "$DIMS" = "768d" ]; then
    DDL_PAIRS+=(
      "${SCRIPT_DIR}/05_cohere_user_1w.sql:cohere_user_1w:10k"
      "${SCRIPT_DIR}/06_cohere_user_10w.sql:cohere_user_10w:100k"
      "${SCRIPT_DIR}/07_cohere_user_50w.sql:cohere_user_50w:500k"
      "${SCRIPT_DIR}/08_cohere_user_100w.sql:cohere_user_100w:1m"
    )
  fi
fi

# --------------------------------------------------
# Step 0: 创建数据库
# --------------------------------------------------
if [ "${SKIP_DDL:-0}" != "1" ]; then
  echo "========================================"
  echo "Step 0: 创建数据库 ${DB}"
  echo "========================================"
  ${MYSQL_CMD} -e "CREATE DATABASE IF NOT EXISTS ${DB};" 2>&1 && \
    echo "[OK] 数据库 ${DB} 已就绪" || \
    echo "[WARN] 创建数据库失败，请手动执行: CREATE DATABASE IF NOT EXISTS ${DB};"

  # --------------------------------------------------
  # Step 1: 建表
  # --------------------------------------------------
  echo ""
  echo "========================================"
  echo "Step 1: 建表"
  echo "========================================"
  for ddl in "${DDL_PAIRS[@]}"; do
    sql_file="${ddl%%:*}"
    rest="${ddl#*:}"
    table="${rest%%:*}"
    scale="${rest##*:}"
    expected="${EXPECTED_ROWS[$scale]}"

    if table_ready "$table" "$expected"; then
      echo "[SKIP] $(basename "$sql_file") (${table} already ready: ${expected} rows)"
      continue
    fi

    echo "[SQL] 执行 $(basename "$sql_file")"
    ${MYSQL_CMD} -D "${DB}" < "$sql_file" 2>&1 && \
      echo "[OK]   $(basename "$sql_file")" || \
      echo "[FAIL] $(basename "$sql_file") - 请手动执行"
  done
fi

# --------------------------------------------------
# Step 2: Stream Load 导入本地数据文件
# --------------------------------------------------
LOAD_ERRORS=0

# 构建要导入的 (table, dataset) 列表
declare -a LOAD_PAIRS=()

for scale in ${SCALE_LIST}; do
  # 128D: 默认只导入 1w，其余通过 ETL 扩展
  if [ "$DIMS" = "all" ] || [ "$DIMS" = "128d" ]; then
    if [ "$INDEX_MODE" = "pq_on_disk" ]; then
      table_map_name="TABLE_MAP_128D_PQ"
    else
      table_map_name="TABLE_MAP_128D"
    fi
    eval 'table="${'"$table_map_name"'[$scale]:-}"'
    if [ "$scale" = "10k" ] && [ -n "$table" ] && [ -n "${DATASET_MAP_128D[$scale]+x}" ]; then
      dataset="${DATASET_MAP_128D[$scale]}"
      LOAD_PAIRS+=("${table}:${dataset}")
    fi
  fi
  # 768D: 只有 1w 有本地数据文件 (10w/50w/100w 由 ETL 扩展)
  if [ "$DIMS" = "all" ] || [ "$DIMS" = "768d" ]; then
    if [ "$INDEX_MODE" = "pq_on_disk" ]; then
      table_map_name="TABLE_MAP_768D_PQ"
    else
      table_map_name="TABLE_MAP_768D"
    fi
    eval 'table="${'"$table_map_name"'[$scale]:-}"'
    if [ -n "$table" ] && [ -n "${DATASET_MAP_768D[$scale]+x}" ]; then
      dataset="${DATASET_MAP_768D[$scale]}"
      LOAD_PAIRS+=("${table}:${dataset}")
    fi
  fi
done

if [ "$LOAD_MODE" = "stream_only" ] || [ "$LOAD_MODE" = "etl_only" ]; then
for pair in "${LOAD_PAIRS[@]}"; do
  table="${pair%%:*}"
  dataset="${pair##*:}"
  shard_dir="${DATA_DIR}/${dataset}"
  expected="${EXPECTED_ROWS[10k]}"

  if table_ready "$table" "$expected"; then
    echo "[SKIP] ${table} already has expected rows (${expected})"
    continue
  fi

  if [ ! -d "$shard_dir" ]; then
    echo "[SKIP] ${shard_dir} 不存在，跳过 ${table}"
    continue
  fi

  shard_count=$(find "${shard_dir}" -name 'shard_*.tsv.gz' | wc -l)

  echo ""
  echo "========================================"
  echo "Step 2: 导入 ${table} (${shard_count} shards, ${PARALLEL} parallel)"
  echo "========================================"

  # 使用 find + xargs 调用外部脚本，避免 export -f 问题
  # xargs 会将退出码传播回来，-P 控制并行度
  find "${shard_dir}" -name 'shard_*.tsv.gz' -print0 | sort -z | \
    xargs -0 -I{} -P "${PARALLEL}" \
      bash "$LOAD_HELPER" "$table" "{}" "$BASE_URL" "$USER" "$PASSWORD" \
    || LOAD_ERRORS=$((LOAD_ERRORS + 1))

  echo "[DONE] ${table} 导入完成"
done
fi

# --------------------------------------------------
# Step 3: ETL 扩展表 (1w -> 10w -> 50w -> 100w)
#
# 通过 INSERT INTO SELECT 复制数据并偏移 id，避免本地生成大文件。
# 每一步从较小的表复制多批到较大的表:
#   cohere_user_1w  (100用户 x 10,000)  --x10--> cohere_user_10w  (100用户 x 100,000)
#   cohere_user_10w (100用户 x 100,000) --x5-->  cohere_user_50w  (100用户 x 500,000)
#   cohere_user_50w (100用户 x 500,000) --x2-->  cohere_user_100w (100用户 x 1,000,000)
#
# 每批 id 偏移 = batch_index * (源表每用户向量数), 保证 id 不冲突。
# 注意: 扩展后的数据向量值有重复 (同一向量不同 id), 不影响暴力搜索基准测试。
# --------------------------------------------------
run_etl_chain() {
  local src_1w="$1"
  local dst_10w="$2"
  local dst_50w="$3"
  local dst_100w="$4"
  local label="$5"
  local sql

  echo ""
  echo "========================================"
  echo "Step 3: ETL 扩展 ${label} (${src_1w} -> ${dst_10w} -> ${dst_50w} -> ${dst_100w})"
  echo "========================================"

  if ! table_ready "$src_1w" "${EXPECTED_ROWS[10k]}"; then
    echo "[SKIP] ${src_1w} is not ready for ETL (expected ${EXPECTED_ROWS[10k]} rows, got $(table_count "$src_1w"))"
    return
  fi

  if table_ready "$dst_10w" "${EXPECTED_ROWS[100k]}"; then
    echo "[SKIP] ${dst_10w} already has expected rows (${EXPECTED_ROWS[100k]})"
  else
    echo ""
    echo "[ETL] ${src_1w} -> ${dst_10w} (10 batches, id offset 10000)"
    for batch in $(seq 0 9); do
      offset=$((batch * 10000))
      echo "  [ETL] batch ${batch}/9, id offset = ${offset}"
      sql="INSERT INTO ${dst_10w} (user_id, id, embedding) SELECT user_id, id + ${offset}, embedding FROM ${src_1w};"
      echo "  [SQL] ${sql}"
      ${MYSQL_CMD} -D "${DB}" -e "${sql}" 2>&1 || { echo "  [FAIL] ETL batch ${batch} for ${dst_10w}"; LOAD_ERRORS=$((LOAD_ERRORS + 1)); }
    done
    echo "[DONE] ${dst_10w} ETL 完成"
  fi

  if table_ready "$dst_50w" "${EXPECTED_ROWS[500k]}"; then
    echo "[SKIP] ${dst_50w} already has expected rows (${EXPECTED_ROWS[500k]})"
  else
    echo ""
    echo "[ETL] ${dst_10w} -> ${dst_50w} (5 batches, id offset 100000)"
    for batch in $(seq 0 4); do
      offset=$((batch * 100000))
      echo "  [ETL] batch ${batch}/4, id offset = ${offset}"
      sql="INSERT INTO ${dst_50w} (user_id, id, embedding) SELECT user_id, id + ${offset}, embedding FROM ${dst_10w};"
      echo "  [SQL] ${sql}"
      ${MYSQL_CMD} -D "${DB}" -e "${sql}" 2>&1 || { echo "  [FAIL] ETL batch ${batch} for ${dst_50w}"; LOAD_ERRORS=$((LOAD_ERRORS + 1)); }
    done
    echo "[DONE] ${dst_50w} ETL 完成"
  fi

  if table_ready "$dst_100w" "${EXPECTED_ROWS[1m]}"; then
    echo "[SKIP] ${dst_100w} already has expected rows (${EXPECTED_ROWS[1m]})"
  else
    echo ""
    echo "[ETL] ${dst_50w} -> ${dst_100w} (2 batches, id offset 500000)"
    for batch in $(seq 0 1); do
      offset=$((batch * 500000))
      echo "  [ETL] batch ${batch}/1, id offset = ${offset}"
      sql="INSERT INTO ${dst_100w} (user_id, id, embedding) SELECT user_id, id + ${offset}, embedding FROM ${dst_50w};"
      echo "  [SQL] ${sql}"
      ${MYSQL_CMD} -D "${DB}" -e "${sql}" 2>&1 || { echo "  [FAIL] ETL batch ${batch} for ${dst_100w}"; LOAD_ERRORS=$((LOAD_ERRORS + 1)); }
    done
    echo "[DONE] ${dst_100w} ETL 完成"
  fi
}

if [ "$LOAD_MODE" = "etl_only" ]; then
  if [ "$INDEX_MODE" = "pq_on_disk" ]; then
    SIFT_SRC_1W="sift_user_1w_pq"
    SIFT_DST_10W="sift_user_10w_pq"
    SIFT_DST_50W="sift_user_50w_pq"
    SIFT_DST_100W="sift_user_100w_pq"
    COHERE_SRC_1W="cohere_user_1w_pq"
    COHERE_DST_10W="cohere_user_10w_pq"
    COHERE_DST_50W="cohere_user_50w_pq"
    COHERE_DST_100W="cohere_user_100w_pq"
  else
    SIFT_SRC_1W="sift_user_1w"
    SIFT_DST_10W="sift_user_10w"
    SIFT_DST_50W="sift_user_50w"
    SIFT_DST_100W="sift_user_100w"
    COHERE_SRC_1W="cohere_user_1w"
    COHERE_DST_10W="cohere_user_10w"
    COHERE_DST_50W="cohere_user_50w"
    COHERE_DST_100W="cohere_user_100w"
  fi

  if [ "$DIMS" = "all" ] || [ "$DIMS" = "128d" ]; then
    run_etl_chain "$SIFT_SRC_1W" "$SIFT_DST_10W" "$SIFT_DST_50W" "$SIFT_DST_100W" "128D 表"
  fi

  if [ "$DIMS" = "all" ] || [ "$DIMS" = "768d" ]; then
    run_etl_chain "$COHERE_SRC_1W" "$COHERE_DST_10W" "$COHERE_DST_50W" "$COHERE_DST_100W" "768D 表"
  fi
fi

# --------------------------------------------------
# Step 4: 为 pq_on_disk 表补建 ANN 索引
# --------------------------------------------------
if [ "$INDEX_MODE" = "pq_on_disk" ]; then
  echo ""
  echo "========================================"
  echo "Step 4: 创建并构建 ANN 索引"
  echo "========================================"

  build_ann_index() {
    local table="$1"
    local create_sql="$2"

    if ! table_count "$table" >/dev/null 2>&1; then
      echo "[SKIP] ${table} 不存在，跳过索引创建"
      return
    fi

    if index_exists "$table" "idx_embedding_ann"; then
      echo "[SKIP] ${table} 已存在 idx_embedding_ann"
    else
      echo "[SQL] ${create_sql}"
      ${MYSQL_CMD} -D "${DB}" -e "${create_sql}" 2>&1 || { echo "[FAIL] CREATE INDEX on ${table}"; LOAD_ERRORS=$((LOAD_ERRORS + 1)); return; }
    fi

    echo "[SQL] BUILD INDEX idx_embedding_ann ON ${table}"
    ${MYSQL_CMD} -D "${DB}" -e "BUILD INDEX idx_embedding_ann ON ${table}" 2>&1 || { echo "[FAIL] BUILD INDEX on ${table}"; LOAD_ERRORS=$((LOAD_ERRORS + 1)); }
  }

  for scale in ${SCALE_LIST}; do
    if [ "$DIMS" = "all" ] || [ "$DIMS" = "128d" ]; then
      if [ -n "${ANN_INDEX_SQL_128D[$scale]+x}" ]; then
        build_ann_index "${TABLE_MAP_128D_PQ[$scale]}" "${ANN_INDEX_SQL_128D[$scale]}"
      fi
    fi
    if [ "$DIMS" = "all" ] || [ "$DIMS" = "768d" ]; then
      if [ -n "${ANN_INDEX_SQL_768D[$scale]+x}" ]; then
        build_ann_index "${TABLE_MAP_768D_PQ[$scale]}" "${ANN_INDEX_SQL_768D[$scale]}"
      fi
    fi
  done
fi

# --------------------------------------------------
# Step 5: 验证
# --------------------------------------------------
echo ""
echo "========================================"
echo "Step 5: 验证数据量"
echo "========================================"

EXPECTED=()

if [ "$INDEX_MODE" = "pq_on_disk" ]; then
  if [ "$DIMS" = "all" ] || [ "$DIMS" = "128d" ]; then
    EXPECTED+=(
      "sift_user_1w_pq:1000000"
      "sift_user_10w_pq:10000000"
      "sift_user_50w_pq:50000000"
      "sift_user_100w_pq:100000000"
    )
  fi
  if [ "$DIMS" = "all" ] || [ "$DIMS" = "768d" ]; then
    EXPECTED+=(
      "cohere_user_1w_pq:1000000"
      "cohere_user_10w_pq:10000000"
      "cohere_user_50w_pq:50000000"
      "cohere_user_100w_pq:100000000"
    )
  fi
else
  if [ "$DIMS" = "all" ] || [ "$DIMS" = "128d" ]; then
    EXPECTED+=(
      "sift_user_1w:1000000"
      "sift_user_10w:10000000"
      "sift_user_50w:50000000"
      "sift_user_100w:100000000"
    )
  fi
  if [ "$DIMS" = "all" ] || [ "$DIMS" = "768d" ]; then
    EXPECTED+=(
      "cohere_user_1w:1000000"
      "cohere_user_10w:10000000"
      "cohere_user_50w:50000000"
      "cohere_user_100w:100000000"
    )
  fi
fi

for entry in "${EXPECTED[@]}"; do
  table="${entry%%:*}"
  expected="${entry##*:}"
  count=$(${MYSQL_CMD} -D "${DB}" -N -e "SELECT COUNT(*) FROM ${table};" 2>/dev/null || echo "N/A")
  if [ "$count" = "$expected" ]; then
    echo "  [OK]   ${table}: ${count} rows (expected ${expected})"
  else
    echo "  [WARN] ${table}: ${count} rows (expected ${expected})"
  fi
done

echo ""
if [ "$LOAD_ERRORS" -gt 0 ]; then
  echo "完成，但有 ${LOAD_ERRORS} 个表导入过程中出现错误，请检查上面的日志。"
  exit 1
else
  echo "全部完成!"
fi

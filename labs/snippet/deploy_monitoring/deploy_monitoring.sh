#!/usr/bin/env bash
#
# deploy_monitoring.sh
# 一键部署 Node Exporter + Prometheus + Grafana 监控系统 (含 Apache Doris 集群监控)
#
# 执行环境: 172.20.56.74 (root 用户)
# 架构:
#   - 172.20.56.74: Prometheus + Grafana + Node Exporter  (数据目录: /mnt/disk2/hzq)
#   - 172.20.56.83/84/85: Node Exporter                   (数据目录: /mnt/disk1/hzq)
#   - Doris FE/BE: 通过 SHOW FRONTENDS/BACKENDS 自动发现, 采集 /metrics 端点
#
# 用法: bash deploy_monitoring.sh [--force]
#   --force  强制重新部署所有组件 (跳过幂等检查)
#

set -euo pipefail

########################################
# 命令行参数解析
########################################
FORCE_DEPLOY=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --force|-f)
            FORCE_DEPLOY=1
            shift
            ;;
        --help|-h)
            echo "用法: bash deploy_monitoring.sh [--force]"
            echo ""
            echo "选项:"
            echo "  --force, -f   强制重新部署所有组件 (跳过幂等检查)"
            echo "  --help, -h    显示帮助信息"
            exit 0
            ;;
        *)
            echo "未知选项: $1"
            echo "用法: bash deploy_monitoring.sh [--force]"
            exit 1
            ;;
    esac
done

########################################
# 配置区 - 按需修改
########################################

# 版本号
NODE_EXPORTER_VERSION="1.8.2"
PROMETHEUS_VERSION="2.53.3"
GRAFANA_VERSION="11.4.0"

# 机器 IP
MONITOR_HOST="172.20.56.74"              # Prometheus + Grafana + Node Exporter
NODE_EXPORTER_HOSTS=("172.20.56.83" "172.20.56.84" "172.20.56.85")
ALL_NODE_EXPORTER_HOSTS=("${MONITOR_HOST}" "${NODE_EXPORTER_HOSTS[@]}")

# 目录
MONITOR_BASE_DIR="/mnt/disk2/hzq"        # 74 机器的基础目录
REMOTE_BASE_DIR="/mnt/disk1/hzq"          # 83/84/85 机器的基础目录
PACKAGES_DIR="./packages"                  # 本地包缓存目录

# 端口
GRAFANA_PORT=3000
PROMETHEUS_PORT=9090
NODE_EXPORTER_PORT=9100

# Prometheus 配置
SCRAPE_INTERVAL="15s"
EVALUATION_INTERVAL="15s"

# SSH 配置
SSH_USER="root"
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"

# 下载超时
DOWNLOAD_TIMEOUT=300

# 包文件名
NODE_EXPORTER_PKG="node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz"
PROMETHEUS_PKG="prometheus-${PROMETHEUS_VERSION}.linux-amd64.tar.gz"
GRAFANA_PKG="grafana-${GRAFANA_VERSION}.linux-amd64.tar.gz"

# 解压后的目录名
NODE_EXPORTER_DIR="node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64"
PROMETHEUS_DIR="prometheus-${PROMETHEUS_VERSION}.linux-amd64"
GRAFANA_DIR="grafana-v${GRAFANA_VERSION}"

# Doris 集群配置 (通过连接 FE 自动发现所有 FE/BE 节点)
DORIS_FE_HOST="172.20.56.74"             # 任意一个 FE 的 IP
DORIS_FE_QUERY_PORT=9030                  # FE MySQL 协议端口
DORIS_USER="root"                         # Doris 登录用户
DORIS_PASSWORD=""                         # Doris 登录密码 (空则免密)

# 以下由 discover_doris_cluster() 自动填充, 无需手动配置
DORIS_FE_TARGETS=()                       # FE http 端点列表, 如 ("ip:8030" ...)
DORIS_BE_TARGETS=()                       # BE http 端点列表, 如 ("ip:8040" ...)

########################################
# 颜色输出
########################################
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $(date '+%H:%M:%S') $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $(date '+%H:%M:%S') $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $(date '+%H:%M:%S') $*"; }
log_step()  { echo -e "\n${BLUE}========================================${NC}"; echo -e "${BLUE}  $*${NC}"; echo -e "${BLUE}========================================${NC}"; }

########################################
# 工具函数
########################################

# 检查命令是否存在
check_cmd() {
    command -v "$1" &>/dev/null
}

# 在远程机器上执行命令 (单台)
remote_exec() {
    local host="$1"
    shift
    ssh ${SSH_OPTS} "${SSH_USER}@${host}" "$@"
}

# 向远程机器传文件 (单台)
remote_copy() {
    local src="$1"
    local host="$2"
    local dst="$3"
    scp ${SSH_OPTS} "${src}" "${SSH_USER}@${host}:${dst}"
}

# 使用 pssh 在多台机器上执行命令
parallel_exec() {
    local hosts_file="$1"
    shift
    pssh -h "${hosts_file}" -l "${SSH_USER}" -O "StrictHostKeyChecking=no" -O "ConnectTimeout=10" -t 120 -i "$@"
}

# 使用 pscp 向多台机器传文件
parallel_copy() {
    local hosts_file="$1"
    local src="$2"
    local dst="$3"
    pscp.pssh -h "${hosts_file}" -l "${SSH_USER}" -O "StrictHostKeyChecking=no" -O "ConnectTimeout=10" -t 120 "${src}" "${dst}"
}

########################################
# Step 0: 前置检查
########################################
preflight_check() {
    log_step "Step 0: 前置检查"

    # 检查是否以 root 运行（当前 74 机器上）
    if [[ "$(id -u)" -ne 0 ]]; then
        log_warn "当前非 root 用户，systemd 操作可能需要 sudo"
    fi

    # 检查 pssh 是否安装
    if ! check_cmd pssh; then
        log_warn "pssh 未安装, 尝试自动安装..."
        if check_cmd apt-get; then
            apt-get update -qq && apt-get install -y -qq pssh
        elif check_cmd yum; then
            yum install -y -q pssh 2>/dev/null || yum install -y -q python3-pssh 2>/dev/null || {
                log_info "通过 pip 安装 pssh..."
                pip3 install parallel-ssh 2>/dev/null || pip install parallel-ssh 2>/dev/null || {
                    log_error "无法安装 pssh, 请手动安装: yum install pssh 或 pip3 install parallel-ssh"
                    exit 1
                }
            }
        fi
    fi

    # 有些系统上命令名是 parallel-ssh / parallel-scp
    if ! check_cmd pssh; then
        if check_cmd parallel-ssh; then
            log_info "检测到 parallel-ssh, 创建别名..."
            pssh()      { parallel-ssh "$@"; }
            pscp.pssh() { parallel-scp "$@"; }
            export -f pssh pscp.pssh
        else
            log_error "pssh 仍不可用, 请手动安装"
            exit 1
        fi
    fi

    # pscp.pssh 检查 (有些系统叫 pscp, 有些叫 pscp.pssh)
    if ! check_cmd pscp.pssh; then
        if check_cmd pscp; then
            # 确保 pscp 是 parallel-scp 而不是 PuTTY 的 pscp
            if pscp --version 2>&1 | grep -qi "parallel"; then
                pscp.pssh() { pscp "$@"; }
                export -f pscp.pssh
            fi
        fi
        if ! check_cmd pscp.pssh; then
            if check_cmd parallel-scp; then
                pscp.pssh() { parallel-scp "$@"; }
                export -f pscp.pssh
            else
                log_warn "pscp.pssh 不可用，将使用循环 scp 替代"
            fi
        fi
    fi

    # SSH 连通性测试
    log_info "测试 SSH 连通性..."
    local failed=0
    for host in "${ALL_NODE_EXPORTER_HOSTS[@]}"; do
        if ssh ${SSH_OPTS} "${SSH_USER}@${host}" "echo ok" &>/dev/null; then
            log_info "  ✓ ${host} 连接正常"
        else
            log_error "  ✗ ${host} 连接失败"
            failed=1
        fi
    done
    if [[ ${failed} -eq 1 ]]; then
        log_error "部分机器 SSH 不通, 请检查后重试"
        exit 1
    fi

    # 创建包目录
    mkdir -p "${PACKAGES_DIR}"

    log_info "前置检查通过 ✓"
}

########################################
# Step 0.5: 自动发现 Doris 集群节点
########################################
discover_doris_cluster() {
    log_step "Step 0.5: 自动发现 Doris 集群节点"

    # 检查 mysql 客户端
    if ! check_cmd mysql; then
        log_warn "mysql 客户端未安装, 尝试自动安装..."
        if check_cmd apt-get; then
            apt-get update -qq && apt-get install -y -qq mysql-client 2>/dev/null || true
        elif check_cmd yum; then
            yum install -y -q mysql 2>/dev/null || yum install -y -q mariadb 2>/dev/null || true
        fi
    fi

    if ! check_cmd mysql; then
        log_error "mysql 客户端不可用, 无法自动发现 Doris 集群"
        log_error "请安装 mysql 客户端: yum install -y mysql 或 apt-get install -y mysql-client"
        log_error "或者手动在脚本配置区填写 DORIS_FE_TARGETS 和 DORIS_BE_TARGETS"
        exit 1
    fi

    # 构造 mysql 连接命令
    local mysql_cmd="mysql -h ${DORIS_FE_HOST} -P ${DORIS_FE_QUERY_PORT} -u ${DORIS_USER} --batch --skip-column-names"
    if [[ -n "${DORIS_PASSWORD}" ]]; then
        mysql_cmd="${mysql_cmd} -p${DORIS_PASSWORD}"
    fi

    # 测试连接
    log_info "连接 Doris FE: ${DORIS_FE_HOST}:${DORIS_FE_QUERY_PORT} ..."
    if ! ${mysql_cmd} -e "SELECT 1" &>/dev/null; then
        log_error "无法连接 Doris FE (${DORIS_FE_HOST}:${DORIS_FE_QUERY_PORT})"
        log_error "请检查 DORIS_FE_HOST / DORIS_FE_QUERY_PORT / DORIS_USER / DORIS_PASSWORD 配置"
        exit 1
    fi
    log_info "  ✓ Doris FE 连接成功"

    # 获取 FE 列表
    # SHOW FRONTENDS 输出列: Name | Host | EditLogPort | HttpPort | QueryPort | ...
    log_info "查询 SHOW FRONTENDS ..."
    local fe_output
    fe_output=$(${mysql_cmd} -e "SHOW FRONTENDS" 2>/dev/null)
    if [[ -z "${fe_output}" ]]; then
        log_error "SHOW FRONTENDS 返回为空"
        exit 1
    fi

    # 解析 FE: 提取 Host 和 HttpPort 列
    # 先获取列头确定列位置
    local fe_header
    fe_header=$(${mysql_cmd} --column-names -e "SHOW FRONTENDS" 2>/dev/null | head -1)

    # 使用 awk 按列名定位
    while IFS=$'\t' read -r line; do
        local fe_host fe_http_port
        # SHOW FRONTENDS 的列顺序: Name, Host, EditLogPort, HttpPort, QueryPort, RpcPort, ...
        # 用 awk 按 tab 分割取各字段
        fe_host=$(echo "${line}" | awk -F'\t' '{print $2}')
        fe_http_port=$(echo "${line}" | awk -F'\t' '{print $4}')
        if [[ -n "${fe_host}" && -n "${fe_http_port}" && "${fe_http_port}" =~ ^[0-9]+$ ]]; then
            DORIS_FE_TARGETS+=("${fe_host}:${fe_http_port}")
            log_info "  发现 FE: ${fe_host}:${fe_http_port}"
        fi
    done <<< "${fe_output}"

    if [[ ${#DORIS_FE_TARGETS[@]} -eq 0 ]]; then
        log_error "未发现任何 Doris FE 节点"
        exit 1
    fi

    # 获取 BE 列表
    # SHOW BACKENDS 输出列: BackendId | Host | ... | HttpPort | ...
    log_info "查询 SHOW BACKENDS ..."
    local be_output
    be_output=$(${mysql_cmd} -e "SHOW BACKENDS" 2>/dev/null)
    if [[ -z "${be_output}" ]]; then
        log_error "SHOW BACKENDS 返回为空"
        exit 1
    fi

    # 解析 BE: 需要找到 Host 列和 HttpPort 列的位置
    # SHOW BACKENDS 列较多且不同版本可能有差异, 用列头动态定位更安全
    local be_header_line
    be_header_line=$(${mysql_cmd} --column-names -e "SHOW BACKENDS" 2>/dev/null | head -1)

    # 找到 Host 和 HttpPort 的列号
    local host_col=0
    local http_port_col=0
    local col_idx=1
    IFS=$'\t' read -ra be_cols <<< "${be_header_line}"
    for col in "${be_cols[@]}"; do
        # 去除可能的空格
        col=$(echo "${col}" | tr -d ' ')
        if [[ "${col}" == "Host" ]]; then
            host_col=${col_idx}
        elif [[ "${col}" == "HttpPort" ]]; then
            http_port_col=${col_idx}
        fi
        col_idx=$((col_idx + 1))
    done

    if [[ ${host_col} -eq 0 || ${http_port_col} -eq 0 ]]; then
        log_warn "无法从列头定位 BE 的 Host/HttpPort 列, 使用默认位置 (col2/col5)"
        host_col=2
        http_port_col=5
    fi

    while IFS=$'\t' read -r line; do
        local be_host be_http_port
        be_host=$(echo "${line}" | awk -F'\t' -v c="${host_col}" '{print $c}')
        be_http_port=$(echo "${line}" | awk -F'\t' -v c="${http_port_col}" '{print $c}')
        if [[ -n "${be_host}" && -n "${be_http_port}" && "${be_http_port}" =~ ^[0-9]+$ ]]; then
            DORIS_BE_TARGETS+=("${be_host}:${be_http_port}")
            log_info "  发现 BE: ${be_host}:${be_http_port}"
        fi
    done <<< "${be_output}"

    if [[ ${#DORIS_BE_TARGETS[@]} -eq 0 ]]; then
        log_error "未发现任何 Doris BE 节点"
        exit 1
    fi

    echo ""
    log_info "Doris 集群发现完成: ${#DORIS_FE_TARGETS[@]} FE + ${#DORIS_BE_TARGETS[@]} BE ✓"
}

########################################
# Step 1: 下载二进制包
########################################
download_packages() {
    log_step "Step 1: 下载二进制包"

    # Node Exporter 下载
    if [[ ! -f "${PACKAGES_DIR}/${NODE_EXPORTER_PKG}" ]]; then
        log_info "下载 Node Exporter v${NODE_EXPORTER_VERSION}..."
        download_with_fallback \
            "https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/${NODE_EXPORTER_PKG}" \
            "${PACKAGES_DIR}/${NODE_EXPORTER_PKG}"
    else
        log_info "Node Exporter 包已存在, 跳过下载"
    fi

    # Prometheus 下载
    if [[ ! -f "${PACKAGES_DIR}/${PROMETHEUS_PKG}" ]]; then
        log_info "下载 Prometheus v${PROMETHEUS_VERSION}..."
        download_with_fallback \
            "https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VERSION}/${PROMETHEUS_PKG}" \
            "${PACKAGES_DIR}/${PROMETHEUS_PKG}"
    else
        log_info "Prometheus 包已存在, 跳过下载"
    fi

    # Grafana 下载 (OSS 版本)
    if [[ ! -f "${PACKAGES_DIR}/${GRAFANA_PKG}" ]]; then
        log_info "下载 Grafana OSS v${GRAFANA_VERSION}..."
        download_with_fallback \
            "https://dl.grafana.com/oss/release/grafana-${GRAFANA_VERSION}.linux-amd64.tar.gz" \
            "${PACKAGES_DIR}/${GRAFANA_PKG}"
    else
        log_info "Grafana 包已存在, 跳过下载"
    fi

    # 校验文件完整性 (简单检查文件大小)
    for pkg in "${NODE_EXPORTER_PKG}" "${PROMETHEUS_PKG}" "${GRAFANA_PKG}"; do
        local fpath="${PACKAGES_DIR}/${pkg}"
        if [[ ! -f "${fpath}" ]]; then
            log_error "包文件不存在: ${fpath}"
            exit 1
        fi
        local size
        size=$(stat -c%s "${fpath}" 2>/dev/null || stat -f%z "${fpath}" 2>/dev/null)
        if [[ ${size} -lt 1000000 ]]; then
            log_error "包文件可能不完整 (${size} bytes): ${fpath}"
            log_error "请手动下载后放到 ${PACKAGES_DIR}/ 目录下再重新执行"
            exit 1
        fi
        log_info "  ✓ ${pkg} ($(numfmt --to=iec ${size}))"
    done
}

download_with_fallback() {
    local url="$1"
    local output="$2"
    local filename
    filename=$(basename "${output}")

    # 国内 GitHub 镜像列表
    local github_mirrors=(
        "https://mirror.ghproxy.com"
        "https://ghproxy.net"
        "https://gh-proxy.com"
    )

    # 如果是 Grafana 官方地址, 直接下载 (不走 GitHub 镜像)
    if [[ "${url}" == *"dl.grafana.com"* ]]; then
        log_info "  从 Grafana 官方下载: ${url}"
        if curl -fSL --connect-timeout 30 --max-time ${DOWNLOAD_TIMEOUT} \
            --retry 3 --retry-delay 5 \
            -o "${output}" "${url}"; then
            log_info "  下载成功 ✓"
            return 0
        fi
        log_warn "  Grafana 官方下载失败"
    fi

    # 如果是 GitHub 链接, 先尝试镜像
    if [[ "${url}" == *"github.com"* ]]; then
        for mirror in "${github_mirrors[@]}"; do
            local mirror_url="${mirror}/${url}"
            log_info "  尝试镜像: ${mirror}..."
            if curl -fSL --connect-timeout 15 --max-time ${DOWNLOAD_TIMEOUT} \
                --retry 2 --retry-delay 3 \
                -o "${output}" "${mirror_url}" 2>/dev/null; then
                log_info "  通过镜像下载成功 ✓"
                return 0
            fi
            log_warn "  镜像 ${mirror} 失败, 尝试下一个..."
            rm -f "${output}"
        done
    fi

    # 最后直接尝试原始地址
    log_info "  尝试直接下载: ${url}"
    if curl -fSL --connect-timeout 30 --max-time ${DOWNLOAD_TIMEOUT} \
        --retry 3 --retry-delay 5 \
        -o "${output}" "${url}"; then
        log_info "  直接下载成功 ✓"
        return 0
    fi

    log_error "所有下载方式均失败: ${filename}"
    log_error "请手动下载并放到 ${PACKAGES_DIR}/ 目录:"
    log_error "  ${url}"
    rm -f "${output}"
    exit 1
}

########################################
# Step 2: 部署 Node Exporter (4台机器)
########################################
deploy_node_exporter() {
    log_step "Step 2: 部署 Node Exporter 到所有机器"

    # 创建 hosts 文件
    local hosts_file
    hosts_file=$(mktemp /tmp/ne_hosts.XXXXXX)

    # 远程3台机器
    for host in "${NODE_EXPORTER_HOSTS[@]}"; do
        echo "${host}" >> "${hosts_file}"
    done

    # --- 先部署远程3台 (83/84/85) ---
    # 幂等检查: 检查远程机器上 node_exporter 是否已安装且版本匹配
    local remote_needs_deploy=()
    local remote_skip=()

    for host in "${NODE_EXPORTER_HOSTS[@]}"; do
        if [[ ${FORCE_DEPLOY} -eq 1 ]]; then
            remote_needs_deploy+=("${host}")
            continue
        fi
        # 检查远程 binary 是否存在并且版本匹配
        local remote_version=""
        remote_version=$(ssh ${SSH_OPTS} "${SSH_USER}@${host}" \
            "${REMOTE_BASE_DIR}/node_exporter/node_exporter --version 2>&1 | head -1" 2>/dev/null || true)
        if echo "${remote_version}" | grep -q "version ${NODE_EXPORTER_VERSION}"; then
            remote_skip+=("${host}")
        else
            remote_needs_deploy+=("${host}")
        fi
    done

    if [[ ${#remote_skip[@]} -gt 0 ]]; then
        log_info "以下远程机器已安装 Node Exporter v${NODE_EXPORTER_VERSION}, 跳过部署:"
        for h in "${remote_skip[@]}"; do
            log_info "  ✓ ${h} (已是最新版本)"
        done
    fi

    if [[ ${#remote_needs_deploy[@]} -gt 0 ]]; then
        # 重新生成只包含需要部署的机器的 hosts 文件
        local deploy_hosts_file
        deploy_hosts_file=$(mktemp /tmp/ne_deploy_hosts.XXXXXX)
        for host in "${remote_needs_deploy[@]}"; do
            echo "${host}" >> "${deploy_hosts_file}"
        done

        log_info "分发 Node Exporter 到远程机器: ${remote_needs_deploy[*]}..."

        # 先在远程机器上创建目录
        parallel_exec "${deploy_hosts_file}" "mkdir -p ${REMOTE_BASE_DIR}/node_exporter"

        # 分发包
        if check_cmd pscp.pssh; then
            parallel_copy "${deploy_hosts_file}" "${PACKAGES_DIR}/${NODE_EXPORTER_PKG}" "${REMOTE_BASE_DIR}/"
        else
            for host in "${remote_needs_deploy[@]}"; do
                log_info "  scp -> ${host}..."
                remote_copy "${PACKAGES_DIR}/${NODE_EXPORTER_PKG}" "${host}" "${REMOTE_BASE_DIR}/"
            done
        fi

        # 远程解压并安装
        log_info "远程解压并安装 Node Exporter..."
        parallel_exec "${deploy_hosts_file}" "
            cd ${REMOTE_BASE_DIR} && \
            tar xzf ${NODE_EXPORTER_PKG} && \
            cp -f ${NODE_EXPORTER_DIR}/node_exporter ${REMOTE_BASE_DIR}/node_exporter/ && \
            rm -rf ${NODE_EXPORTER_DIR} ${NODE_EXPORTER_PKG}
        "

        rm -f "${deploy_hosts_file}"
    else
        log_info "所有远程机器已安装 Node Exporter v${NODE_EXPORTER_VERSION}, 跳过分发"
    fi

    # 远程创建 systemd 服务 (对所有远程机器 - 确保配置一致, systemd 操作天然幂等)
    log_info "配置远程机器 Node Exporter systemd 服务..."
    parallel_exec "${hosts_file}" "
cat > /etc/systemd/system/node_exporter.service << 'UNIT_EOF'
[Unit]
Description=Prometheus Node Exporter
Documentation=https://prometheus.io/docs/guides/node-exporter/
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=${REMOTE_BASE_DIR}/node_exporter/node_exporter \
    --web.listen-address=:${NODE_EXPORTER_PORT} \
    --collector.systemd \
    --collector.processes
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
UNIT_EOF
systemctl daemon-reload && \
systemctl enable node_exporter && \
systemctl restart node_exporter
"

    # --- 再部署本地 74 ---
    # 幂等检查: 检查本机 node_exporter 是否已安装且版本匹配
    local local_ne_needs_deploy=1
    if [[ ${FORCE_DEPLOY} -eq 0 ]]; then
        local local_ne_version=""
        local_ne_version=$("${MONITOR_BASE_DIR}/node_exporter/node_exporter" --version 2>&1 | head -1 || true)
        if echo "${local_ne_version}" | grep -q "version ${NODE_EXPORTER_VERSION}"; then
            log_info "本机已安装 Node Exporter v${NODE_EXPORTER_VERSION}, 跳过二进制部署"
            local_ne_needs_deploy=0
        fi
    fi

    if [[ ${local_ne_needs_deploy} -eq 1 ]]; then
        log_info "部署 Node Exporter 到本机 (${MONITOR_HOST})..."
        mkdir -p "${MONITOR_BASE_DIR}/node_exporter"
        cd "${MONITOR_BASE_DIR}"
        tar xzf "${OLDPWD}/${PACKAGES_DIR}/${NODE_EXPORTER_PKG}"
        cp -f "${NODE_EXPORTER_DIR}/node_exporter" "${MONITOR_BASE_DIR}/node_exporter/"
        rm -rf "${NODE_EXPORTER_DIR}"
        cd "${OLDPWD}"
    fi

    # 本机 systemd 服务 (始终更新配置, systemd 操作幂等)
    cat > /etc/systemd/system/node_exporter.service << UNIT_EOF
[Unit]
Description=Prometheus Node Exporter
Documentation=https://prometheus.io/docs/guides/node-exporter/
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=${MONITOR_BASE_DIR}/node_exporter/node_exporter \\
    --web.listen-address=:${NODE_EXPORTER_PORT} \\
    --collector.systemd \\
    --collector.processes
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
UNIT_EOF

    systemctl daemon-reload
    systemctl enable node_exporter
    systemctl restart node_exporter

    # 验证
    sleep 2
    log_info "验证 Node Exporter 服务状态..."
    for host in "${ALL_NODE_EXPORTER_HOSTS[@]}"; do
        if curl -sf --connect-timeout 5 "http://${host}:${NODE_EXPORTER_PORT}/metrics" > /dev/null 2>&1; then
            log_info "  ✓ ${host}:${NODE_EXPORTER_PORT} 正常"
        else
            log_warn "  ✗ ${host}:${NODE_EXPORTER_PORT} 暂不可达 (可能需要等待启动)"
        fi
    done

    rm -f "${hosts_file}"
    log_info "Node Exporter 部署完成 ✓"
}

########################################
# Step 3: 部署 Prometheus (74)
########################################
deploy_prometheus() {
    log_step "Step 3: 部署 Prometheus 到 ${MONITOR_HOST}"

    local PROM_HOME="${MONITOR_BASE_DIR}/prometheus"
    local PROM_DATA="${PROM_HOME}/data"

    # 幂等检查: 检查 Prometheus 二进制是否已安装且版本匹配
    local prom_needs_extract=1
    if [[ ${FORCE_DEPLOY} -eq 0 ]] && [[ -x "${PROM_HOME}/prometheus" ]]; then
        local prom_version=""
        prom_version=$("${PROM_HOME}/prometheus" --version 2>&1 | head -1 || true)
        if echo "${prom_version}" | grep -q "version ${PROMETHEUS_VERSION}"; then
            log_info "Prometheus v${PROMETHEUS_VERSION} 已安装, 跳过二进制解压"
            prom_needs_extract=0
        fi
    fi

    mkdir -p "${PROM_HOME}" "${PROM_DATA}"

    if [[ ${prom_needs_extract} -eq 1 ]]; then
        # 解压安装
        log_info "解压 Prometheus..."
        cd "${MONITOR_BASE_DIR}"
        tar xzf "${OLDPWD}/${PACKAGES_DIR}/${PROMETHEUS_PKG}"
        cp -f "${PROMETHEUS_DIR}/prometheus" "${PROM_HOME}/"
        cp -f "${PROMETHEUS_DIR}/promtool" "${PROM_HOME}/"
        # 保留 console 模板
        cp -rf "${PROMETHEUS_DIR}/consoles" "${PROM_HOME}/" 2>/dev/null || true
        cp -rf "${PROMETHEUS_DIR}/console_libraries" "${PROM_HOME}/" 2>/dev/null || true
        rm -rf "${PROMETHEUS_DIR}"
        cd "${OLDPWD}"
    fi

    # 生成 targets 列表
    local targets=""
    for host in "${ALL_NODE_EXPORTER_HOSTS[@]}"; do
        if [[ -n "${targets}" ]]; then
            targets="${targets}, "
        fi
        targets="${targets}'${host}:${NODE_EXPORTER_PORT}'"
    done

    # 生成 Doris FE targets 列表
    local doris_fe_targets=""
    for t in "${DORIS_FE_TARGETS[@]}"; do
        if [[ -n "${doris_fe_targets}" ]]; then
            doris_fe_targets="${doris_fe_targets}, "
        fi
        doris_fe_targets="${doris_fe_targets}'${t}'"
    done

    # 生成 Doris BE targets 列表
    local doris_be_targets=""
    for t in "${DORIS_BE_TARGETS[@]}"; do
        if [[ -n "${doris_be_targets}" ]]; then
            doris_be_targets="${doris_be_targets}, "
        fi
        doris_be_targets="${doris_be_targets}'${t}'"
    done

    # 写入 prometheus.yml 配置
    log_info "生成 Prometheus 配置文件..."
    cat > "${PROM_HOME}/prometheus.yml" << PROM_EOF
# Prometheus 配置文件
# 由 deploy_monitoring.sh 自动生成于 $(date '+%Y-%m-%d %H:%M:%S')

global:
  scrape_interval: ${SCRAPE_INTERVAL}
  evaluation_interval: ${EVALUATION_INTERVAL}
  scrape_timeout: 10s

# Alertmanager 配置 (按需启用)
# alerting:
#   alertmanagers:
#     - static_configs:
#         - targets: []

# 规则文件 (按需添加)
# rule_files:
#   - "rules/*.yml"

scrape_configs:
  # Prometheus 自身监控
  - job_name: "prometheus"
    static_configs:
      - targets: ["localhost:${PROMETHEUS_PORT}"]
        labels:
          instance: "${MONITOR_HOST}"

  # Node Exporter 系统监控
  - job_name: "node_exporter"
    static_configs:
      - targets: [${targets}]

  # Apache Doris 集群监控
  - job_name: "doris_cluster"
    metrics_path: "/metrics"
    static_configs:
      - targets: [${doris_fe_targets}]
        labels:
          group: fe
      - targets: [${doris_be_targets}]
        labels:
          group: be
PROM_EOF

    # 检查配置文件语法
    log_info "校验 Prometheus 配置..."
    if "${PROM_HOME}/promtool" check config "${PROM_HOME}/prometheus.yml"; then
        log_info "  配置文件语法正确 ✓"
    else
        log_error "  配置文件语法错误, 请检查"
        exit 1
    fi

    # 创建 systemd 服务
    log_info "配置 Prometheus systemd 服务..."
    cat > /etc/systemd/system/prometheus.service << UNIT_EOF
[Unit]
Description=Prometheus Monitoring System
Documentation=https://prometheus.io/docs/introduction/overview/
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=${PROM_HOME}/prometheus \\
    --config.file=${PROM_HOME}/prometheus.yml \\
    --storage.tsdb.path=${PROM_DATA} \\
    --storage.tsdb.retention.time=30d \\
    --web.listen-address=:${PROMETHEUS_PORT} \\
    --web.enable-lifecycle \\
    --web.console.templates=${PROM_HOME}/consoles \\
    --web.console.libraries=${PROM_HOME}/console_libraries
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
UNIT_EOF

    systemctl daemon-reload
    systemctl enable prometheus
    systemctl restart prometheus

    # 等待启动
    sleep 3
    log_info "验证 Prometheus 服务..."
    local retries=0
    while [[ ${retries} -lt 10 ]]; do
        if curl -sf "http://localhost:${PROMETHEUS_PORT}/-/ready" > /dev/null 2>&1; then
            log_info "  ✓ Prometheus 已就绪 (http://${MONITOR_HOST}:${PROMETHEUS_PORT})"
            break
        fi
        retries=$((retries + 1))
        sleep 2
    done
    if [[ ${retries} -ge 10 ]]; then
        log_warn "  Prometheus 启动超时, 请检查: journalctl -u prometheus -f"
    fi

    log_info "Prometheus 部署完成 ✓"
}

########################################
# Step 4: 部署 Grafana (74)
########################################
deploy_grafana() {
    log_step "Step 4: 部署 Grafana 到 ${MONITOR_HOST}"

    local GRAFANA_HOME="${MONITOR_BASE_DIR}/grafana"
    local GRAFANA_DATA="${GRAFANA_HOME}/data"

    # 幂等检查: 检查 Grafana 二进制是否已安装且版本匹配
    local grafana_needs_extract=1
    if [[ ${FORCE_DEPLOY} -eq 0 ]] && [[ -x "${GRAFANA_HOME}/bin/grafana" || -x "${GRAFANA_HOME}/bin/grafana-server" ]]; then
        local grafana_version=""
        if [[ -x "${GRAFANA_HOME}/bin/grafana" ]]; then
            grafana_version=$("${GRAFANA_HOME}/bin/grafana" server -v 2>&1 || true)
        elif [[ -x "${GRAFANA_HOME}/bin/grafana-server" ]]; then
            grafana_version=$("${GRAFANA_HOME}/bin/grafana-server" -v 2>&1 || true)
        fi
        if echo "${grafana_version}" | grep -q "${GRAFANA_VERSION}"; then
            log_info "Grafana v${GRAFANA_VERSION} 已安装, 跳过二进制解压"
            grafana_needs_extract=0
        fi
    fi

    mkdir -p "${GRAFANA_HOME}"

    if [[ ${grafana_needs_extract} -eq 1 ]]; then
        # 解压安装
        log_info "解压 Grafana..."
        cd "${MONITOR_BASE_DIR}"
        tar xzf "${OLDPWD}/${PACKAGES_DIR}/${GRAFANA_PKG}"

        # Grafana OSS 解压后目录名可能是 grafana-v11.4.0 或 grafana-11.4.0
        local grafana_extracted=""
        for d in grafana-v${GRAFANA_VERSION} grafana-${GRAFANA_VERSION} grafana; do
            if [[ -d "${d}" ]]; then
                grafana_extracted="${d}"
                break
            fi
        done

        if [[ -z "${grafana_extracted}" ]]; then
            # 尝试找以 grafana 开头的目录
            grafana_extracted=$(ls -d grafana* 2>/dev/null | head -1)
        fi

        if [[ -z "${grafana_extracted}" || ! -d "${grafana_extracted}" ]]; then
            log_error "无法找到 Grafana 解压目录, 请检查包文件"
            ls -la
            exit 1
        fi

        log_info "  Grafana 解压目录: ${grafana_extracted}"

        # 移动文件到目标目录
        if [[ "${grafana_extracted}" != "grafana" || "$(realpath ${grafana_extracted})" != "$(realpath ${GRAFANA_HOME})" ]]; then
            cp -rf "${grafana_extracted}"/* "${GRAFANA_HOME}/"
            rm -rf "${grafana_extracted}"
        fi
        cd "${OLDPWD}"
    fi

    # 创建数据目录
    mkdir -p "${GRAFANA_DATA}" "${GRAFANA_DATA}/plugins" "${GRAFANA_DATA}/log" "${GRAFANA_HOME}/provisioning/datasources" "${GRAFANA_HOME}/provisioning/dashboards"

    # 修改 Grafana 配置
    log_info "生成 Grafana 配置..."
    cat > "${GRAFANA_HOME}/conf/custom.ini" << GRAFANA_EOF
# Grafana 自定义配置
# 由 deploy_monitoring.sh 自动生成于 $(date '+%Y-%m-%d %H:%M:%S')

[paths]
data = ${GRAFANA_DATA}
logs = ${GRAFANA_DATA}/log
plugins = ${GRAFANA_DATA}/plugins
provisioning = ${GRAFANA_HOME}/provisioning

[server]
protocol = http
http_addr = 0.0.0.0
http_port = ${GRAFANA_PORT}
domain = ${MONITOR_HOST}

[database]
type = sqlite3
path = ${GRAFANA_DATA}/grafana.db

[security]
admin_user = admin
admin_password = admin
allow_embedding = true

[users]
allow_sign_up = false

[auth.anonymous]
enabled = false

[log]
mode = file console
level = info

[log.file]
log_rotate = true
max_days = 7
GRAFANA_EOF

    # 自动配置 Prometheus 数据源 (provisioning)
    log_info "配置 Prometheus 数据源 (provisioning)..."
    cat > "${GRAFANA_HOME}/provisioning/datasources/prometheus.yml" << DS_EOF
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://localhost:${PROMETHEUS_PORT}
    isDefault: true
    editable: true
    jsonData:
      timeInterval: "${SCRAPE_INTERVAL}"
      httpMethod: POST
DS_EOF

    # 配置 Dashboard provisioning
    cat > "${GRAFANA_HOME}/provisioning/dashboards/default.yml" << DASH_PROV_EOF
apiVersion: 1

providers:
  - name: 'default'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    editable: true
    updateIntervalSeconds: 30
    options:
      path: ${GRAFANA_HOME}/provisioning/dashboards/json
      foldersFromFilesStructure: false
DASH_PROV_EOF

    mkdir -p "${GRAFANA_HOME}/provisioning/dashboards/json"

    # 创建 systemd 服务
    log_info "配置 Grafana systemd 服务..."
    cat > /etc/systemd/system/grafana.service << UNIT_EOF
[Unit]
Description=Grafana Dashboard
Documentation=https://grafana.com/docs/grafana/latest/
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=${GRAFANA_HOME}/bin/grafana server \\
    --config=${GRAFANA_HOME}/conf/custom.ini \\
    --homepath=${GRAFANA_HOME}
WorkingDirectory=${GRAFANA_HOME}
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
UNIT_EOF

    systemctl daemon-reload
    systemctl enable grafana
    systemctl restart grafana

    # 等待启动
    sleep 5
    log_info "验证 Grafana 服务..."
    local retries=0
    while [[ ${retries} -lt 15 ]]; do
        if curl -sf "http://localhost:${GRAFANA_PORT}/api/health" > /dev/null 2>&1; then
            log_info "  ✓ Grafana 已就绪 (http://${MONITOR_HOST}:${GRAFANA_PORT})"
            break
        fi
        retries=$((retries + 1))
        sleep 2
    done
    if [[ ${retries} -ge 15 ]]; then
        log_warn "  Grafana 启动超时, 请检查: journalctl -u grafana -f"
    fi

    log_info "Grafana 部署完成 ✓"
}

########################################
# Step 5: 导入 Grafana Dashboard
########################################
import_dashboard() {
    log_step "Step 5: 导入 Grafana Dashboard"

    local GRAFANA_URL="http://localhost:${GRAFANA_PORT}"
    local GRAFANA_AUTH="admin:admin"
    local DASHBOARD_JSON_DIR="${MONITOR_BASE_DIR}/grafana/provisioning/dashboards/json"

    # 等待 Grafana API 可用
    log_info "等待 Grafana API 就绪..."
    local retries=0
    while [[ ${retries} -lt 20 ]]; do
        if curl -sf -u "${GRAFANA_AUTH}" "${GRAFANA_URL}/api/datasources" > /dev/null 2>&1; then
            break
        fi
        retries=$((retries + 1))
        sleep 3
    done
    if [[ ${retries} -ge 20 ]]; then
        log_warn "Grafana API 不可用, 跳过 Dashboard 导入"
        log_warn "你可以稍后手动导入 Dashboard ID: 1860"
        return 0
    fi

    # 验证数据源
    log_info "验证 Prometheus 数据源..."
    local ds_count
    ds_count=$(curl -sf -u "${GRAFANA_AUTH}" "${GRAFANA_URL}/api/datasources" | grep -c "Prometheus" || true)
    if [[ ${ds_count} -gt 0 ]]; then
        log_info "  ✓ Prometheus 数据源已配置"
    else
        log_warn "  数据源未自动配置, 通过 API 手动添加..."
        curl -sf -u "${GRAFANA_AUTH}" \
            -H "Content-Type: application/json" \
            -X POST "${GRAFANA_URL}/api/datasources" \
            -d "{
                \"name\": \"Prometheus\",
                \"type\": \"prometheus\",
                \"url\": \"http://localhost:${PROMETHEUS_PORT}\",
                \"access\": \"proxy\",
                \"isDefault\": true
            }" > /dev/null 2>&1 || true
    fi

    # 通过 Grafana API 获取 Dashboard JSON (Dashboard ID: 1860 - Node Exporter Full)
    log_info "下载 Node Exporter Full Dashboard (ID: 1860)..."
    local dashboard_file="${DASHBOARD_JSON_DIR}/node-exporter-full.json"
    local dashboard_tmp="${DASHBOARD_JSON_DIR}/.node-exporter-full.tmp.json"

    # 幂等检查: 如果 dashboard JSON 已存在且非空, 跳过下载
    if [[ ${FORCE_DEPLOY} -eq 0 ]] && [[ -s "${dashboard_file}" ]]; then
        local existing_size
        existing_size=$(stat -c%s "${dashboard_file}" 2>/dev/null || echo 0)
        if [[ ${existing_size} -gt 1000 ]]; then
            log_info "  Node Exporter Dashboard JSON 已存在 ($(numfmt --to=iec ${existing_size})), 跳过下载"
        else
            # 文件太小, 可能是损坏的, 重新下载
            log_warn "  Dashboard 文件过小, 将重新下载"
            rm -f "${dashboard_file}"
        fi
    fi

    if [[ ! -s "${dashboard_file}" ]] || [[ ${FORCE_DEPLOY} -eq 1 ]]; then
    # 尝试从 Grafana.com API 下载 dashboard JSON 到文件
    local download_ok=0
    if curl -sf --connect-timeout 15 --max-time 60 \
        -o "${dashboard_tmp}" \
        "https://grafana.com/api/dashboards/1860/revisions/37/download" 2>/dev/null; then
        # 检查文件有效性
        if [[ -s "${dashboard_tmp}" ]] && head -1 "${dashboard_tmp}" | grep -q '{'; then
            local fsize
            fsize=$(stat -c%s "${dashboard_tmp}" 2>/dev/null || echo 0)
            if [[ ${fsize} -gt 1000 ]]; then
                download_ok=1
            fi
        fi
    fi

    if [[ ${download_ok} -eq 1 ]]; then
        log_info "  Dashboard JSON 下载成功"

        # 用 Python 处理 JSON: 修正 datasource 引用，设置 uid/title
        if check_cmd python3; then
            python3 -c "
import json, sys

with open('${dashboard_tmp}', 'r') as f:
    dashboard = json.load(f)

def fix_datasource(obj):
    if isinstance(obj, dict):
        if 'datasource' in obj:
            ds = obj['datasource']
            if isinstance(ds, str):
                obj['datasource'] = {'type': 'prometheus', 'uid': ''}
            elif isinstance(ds, dict):
                ds.setdefault('type', 'prometheus')
        for v in obj.values():
            fix_datasource(v)
    elif isinstance(obj, list):
        for item in obj:
            fix_datasource(item)

fix_datasource(dashboard)
dashboard['id'] = None
dashboard['uid'] = 'node-exporter-full'
dashboard['title'] = 'Node Exporter Full'

with open('${dashboard_file}', 'w') as f:
    json.dump(dashboard, f, indent=2)
" 2>/dev/null || cp -f "${dashboard_tmp}" "${dashboard_file}"
        else
            cp -f "${dashboard_tmp}" "${dashboard_file}"
        fi

        rm -f "${dashboard_tmp}"

        # 如果处理失败则回退原始文件
        if [[ ! -s "${dashboard_file}" ]]; then
            log_warn "  Python 处理失败, 使用原始 JSON"
            cp -f "${dashboard_tmp}" "${dashboard_file}" 2>/dev/null || true
        fi

        log_info "  Dashboard 已写入 provisioning 目录"

        log_info "  ✓ Node Exporter Dashboard 准备就绪"
    else
        rm -f "${dashboard_tmp}"
        log_warn "  无法从 grafana.com 下载 Dashboard"
        log_warn "  请在 Grafana UI 中手动导入: Dashboards -> Import -> 输入 ID: 1860"

        # 写一个简化版 dashboard 作为替代
        log_info "  生成简化版 Node Exporter Dashboard..."
        cat > "${dashboard_file}" << 'BASIC_DASH_EOF'
{
  "id": null,
  "uid": "node-exporter-basic",
  "title": "Node Exporter Basic",
  "tags": ["node-exporter", "prometheus"],
  "timezone": "browser",
  "schemaVersion": 39,
  "version": 1,
  "refresh": "30s",
  "time": { "from": "now-1h", "to": "now" },
  "panels": [
    {
      "title": "CPU Usage",
      "type": "timeseries",
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 0 },
      "datasource": { "type": "prometheus", "uid": "" },
      "targets": [{
        "expr": "100 - (avg by(instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)",
        "legendFormat": "{{instance}}"
      }],
      "fieldConfig": { "defaults": { "unit": "percent", "min": 0, "max": 100 } }
    },
    {
      "title": "Memory Usage",
      "type": "timeseries",
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 0 },
      "datasource": { "type": "prometheus", "uid": "" },
      "targets": [{
        "expr": "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100",
        "legendFormat": "{{instance}}"
      }],
      "fieldConfig": { "defaults": { "unit": "percent", "min": 0, "max": 100 } }
    },
    {
      "title": "Disk Usage",
      "type": "timeseries",
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 8 },
      "datasource": { "type": "prometheus", "uid": "" },
      "targets": [{
        "expr": "(1 - node_filesystem_avail_bytes{mountpoint=\"/\",fstype!=\"tmpfs\"} / node_filesystem_size_bytes{mountpoint=\"/\",fstype!=\"tmpfs\"}) * 100",
        "legendFormat": "{{instance}}"
      }],
      "fieldConfig": { "defaults": { "unit": "percent", "min": 0, "max": 100 } }
    },
    {
      "title": "Network Traffic",
      "type": "timeseries",
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 8 },
      "datasource": { "type": "prometheus", "uid": "" },
      "targets": [
        {
          "expr": "rate(node_network_receive_bytes_total{device!~\"lo|veth.*|docker.*|br.*\"}[5m]) * 8",
          "legendFormat": "{{instance}} - {{device}} RX"
        },
        {
          "expr": "rate(node_network_transmit_bytes_total{device!~\"lo|veth.*|docker.*|br.*\"}[5m]) * 8",
          "legendFormat": "{{instance}} - {{device}} TX"
        }
      ],
      "fieldConfig": { "defaults": { "unit": "bps" } }
    },
    {
      "title": "System Load (1m)",
      "type": "timeseries",
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 16 },
      "datasource": { "type": "prometheus", "uid": "" },
      "targets": [{
        "expr": "node_load1",
        "legendFormat": "{{instance}}"
      }]
    },
    {
      "title": "Uptime",
      "type": "stat",
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 16 },
      "datasource": { "type": "prometheus", "uid": "" },
      "targets": [{
        "expr": "time() - node_boot_time_seconds",
        "legendFormat": "{{instance}}"
      }],
      "fieldConfig": { "defaults": { "unit": "s" } }
    }
  ]
}
BASIC_DASH_EOF

        log_info "  ✓ 简化版 Dashboard 准备就绪"
    fi

    fi  # 结束 Node Exporter Dashboard 幂等检查

    # --- Doris Overview Dashboard (ID: 9734) ---
    log_info ""
    log_info "下载 Doris Overview Dashboard (ID: 9734)..."
    local doris_dashboard_file="${DASHBOARD_JSON_DIR}/doris-overview.json"
    local doris_dashboard_tmp="${DASHBOARD_JSON_DIR}/.doris-overview.tmp.json"

    # 幂等检查: 如果 Doris Dashboard JSON 已存在且非空, 跳过下载
    local doris_dash_skip=0
    if [[ ${FORCE_DEPLOY} -eq 0 ]] && [[ -s "${doris_dashboard_file}" ]]; then
        local doris_existing_size
        doris_existing_size=$(stat -c%s "${doris_dashboard_file}" 2>/dev/null || echo 0)
        if [[ ${doris_existing_size} -gt 1000 ]]; then
            log_info "  Doris Dashboard JSON 已存在 ($(numfmt --to=iec ${doris_existing_size})), 跳过下载"
            doris_dash_skip=1
        fi
    fi

    if [[ ${doris_dash_skip} -eq 0 ]]; then
    local doris_download_ok=0
    if curl -sf --connect-timeout 15 --max-time 60 \
        -o "${doris_dashboard_tmp}" \
        "https://grafana.com/api/dashboards/9734/revisions/5/download" 2>/dev/null; then
        if [[ -s "${doris_dashboard_tmp}" ]] && head -1 "${doris_dashboard_tmp}" | grep -q '{'; then
            local doris_fsize
            doris_fsize=$(stat -c%s "${doris_dashboard_tmp}" 2>/dev/null || echo 0)
            if [[ ${doris_fsize} -gt 1000 ]]; then
                doris_download_ok=1
            fi
        fi
    fi

    if [[ ${doris_download_ok} -eq 1 ]]; then
        log_info "  Doris Dashboard JSON 下载成功"

        if check_cmd python3; then
            python3 -c "
import json

with open('${doris_dashboard_tmp}', 'r') as f:
    dashboard = json.load(f)

def fix_datasource(obj):
    if isinstance(obj, dict):
        if 'datasource' in obj:
            ds = obj['datasource']
            if isinstance(ds, str):
                obj['datasource'] = {'type': 'prometheus', 'uid': ''}
            elif isinstance(ds, dict):
                ds.setdefault('type', 'prometheus')
        for v in obj.values():
            fix_datasource(v)
    elif isinstance(obj, list):
        for item in obj:
            fix_datasource(item)

fix_datasource(dashboard)
dashboard['id'] = None
dashboard['uid'] = 'doris-overview'
dashboard['title'] = 'Doris Overview'

with open('${doris_dashboard_file}', 'w') as f:
    json.dump(dashboard, f, indent=2)
" 2>/dev/null || cp -f "${doris_dashboard_tmp}" "${doris_dashboard_file}"
        else
            cp -f "${doris_dashboard_tmp}" "${doris_dashboard_file}"
        fi

        rm -f "${doris_dashboard_tmp}"

        if [[ ! -s "${doris_dashboard_file}" ]]; then
            log_warn "  Python 处理失败, 使用原始 JSON"
            cp -f "${doris_dashboard_tmp}" "${doris_dashboard_file}" 2>/dev/null || true
        fi

        log_info "  Doris Dashboard 已写入 provisioning 目录"
    else
        rm -f "${doris_dashboard_tmp}"
        log_warn "  无法从 grafana.com 下载 Doris Dashboard"
        log_warn "  请在 Grafana UI 中手动导入: Dashboards -> Import -> 输入 ID: 9734"
    fi

    fi  # 结束 Doris Dashboard 幂等检查

    # 最终重启 Grafana 使所有 Dashboard provisioning 生效
    log_info "重启 Grafana 加载所有 Dashboard..."
    systemctl restart grafana
    sleep 3
    log_info "Dashboard 导入完成 ✓"
}

########################################
# Step 6: 最终验证与信息输出
########################################
final_verify() {
    log_step "Step 6: 最终验证"

    echo ""
    log_info "======== 服务状态汇总 ========"
    echo ""

    # Node Exporter 状态
    log_info "--- Node Exporter ---"
    for host in "${ALL_NODE_EXPORTER_HOSTS[@]}"; do
        local metrics_ok="✗"
        if curl -sf --connect-timeout 5 "http://${host}:${NODE_EXPORTER_PORT}/metrics" > /dev/null 2>&1; then
            metrics_ok="✓"
        fi
        printf "  %-18s http://%s:%s/metrics  [%s]\n" "${host}" "${host}" "${NODE_EXPORTER_PORT}" "${metrics_ok}"
    done

    echo ""

    # Doris FE/BE 状态
    log_info "--- Doris FE ---"
    for target in "${DORIS_FE_TARGETS[@]}"; do
        local fe_ok="✗"
        if curl -sf --connect-timeout 5 "http://${target}/metrics" > /dev/null 2>&1; then
            fe_ok="✓"
        fi
        printf "  %-18s http://%s/metrics     [%s]\n" "${target}" "${target}" "${fe_ok}"
    done

    echo ""

    log_info "--- Doris BE ---"
    for target in "${DORIS_BE_TARGETS[@]}"; do
        local be_ok="✗"
        if curl -sf --connect-timeout 5 "http://${target}/metrics" > /dev/null 2>&1; then
            be_ok="✓"
        fi
        printf "  %-18s http://%s/metrics     [%s]\n" "${target}" "${target}" "${be_ok}"
    done

    echo ""

    # Prometheus 状态
    log_info "--- Prometheus ---"
    local prom_status="✗"
    if curl -sf "http://localhost:${PROMETHEUS_PORT}/-/ready" > /dev/null 2>&1; then
        prom_status="✓"
    fi
    printf "  %-18s http://%s:%s           [%s]\n" "${MONITOR_HOST}" "${MONITOR_HOST}" "${PROMETHEUS_PORT}" "${prom_status}"

    # 检查 targets 状态
    local targets_info
    targets_info=$(curl -sf "http://localhost:${PROMETHEUS_PORT}/api/v1/targets" 2>/dev/null || true)
    if [[ -n "${targets_info}" ]]; then
        local active_targets
        active_targets=$(echo "${targets_info}" | grep -o '"health":"up"' | wc -l)
        log_info "  活跃 targets: ${active_targets}"
    fi

    echo ""

    # Grafana 状态
    log_info "--- Grafana ---"
    local grafana_status="✗"
    if curl -sf "http://localhost:${GRAFANA_PORT}/api/health" > /dev/null 2>&1; then
        grafana_status="✓"
    fi
    printf "  %-18s http://%s:%s           [%s]\n" "${MONITOR_HOST}" "${MONITOR_HOST}" "${GRAFANA_PORT}" "${grafana_status}"

    echo ""
    echo -e "${GREEN}================================================${NC}"
    echo -e "${GREEN}  部署完成!${NC}"
    echo -e "${GREEN}================================================${NC}"
    echo ""
    echo "  访问信息:"
    echo "  ─────────────────────────────────────────────"
    echo "  Grafana:    http://${MONITOR_HOST}:${GRAFANA_PORT}"
    echo "  用户名:     admin"
    echo "  密码:       admin (首次登录请修改)"
    echo ""
    echo "  Prometheus: http://${MONITOR_HOST}:${PROMETHEUS_PORT}"
    echo "  ─────────────────────────────────────────────"
    echo ""
    echo "  Prometheus 配置文件: ${MONITOR_BASE_DIR}/prometheus/prometheus.yml"
    echo "  Prometheus 数据目录: ${MONITOR_BASE_DIR}/prometheus/data"
    echo "  Grafana 配置文件:    ${MONITOR_BASE_DIR}/grafana/conf/custom.ini"
    echo "  Grafana 数据目录:    ${MONITOR_BASE_DIR}/grafana/data"
    echo ""
    echo "  服务管理:"
    echo "  ─────────────────────────────────────────────"
    echo "  systemctl {start|stop|restart|status} node_exporter"
    echo "  systemctl {start|stop|restart|status} prometheus"
    echo "  systemctl {start|stop|restart|status} grafana"
    echo ""
    echo "  日志查看:"
    echo "  ─────────────────────────────────────────────"
    echo "  journalctl -u node_exporter -f"
    echo "  journalctl -u prometheus -f"
    echo "  journalctl -u grafana -f"
    echo ""
}

########################################
# 主流程
########################################
main() {
    log_step "开始部署监控系统"
    log_info "部署时间: $(date '+%Y-%m-%d %H:%M:%S')"
    log_info "执行用户: $(whoami)"
    log_info "执行机器: $(hostname) (${MONITOR_HOST})"
    if [[ ${FORCE_DEPLOY} -eq 1 ]]; then
        log_warn "强制模式已启用 (--force), 将跳过所有幂等检查"
    fi

    # 记录脚本所在目录
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cd "${SCRIPT_DIR}"

    preflight_check
    discover_doris_cluster
    download_packages
    deploy_node_exporter
    deploy_prometheus
    deploy_grafana
    import_dashboard
    final_verify
}

# 执行
main "$@"

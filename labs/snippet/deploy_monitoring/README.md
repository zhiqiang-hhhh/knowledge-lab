# Node Exporter + Prometheus + Grafana + Doris 一键部署

基于 shell 脚本 + parallel-ssh 的二进制自动化部署方案，适用于无外网 Docker 环境的内网机器。
含 Apache Doris 集群自动发现与监控面板。

## 架构

```
                   +--------------------------+
                   |   172.20.56.74           |
                   |   /mnt/disk2/hzq         |
                   |                          |
                   |  +--------+  +--------+  |
  浏览器 --------->|  |Grafana |  |Promethe|  |
  :3000            |  | :3000  |  |us :9090|  |
                   |  +--------+  +---+----+  |
                   |  +-------------+ |       |
                   |  |Node Exporter| |       |
                   |  |   :9100     | |       |
                   |  +-------------+ |       |
                   +------------------+-------+
                                      |
              +-----------------------+ scrape (每15s)
              |                       |
     +--------+--------+    +--------+--------+
     | Node Exporter    |    | Doris 集群       |
     | 系统指标采集      |    | 应用指标采集      |
     +--------+---------+    +--------+---------+
              |                       |
   +----------+----------+   +--------+--------+
   |          |          |   |                  |
  .83:9100  .84:9100  .85:9100  FE:8030    BE:8040
                              /metrics     /metrics
                           (自动发现)    (自动发现)
```

Prometheus 同时采集两类数据：
- **Node Exporter** (job: `node_exporter`) -- 操作系统级别指标 (CPU/Memory/Disk/Network)
- **Doris** (job: `doris_cluster`) -- 数据库级别指标 (Query/Compaction/JVM/Tablet)

Doris FE/BE 的地址和端口通过连接 FE MySQL 端口执行 `SHOW FRONTENDS` / `SHOW BACKENDS` **自动发现**，无需手动填写。

## 组件版本

| 组件 | 版本 | 说明 |
|---|---|---|
| Node Exporter | v1.8.2 | 系统指标采集 |
| Prometheus | v2.53.3 | 指标存储与查询 |
| Grafana OSS | v11.4.0 | 可视化面板 |
| Apache Doris | (已有集群) | FE/BE 原生暴露 Prometheus 兼容的 `/metrics` 端点 |

## 机器清单

| 机器 | 部署组件 | 安装目录 | 端口 |
|---|---|---|---|
| 172.20.56.74 | Prometheus + Grafana + Node Exporter | `/mnt/disk2/hzq` | 9090 / 3000 / 9100 |
| 172.20.56.83 | Node Exporter | `/mnt/disk1/hzq` | 9100 |
| 172.20.56.84 | Node Exporter | `/mnt/disk1/hzq` | 9100 |
| 172.20.56.85 | Node Exporter | `/mnt/disk1/hzq` | 9100 |
| Doris FE | (自动发现) | -- | 默认 8030 |
| Doris BE | (自动发现) | -- | 默认 8040 |

## 前置条件

- 74 机器已配置到 83/84/85 的 **root 免密 SSH**
- 74 机器有 **sudo/root** 权限（注册 systemd 服务需要）
- 所有机器为 **linux amd64** 架构
- 端口 3000 / 9090 / 9100 未被占用
- 74 机器上有 **mysql 客户端** 且能连接到 Doris FE（脚本会自动尝试安装 mysql 客户端）
- Doris FE MySQL 端口（默认 9030）从 74 机器可达

## 使用方法

### 1. 将本目录拷贝到 74 机器

```bash
scp -r deploy_monitoring root@172.20.56.74:/mnt/disk2/hzq/
```

### 2. 在 74 上执行脚本

```bash
ssh root@172.20.56.74
cd /mnt/disk2/hzq/deploy_monitoring
bash deploy_monitoring.sh
```

**重复执行 (幂等)**：脚本支持多次执行，会自动跳过已完成的步骤：
- 已安装且版本匹配的 Node Exporter / Prometheus / Grafana 二进制 → 跳过解压
- 已存在的 Dashboard JSON 文件 → 跳过下载
- 配置文件和 systemd 服务始终重新生成（确保配置一致性）

如需强制重新部署所有组件（忽略幂等检查），使用 `--force` 参数：

```bash
bash deploy_monitoring.sh --force
```

### 3. 脚本执行流程

脚本全自动完成以下步骤：

| 步骤 | 内容 |
|---|---|
| **Step 0** | 前置检查：自动安装 pssh（如缺失）、SSH 连通性测试、创建目录 |
| **Step 0.5** | Doris 集群自动发现：连接 FE 执行 `SHOW FRONTENDS` / `SHOW BACKENDS`，解析所有 FE/BE 的 IP 和 HTTP 端口 |
| **Step 1** | 下载二进制包：Node Exporter / Prometheus / Grafana（优先国内 GitHub 镜像，Grafana 走官方 CDN `dl.grafana.com`），已有包则跳过 |
| **Step 2** | 部署 Node Exporter 到全部 4 台机器（pssh 批量分发到 83/84/85 + 本机 74），注册 systemd 服务并启动 |
| **Step 3** | 部署 Prometheus 到 74，自动生成 `prometheus.yml`（包含 node_exporter targets + Doris FE/BE targets），注册 systemd 服务并启动 |
| **Step 4** | 部署 Grafana OSS 到 74，生成 `custom.ini` + provisioning 自动配置 Prometheus 数据源，注册 systemd 服务并启动 |
| **Step 5** | 导入 Dashboard：Node Exporter Full (ID: 1860) + **Doris Overview (ID: 9734)**，下载失败则生成简化版 |
| **Step 6** | 最终验证：逐一检查 Node Exporter / Doris FE / Doris BE / Prometheus / Grafana 端口可达性，输出访问信息 |

### 4. Doris 连接配置

脚本配置区的 Doris 相关变量（按实际情况修改）：

```bash
DORIS_FE_HOST="172.20.56.74"    # 任意一个 FE 的 IP
DORIS_FE_QUERY_PORT=9030         # FE MySQL 协议端口
DORIS_USER="root"                # Doris 登录用户
DORIS_PASSWORD=""                # Doris 登录密码 (空则免密)
```

脚本会自动通过 `SHOW FRONTENDS` / `SHOW BACKENDS` 获取所有 FE/BE 节点的 IP 和 HTTP 端口，无需手动列举。

### 5. 手动提前下载包（可选）

如果机器完全无法访问外网，可以手动下载以下 3 个包，放到脚本同目录的 `packages/` 下：

```
deploy_monitoring/
├── deploy_monitoring.sh
└── packages/
    ├── node_exporter-1.8.2.linux-amd64.tar.gz
    ├── prometheus-2.53.3.linux-amd64.tar.gz
    └── grafana-11.4.0.linux-amd64.tar.gz
```

下载地址：

- Node Exporter: https://github.com/prometheus/node_exporter/releases/download/v1.8.2/node_exporter-1.8.2.linux-amd64.tar.gz
- Prometheus: https://github.com/prometheus/prometheus/releases/download/v2.53.3/prometheus-2.53.3.linux-amd64.tar.gz
- Grafana OSS: https://dl.grafana.com/oss/release/grafana-11.4.0.linux-amd64.tar.gz

脚本检测到 `packages/` 目录下已有对应文件时，会自动跳过下载步骤。

## 部署完成后

### 访问地址

```
Grafana:    http://172.20.56.74:3000    (用户名: admin / 密码: admin，首次登录需修改密码)
Prometheus: http://172.20.56.74:9090
```

### Grafana Dashboard

部署完成后 Grafana 中预装了两个 Dashboard：

| Dashboard | Grafana ID | 说明 |
|---|---|---|
| **Node Exporter Full** | 1860 | 系统监控：CPU / 内存 / 磁盘 / 网络 / 负载等全量指标 |
| **Doris Overview** | 9734 | Doris 监控：集群概览 / 查询统计 / FE JVM / BE 任务等 |

Doris Overview Dashboard 包含以下面板行：

| 面板行 | 内容 |
|---|---|
| Overview | 所有 Doris 集群的总览 |
| Cluster Overview | 选中集群的汇总信息 |
| Query Statistic | 查询 QPS、延迟分布、错误率 |
| FE JVM | JVM 堆内存、GC、线程数 |
| BE | Compaction Score、磁盘使用、内存 |
| BE Task | BE 后台任务信息 |

> Dashboard 中的 `job` 变量对应 Prometheus 中的 `job_name: "doris_cluster"`，`group` label 区分 FE (`group=fe`) 和 BE (`group=be`)。

### 目录结构

```
# 74 机器 (/mnt/disk2/hzq)
├── node_exporter/
│   └── node_exporter                    # 二进制文件
├── prometheus/
│   ├── prometheus                       # 二进制文件
│   ├── promtool                         # 配置校验工具
│   ├── prometheus.yml                   # 采集配置（含 node_exporter + doris_cluster）
│   ├── consoles/                        # 内置 console 模板
│   ├── console_libraries/
│   └── data/                            # TSDB 时序数据（默认保留 30 天）
└── grafana/
    ├── bin/grafana                       # 二进制文件
    ├── conf/
    │   ├── defaults.ini                  # 默认配置（勿改）
    │   └── custom.ini                   # 自定义配置（改这个）
    ├── data/                             # SQLite DB + 日志 + 插件
    │   ├── grafana.db
    │   └── log/
    └── provisioning/
        ├── datasources/prometheus.yml   # 自动配置的 Prometheus 数据源
        └── dashboards/
            ├── default.yml              # Dashboard provisioning 配置
            └── json/
                ├── node-exporter-full.json  # Node Exporter Dashboard
                └── doris-overview.json      # Doris Overview Dashboard

# 83/84/85 机器 (/mnt/disk1/hzq)
└── node_exporter/
    └── node_exporter                    # 二进制文件
```

### 服务管理

所有组件通过 systemd 管理，支持开机自启。

```bash
# 在 74 上
systemctl {start|stop|restart|status} prometheus
systemctl {start|stop|restart|status} grafana
systemctl {start|stop|restart|status} node_exporter

# 在 83/84/85 上（单台）
ssh root@172.20.56.83 "systemctl restart node_exporter"

# 批量操作（在 74 上执行）
echo -e "172.20.56.83\n172.20.56.84\n172.20.56.85" > /tmp/ne_hosts
pssh -h /tmp/ne_hosts -l root "systemctl restart node_exporter"
```

### 查看日志

```bash
journalctl -u prometheus -f
journalctl -u grafana -f
journalctl -u node_exporter -f

# 远程查看
ssh root@172.20.56.83 "journalctl -u node_exporter -f"
```

## 生成的 Prometheus 配置示例

脚本自动生成的 `prometheus.yml` 结构如下（Doris targets 由自动发现填入）：

```yaml
scrape_configs:
  # Prometheus 自身监控
  - job_name: "prometheus"
    static_configs:
      - targets: ["localhost:9090"]

  # Node Exporter 系统监控
  - job_name: "node_exporter"
    static_configs:
      - targets: ['172.20.56.74:9100', '172.20.56.83:9100', '172.20.56.84:9100', '172.20.56.85:9100']

  # Apache Doris 集群监控
  - job_name: "doris_cluster"
    metrics_path: "/metrics"
    static_configs:
      - targets: ['fe_ip1:8030', 'fe_ip2:8030']    # 自动从 SHOW FRONTENDS 获取
        labels:
          group: fe
      - targets: ['be_ip1:8040', 'be_ip2:8040']    # 自动从 SHOW BACKENDS 获取
        labels:
          group: be
```

## Doris 关键监控指标

### FE 关键指标

| 指标 | 含义 | 关注点 |
|---|---|---|
| `doris_fe_connection_total` | MySQL 连接数 | 接近上限时需告警 |
| `doris_fe_qps` | 查询 QPS | 业务负载基线 |
| `doris_fe_query_latency_ms{quantile="0.99"}` | P99 查询延迟 | 超过阈值需排查 |
| `doris_fe_query_err_rate` | 查询错误率 | 非零需关注 |
| `doris_fe_max_tablet_compaction_score` | 最大 Compaction 分数 | 过高表示 BE 压力大 |
| `doris_fe_scheduled_tablet_num` | 调度中的 Tablet 数 | 修复/均衡进度 |
| `jvm_heap_size_bytes{type="used"}` | FE JVM 堆使用 | 接近 max 需调整 |

### BE 关键指标

| 指标 | 含义 | 关注点 |
|---|---|---|
| `doris_be_compaction_bytes_total` | Compaction 吞吐 | 持续为 0 可能异常 |
| `doris_be_tablet_cumulative_max_compaction_score` | Compaction 分数 | 过高表示积压 |
| `doris_be_disks_avail_capacity` | 可用磁盘空间 | 低于 10% 需扩容 |
| `doris_be_memory_allocated_bytes` | 进程内存 | 接近物理内存上限需关注 |
| `doris_be_fragment_instance_count` | 活跃查询 Fragment 数 | 持续增长可能有慢查询 |
| `doris_be_query_scan_bytes_per_second` | 扫描吞吐 | 磁盘 IO 瓶颈参考 |
| `doris_be_process_fd_num_used` | 文件描述符使用数 | 接近系统 ulimit 需调整 |

## 日常运维

### 添加新的 Node Exporter 监控机器

1. 在新机器上部署 Node Exporter（参考脚本中 `deploy_node_exporter` 函数）
2. 编辑 Prometheus 配置，添加 target：

```bash
vim /mnt/disk2/hzq/prometheus/prometheus.yml
```

在 `node_exporter` job 的 `targets` 列表中添加新 IP：

```yaml
  - job_name: "node_exporter"
    static_configs:
      - targets:
        - '172.20.56.74:9100'
        - '172.20.56.83:9100'
        - '172.20.56.84:9100'
        - '172.20.56.85:9100'
        - '172.20.56.NEW:9100'    # 新增
```

3. 热加载配置（无需重启）：

```bash
curl -X POST http://localhost:9090/-/reload
```

> 已通过 `--web.enable-lifecycle` 启用热加载。

### Doris 集群扩缩容后更新监控

当 Doris 集群新增或下线 FE/BE 节点后，需要更新 Prometheus 配置：

```bash
# 1. 查看当前 FE/BE 列表
mysql -h 172.20.56.74 -P 9030 -u root -e "SHOW FRONTENDS\G"
mysql -h 172.20.56.74 -P 9030 -u root -e "SHOW BACKENDS\G"

# 2. 编辑 prometheus.yml, 在 doris_cluster job 的 targets 中增删节点
vim /mnt/disk2/hzq/prometheus/prometheus.yml

# 3. 热加载
curl -X POST http://localhost:9090/-/reload
```

或者重新执行部署脚本（脚本会重新自动发现并覆盖配置，已部署的 binary 和 systemd 不受影响）。

### 修改 Prometheus 数据保留时间

默认保留 30 天。如需调整，编辑 systemd unit 文件：

```bash
vim /etc/systemd/system/prometheus.service
# 修改 --storage.tsdb.retention.time=30d 为期望值
systemctl daemon-reload
systemctl restart prometheus
```

### 手动导入 Grafana Dashboard

如果自动导入的 Dashboard 不满足需求，可在 Grafana UI 中手动导入：

1. 访问 http://172.20.56.74:3000
2. 左侧菜单 -> Dashboards -> Import
3. 输入 Dashboard ID（推荐）：
   - **1860** - Node Exporter Full（系统监控，最全面）
   - **9734** - Doris Overview（Doris 官方 Dashboard）
   - **11074** - Node Exporter for Prometheus（简洁版）
4. 选择 Prometheus 数据源 -> Import

### 配置告警（可选扩展）

在 `prometheus.yml` 同级目录创建告警规则文件：

```bash
mkdir -p /mnt/disk2/hzq/prometheus/rules
cat > /mnt/disk2/hzq/prometheus/rules/alerts.yml << 'EOF'
groups:
  - name: node_alerts
    rules:
      - alert: HighCpuUsage
        expr: 100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "CPU 使用率过高 ({{ $labels.instance }})"
          description: "CPU 使用率超过 85%，当前值: {{ $value }}%"

      - alert: HighMemoryUsage
        expr: (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100 > 90
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "内存使用率过高 ({{ $labels.instance }})"
          description: "内存使用率超过 90%，当前值: {{ $value }}%"

      - alert: DiskSpaceLow
        expr: (1 - node_filesystem_avail_bytes{fstype!="tmpfs"} / node_filesystem_size_bytes{fstype!="tmpfs"}) * 100 > 85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "磁盘空间不足 ({{ $labels.instance }})"
          description: "磁盘使用率超过 85%，挂载点: {{ $labels.mountpoint }}，当前值: {{ $value }}%"

      - alert: NodeDown
        expr: up{job="node_exporter"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "节点离线 ({{ $labels.instance }})"
          description: "Node Exporter 无法连接超过 1 分钟"

  - name: doris_alerts
    rules:
      - alert: DorisNodeDown
        expr: up{job="doris_cluster"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Doris 节点离线 ({{ $labels.instance }})"
          description: "Doris {{ $labels.group }} 节点无法连接超过 1 分钟"

      - alert: DorisHighCompactionScore
        expr: doris_be_tablet_cumulative_max_compaction_score > 500
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Doris BE Compaction 积压 ({{ $labels.instance }})"
          description: "Compaction Score 持续超过 500，当前值: {{ $value }}"

      - alert: DorisHighQueryLatency
        expr: doris_fe_query_latency_ms{quantile="0.99"} > 10000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Doris P99 查询延迟过高 ({{ $labels.instance }})"
          description: "P99 查询延迟超过 10s，当前值: {{ $value }}ms"

      - alert: DorisFEHighJvmUsage
        expr: jvm_heap_size_bytes{type="used"} / jvm_heap_size_bytes{type="max"} > 0.85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Doris FE JVM 堆使用率过高 ({{ $labels.instance }})"
          description: "JVM 堆使用率超过 85%"
EOF
```

然后取消 `prometheus.yml` 中 `rule_files` 的注释：

```yaml
rule_files:
  - "rules/*.yml"
```

热加载生效：

```bash
curl -X POST http://localhost:9090/-/reload
```

## 故障排查

### 服务启动失败

```bash
# 查看详细错误
journalctl -u <服务名> --no-pager -n 50

# 检查端口占用
ss -tlnp | grep -E '3000|9090|9100'

# 手动启动查看错误输出
/mnt/disk2/hzq/prometheus/prometheus --config.file=/mnt/disk2/hzq/prometheus/prometheus.yml
```

### Prometheus targets 显示 DOWN

```bash
# Node Exporter
ssh root@目标IP "systemctl status node_exporter"
curl http://目标IP:9100/metrics

# Doris FE
curl http://FE_IP:8030/metrics

# Doris BE
curl http://BE_IP:8040/metrics

# 检查防火墙
iptables -L -n | grep -E '9100|8030|8040'
```

### Doris targets 全部 DOWN

1. 确认 Doris 集群正常运行：`mysql -h 172.20.56.74 -P 9030 -u root -e "SHOW FRONTENDS"`
2. 确认 FE HTTP 端口可达：`curl http://FE_IP:8030/metrics`（应返回 Prometheus 格式文本）
3. 确认 BE HTTP 端口可达：`curl http://BE_IP:8040/metrics`
4. 检查 `prometheus.yml` 中 `doris_cluster` job 的 targets 是否正确
5. 如果 Doris 集群扩缩容过，需要更新 targets 并热加载

### Doris Dashboard 无数据

1. 确认 Prometheus 中 Doris targets 状态为 UP：访问 http://172.20.56.74:9090/targets
2. 在 Prometheus UI 查询 `up{job="doris_cluster"}`，确认有数据
3. 在 Grafana 的 Doris Overview Dashboard 中，检查顶部的 `job` 下拉框是否选中了 `doris_cluster`
4. 检查 Dashboard 的 datasource 是否指向正确的 Prometheus 实例

### Grafana 数据源连接失败

1. 确认 Prometheus 运行正常：`curl http://localhost:9090/-/ready`
2. 在 Grafana 中：Settings -> Data Sources -> Prometheus -> Test，查看错误信息

### 包下载失败

脚本会依次尝试以下下载源：
1. 国内 GitHub 镜像（ghproxy.com 等）
2. GitHub 官方直连
3. Grafana 官方 CDN（`dl.grafana.com`）

如果全部失败，手动下载后放入 `packages/` 目录重新执行即可（脚本检测到文件存在会跳过下载）。

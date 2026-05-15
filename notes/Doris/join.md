基本概念：
* PlanFramgnet 执行计划在 FE 上的分发单位，一个 Plan 由多个 PlanFramgnet 组成
* PlanNode 是 PlanFragment 的基本组成单位，explain 看到的各个节点就是 PlanNode
* Operator 是 BE 上执行时的概念，大多数情况下，对于一个 PlanNode，BE 上都会创建一个 Operator，少数情况，如 HASH_JOIN_NODE 等内部有数据依赖的 Node，会在 BE 上对应多个 Operator。一个 HASH_JOIN_NODE，会对应一个 ProbeOperator 和一个 BuildSinkOperator。
* Pipeline 也是 BE 上的概念，pipeline 属于逻辑概念，并不是执行的实体。每条 Pipeline 都会包含 source operaotr + operator + sink operator 的 operator 组合
    对于一个 PlanNode 来说，如果其内部包含了数据依赖，通常会被分解为两条 pipeline，假如 pipeline A 依赖 pipeline B 的执行完成，那么 pipeline A 的 source operaotr 将会对应 pipeline B 的 sink operator，
* PipelineTask 是 BE 上的实际调度执行单位。对于一个并发度为 n 的 pipeline，其会创建 n 个看起来一样的 pipeline task。

### Shared hash table in broadcast join
```sql
SELECT count(1)
FROM demo.DWA_CHECK_KPI A
INNER JOIN[broadcast] demo.DIM_KPI_CUBE B ON A.KPI_ID = B.KPI_ID
INNER JOIN[broadcast] demo.DIM_KPI_CODE C ON A.KPI_CODE = C.KPI_CODE
```
```text
+---------------------------------------------------------------------------------------------------------------------------------+
| Explain String(Nereids Planner)                                                                                                 |
+---------------------------------------------------------------------------------------------------------------------------------+
| PLAN FRAGMENT 0                                                                                                                 |
|   OUTPUT EXPRS:                                                                                                                 |
|     count(*)[#61]                                                                                                               |
|   PARTITION: UNPARTITIONED                                                                                                      |
|                                                                                                                                 |
|   VRESULT SINK                                                                                                                  |
|      MYSQL_PROTOCAL                                                                                                             |
|                                                                                                                                 |
|   9:VAGGREGATE (merge finalize)(673)                                                                                            |
|   |  output: count(partial_count(*)[#60])[#61]                                                                                  |
|   |  cardinality=1                                                                                                              |
|   |                                                                                                                             |
|   8:VEXCHANGE                                                                                                                   |
|                                                                                                                                 |
| PLAN FRAGMENT 1                                                                                                                 |
|                                                                                                                                 |
|   PARTITION: HASH_PARTITIONED: FLIGHT_DATE[#31]                                                                                 |
|                                                                                                                                 |
|   STREAM DATA SINK                                                                                                              |
|     EXCHANGE ID: 08                                                                                                             |
|     UNPARTITIONED                                                                                                               |
|                                                                                                                                 |
|   7:VAGGREGATE (update serialize)(667)                                                                                          |
|   |  output: partial_count(*)[#60]                                                                                              |
|   |                                                                                                                             |
|   6:VHASH JOIN(661)                                                                                                             |
|   |  join op: INNER JOIN(BROADCAST)[]                                                                                           |
|   |  equal join conjunct: (KPI_CODE[#56] = KPI_CODE[#10])                                                                       |
|   |  final projections: KPI_CODE[#57]                                                                                           |
|   |                                                                                                                             |
|   |----1:VEXCHANGE                                                                                                              |
|   |       distribute expr lists: KPI_CODE[#10]                                                                                  |
|   |                                                                                                                             |
|   5:VHASH JOIN(645)                                                                                                             |
|   |  join op: INNER JOIN(BROADCAST)[]                                                                                           |
|   |  equal join conjunct: (KPI_ID[#51] = KPI_ID[#30])                                                                           |
|   |  final projections: KPI_CODE[#54]                                                                                            |
|   |                                                                                                                             |
|   |----3:VEXCHANGE                                                                                                              |
|   |       distribute expr lists: KPI_ID[#30]                                                                                    |
|   |                                                                                                                             |
|   4:VOlapScanNode(626)                                                                                                          |
|      TABLE: demo.DWA_CHECK_KPI(DWA_CHECK_KPI), PREAGGREGATION: ON                                                               |
|      final projections: KPI_ID[#32], KPI_CODE[#39]                                                                              |
|                                                                                                                                 |
| PLAN FRAGMENT 2                                                                                                                 |
|                                                                                                                                 |
|   PARTITION: HASH_PARTITIONED: KPI_ID[#11]                                                                                      |
|                                                                                                                                 |
|   STREAM DATA SINK                                                                                                              |
|     UNPARTITIONED                                                                                                               |
|                                                                                                                                 |
|   2:VOlapScanNode(633)                                                                                                          |
|      TABLE: demo.DIM_KPI_CUBE(DIM_KPI_CUBE), PREAGGREGATION: ON                                                                 |
|      final projections: KPI_ID[#11]                                                                                             |
|                                                                                                                                 |
| PLAN FRAGMENT 3                                                                                                                 |
|                                                                                                                                 |
|   PARTITION: HASH_PARTITIONED: KPI_CODE[#0]                                                                                     |
|                                                                                                                                 |
|   STREAM DATA SINK                                                                                                              |
|     UNPARTITIONED                                                                                                               |
|                                                                                                                                 |
|   0:VOlapScanNode(649)                                                                                                          |
|      TABLE: demo.DIM_KPI_CODE(DIM_KPI_CODE), PREAGGREGATION: ON                                                                 |
|      final projections: KPI_CODE[#0]                                                                                            |
+---------------------------------------------------------------------------------------------------------------------------------+
```
Fragment 1 中包含两个 broad cast join node，
```cpp
PipelineFragmentContext::_create_operator {
    case TPlanNodeType::HASH_JOIN_NODE: {
        const auto is_broadcast_join = tnode.hash_join_node.__isset.is_broadcast_join &&
                                       tnode.hash_join_node.is_broadcast_join;
        if (is_broadcast_join) {
            operator.reset(new HashJoinProbeOperatorX(pool, tnode, next_operator_id(), descs));
            RETURN_IF_ERROR(cur_pipeline->add_operator(op));
        }
    }
}

PipelineFragmentContext::_create_tree_helper(plan_node_list, plan_node_idx) {
    PlanNode cur_plan_node = PlanNodeList[plan_node_idx];
    [cur_pipeline, cur_operator] = _create_operator (cur_plan_node);

    for (size_t i = 0; i < cur_plan_node.child_size; ++i) {
        _create_tree_helper(plan_node_list, plan_node_idx + 1 + i);
    }
}
```
`PipelineFragmentContext::_create_tree_helper` 这个函数实现还是比较绕的。。只需要知道，对于上述的 `PlanFramgnet 1`，我们可以得到如下的 pipeline 拓扑：
```text
Pipeline1:
    DataStreamSink
    |
    AggOperator
    |
    HashJoinProbeOperator(PlanNodeId1, OperatorId1)
    |
    HashJoinProbeOperator(PlanNodeId2, OperatorId2)
    |
    OlapScanOperator

Pipeline2:
    HashJoinBuildSinkOperator(DestId: OperatorId1)
    |
    ExchangeSourceOperator

Pipeline3:
    HashJoinBuildSinkOperator(DestId: OperatorId2)
    |
    ExchangeSourceOperator
```
PipelineFragmentContext 中用来记录数据依赖关系的 DAG 内容如下
```text
    std::map<PipelineId, std::vector<PipelineId>> _dag;

    [Pipline1 -> {Pipeline2, Pipeline3}]
```

TODO: dependency 是怎么设置的。
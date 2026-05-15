<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [Overall](#overall)
  - [vunion_node](#vunion_node)
    - [init](#init)
  - [vscan_node](#vscan_node)

<!-- /code_chunk_output -->



### Overall
create_tree_helper creates exec node tree in a recursive manner

```cpp
ExecNode::create_tree_helper(
    RuntimeState* runtime_state, 
    ObjectPool* object_pool,
    const std::vector<TPlanNode>& thrift_plan_nodes,
    const DescriptorTbl& descs,
    ExecNode* parent,
    int* node_idx,
    ExecNode** root)
{
    const TPlanNode& curr_plan_node = thrift_plan_nodes[*node_idx];
    int num_children = curr_plan_node.num_children;

    // Step 1 Create current ExecNode according to current thrift plan node.
    ExecNode* node = nullptr;
    create_node(state, pool, curr_plan_node, descs, &node);

    // Step 1.1
    // Record current node if we have parent
    if (parent != nullptr) {
        parent->_children.push_back(node);
    } else {
        *root = node;
    }

    // Step.2 Create child ExecNode tree in a recursive manner
    for (int i = 0; i < num_children; i++) {
        ++*node_idx;
        create_tree_helper(state, pool, thrift_plan_nodes, descs, node, node_idx, nullptr);
    }

    // Step.3 Init myself after sub ExecNode tree is created and initialized
    node->init(curr_plan_node, state)


}
```

// runtime_state  is owned by PipelineFragmentContext
// object_pool is owned by RuntimeState

```cpp

```

#### vunion_node
##### init
```cpp
Status VUnionNode::init(const TPlanNode& tnode, RuntimeState* state) {
    ExecNode::init(tnode, state));
    
    // Create const_expr_ctx_lists_ from thrift exprs.
    const auto& const_texpr_lists = tnode.union_node.const_expr_lists;
    for (const auto& texprs : const_texpr_lists) {
        VExprContextSPtrs ctxs;
        RETURN_IF_ERROR(VExpr::create_expr_trees(texprs, ctxs));
        _const_expr_lists.push_back(ctxs);
    }

    // Create result_expr_ctx_lists_ from thrift exprs.
    auto& result_texpr_lists = tnode.union_node.result_expr_lists;
    for (auto& texprs : result_texpr_lists) {
        VExprContextSPtrs ctxs;
        RETURN_IF_ERROR(VExpr::create_expr_trees(texprs, ctxs));
        _child_expr_lists.push_back(ctxs);
    }
    return Status::OK();
}
```
What is const_expr_lists & result_expr_lists?

`select round(250/100)`

```txt
VUNION
    constExprLists
        FunctionCallExpr
            fnName: round
            fnParams:
                exprs:
                    FloatLiteral: 2.5
            type: DOUBLE
            ScalarFunction:
                name: round
                retType: DOUBLE
                argTypes: DOUBLE
            children:
                FloatLiteral
                    value: 2.5
    children: []
```
250/100=2.5 是在 FE 计算出来的

`select round(2.5)`
```txt
VUNION
    constExprLists
        FunctionCallExpr
            fnName: round
            fnParams:
                exprs:
                    DecimalLiteral
                        value: 2.5
                        type: DECIMALV3(2,1)
```

传到 be 的时候字面值都是 2.5 可是类型不一样。
对比一下代码：

```cpp
DoubleRoundOneImpl<round>



FunctionRounding<DoubleRoundOneImpl<round>, RoundingMode::round>
FunctionRounding<DecimalRoundOneImpl<round>, RoundingMode::round>

auto call = [&](const auto& types) -> bool {
    using Types = std::decay_t<decltype(types)>;
    using DataType = typename Types::LeftType;

    if constexpr (IsDataTypeNumber<DataType> || IsDataTypeDecimal<DataType>) {
        using FieldType = typename DataType::FieldType;
        res = Dispatcher<FieldType, rounding_mode, tie_breaking_mode>::apply(
                column.column.get(), scale_arg);
        return true;
    }
    return false;
}

if (!call_on_index_and_data_type<void>(column.type->get_type_id(), call)) {
            return Status::InvalidArgument("Invalid argument type {} for function {}",
                                           column.type->get_name(), name);
}

block.replace_by_position(result, std::move(res));
return Status::OK();

template <typename T, typename F>
bool call_on_index_and_data_type(TypeIndex number, F&& f) {
    switch(number) {
        ...
        case TypeIndex::Float32:
            return f(TypePair<DataTypeNumber<Float32>, T>());
        case TypeIndex::Float64:
            return f(TypePair<DataTypeNumber<Float64>, T>());
        ...
        case TypeIndex::Decimal32:
            return f(TypePair<DataTypeDecimal<Decimal32>, T>());
        case TypeIndex::Decimal64:
            return f(TypePair<DataTypeDecimal<Decimal64>, T>());
        ...
    }
}
```
这里看，模板展开后对于 `DoubleRoundOneImpl<round>` 和 `DecimalRoundOneImpl<round>`, call 变为：
```cpp
(TypePair<DataTypeNumber<Float64>, T>())
{
    using Types = std::decay_t<decltype<DataTypeNumber<Float64>, T>()>>
}
```

Double


FunctionImpl = FloatRoundImpl<Float64, Round, Zero>

FloatRoundImpl<Float64, Round, Zero>::apply(column, 0, res_col);


#### vscan_node
```thrift
// A single scan range plus the hosts that serve it
struct TScanRangeLocations {
  1: required PlanNodes.TScanRange scan_range
  // non-empty list
  2: list<TScanRangeLocation> locations
}
```

```java

public class TScanRangeLocations {
    private TScanRange scan_range;
    private List<TScanRangeLocation> locations;

}

public abstract class ScanNode extends PlanNode {
    protected List<TScanRangeLocations>;
    ...
    protected abstract void createScanRangeLocations();
}
```
函数 `createScanRangeLocations()` 会更新 `locations`,

DataGenScanNode 为例：
```java
public class DataGenScanNode extends ExternalScanNode {
    protected void createScanRangeLocations() throws UserException {
        scanRangeLocations = Lists.newArrayList();
        for (TableValuedFunctionTask task : tvf.getTasks()) {
            TScanRangeLocations locations = new TScanRangeLocations();
            TScanRangeLocation location = new TScanRangeLocation();
            location.setBackendId(task.getBackend().getId());
            location.setServer(new TNetworkAddress(task.getBackend().getHost(), task.getBackend().getBePort()));
            locations.addToLocations(location);
            locations.setScanRange(task.getExecParams());
            scanRangeLocations.add(locations);
        }
    }
}
```
以上是 ScanRangeLocations 的生产过程，其消费是在 `Coordinator.computeScanRangeAssignment` 中进行的，消费的目的肯定是产生 FE 与 BE 之间传递参数的 thrift 数据结构：
```txt
TPipelineFragmentParams {
    ...
    list<TPipelineInstanceParams> {
        TPipelineInstanceParams {
            Types.TUniqueId fragment_instance_id
            bool build_hash_table_for_broadcast_join = false;
            map<Types.TPlanNodeId, list<TScanRangeParams>> per_node_scan_ranges
            i32 sender_id
            TRuntimeFilterParams runtime_filter_params
            i32 backend_num
            map<Types.TPlanNodeId, bool> per_node_shared_scans
        }
    }
}
```
逻辑计划的执行单位是 Fragment，一个 Fragment 内可能会有多个 node，也可能会有多个 scan node，所以可以看到 per_node_scan_ranges 的 value 类型是 `list<TScanRangeParams>`。

在看生成最终 thrift 数据结构的算法之前，先研究下 Coordinator 中有哪些与 scan 相关的数据结构
```java
class Coordinator {
    ...
    class FragmentExecParams {
        ...
        public FragmentScanRangeAssignment scanRangeAssignment;
    }

    private Map<PlanFragmentId, FragmentExecParams> fragmentExecParams;
    private final List<ScanNode> scanNodes;
}

// map from a BE host address to the per-node assigned scan ranges;
// records scan range assignment for a single fragment
// BackendAddress -> <PlanNodeId, List<TScanRangeParams>>
static class FragmentScanRangeAssignment
    extends HashMap<TNetworkAddress, Map<Integer, List<TScanRangeParams>>> {
}
```
从这里可以看到，`FragmentScanRangeAssignment` 是从 Planner 的 ScanNode 到 Thrift 数据结构的中间数据结构，转换路是 `List<ScanNode> -> FragmentScanRangeAssignment -> Thrift`

```java
public class Coordinator {
    private void computeScanRangeAssignment() {
        ...
        for (ScanNode scanNode : scanNodes) {
            ...
            locations = scanNode.getScanRangeLocations();
            ...
            FragmentScanRangeAssignment assignment
                    = fragmentExecParamsMap.get(scanNode.getFragmentId()).scanRangeAssignment;
            ...
            computeScanRangeAssignmentByScheduler(scanNode, locations, assignment, assignedBytesPerHost,
                        replicaNumPerHost);
        }
    }

    private void computeScanRangeAssignmentByScheduler(
            final ScanNode scanNode,
            final List<TScanRangeLocations> locations,
            FragmentScanRangeAssignment assignment,
            Map<TNetworkAddress, Long> assignedBytesPerHost,
            Map<TNetworkAddress, Long> replicaNumPerHost) throws Exception {
        for (TScanRangeLocations scanRangeLocations : locations) {
            ...
            Map<Integer, List<TScanRangeParams>> scanRanges = findOrInsert(assignment, execHostPort,
                    new HashMap<Integer, List<TScanRangeParams>>());
            List<TScanRangeParams> scanRangeParamsList = findOrInsert(scanRanges, scanNode.getId().asInt(),
                    new ArrayList<TScanRangeParams>());
            // add scan range
            TScanRangeParams scanRangeParams = new TScanRangeParams();
            scanRangeParams.scan_range = scanRangeLocations.scan_range;
            scanRangeParamsList.add(scanRangeParams);
            ...
        }
    }
}
```
上述代码完成了从 `List<ScanNode> -> FragmentScanRangeAssignment` 的转换。对于每一个 ScanNode，遍历其 ScanRangeLocations，将 `ScanRangeLocations.ScanRange` 添加到  对应 FragmentScanRangeAssignment 的 `List<TScanRangeParams>` 中


```java {.line-numbers}
class Coordinator {
    ...
    private void computeFragmentHosts() {
        for(int i = fragments.size() - 1; i >= 0; --i) {
            PlanFragment fragment = fragements.get(i);
            FragmentExecParams params = fragmentExecParamsMap.get(fragment.getFragmentId());
            ...
            for (Entry<TNetworkAddress, Map<Integer, List<TScanRangeParams>>> entry : fragmentExecParamsMap.get(
                        fragment.getFragmentId()).scanRangeAssignment.entrySet()) {
                TNetworkAddress scan_range_address = entry.getKey();
                Map<Integer, List<TScanRangeParams>> plan_node_params = entry.getValue();

                for (Integer id : value.keySet()) {
                    List<TScanRangeParams> perNodeScanRanges = value.get(id);
                    List<List<TScanRangeParams>> perInstanceScanRanges;
                    ...
                    int expectedInstanceNum = Math.min(parallelExecInstanceNum,
                                    leftMostNode.getNumInstances());
                    expectedInstanceNum = Math.max(expectedInstanceNum, 1);
                    perInstanceScanRanges = Collections.nCopies(expectedInstanceNum, perNodeScanRanges);

                    for (int j = 0; j < perInstanceScanRanges.size(); j++) {
                            List<TScanRangeParams> scanRangeParams = perInstanceScanRanges.get(j);
                            boolean sharedScan = sharedScanOpts.get(j);

                            FInstanceExecParam instanceParam = new FInstanceExecParam(null, key, 0, params);
                            instanceParam.perNodeScanRanges.put(id, scanRangeParams);
                            instanceParam.perNodeSharedScans.put(id, sharedScan);
                            params.instanceExecParams.add(instanceParam);
                    }
                }
            }
        }
    }
}
```
这里 20 行的逻辑是，首先获得 ScanNode 指定的当前 ScanNode 需要多少并发度，然后根据这个并发度 F，将这个 node 的 ScanRange 参数拷贝 F 次
NOTE: 这里感觉有问题？`F * List<TScanRangeParams>` 会导致实际的并发度并不是 F。

假设 node 的 scan range 是 range 1 + range 2，instance num = 3，那么这里 copy 过后，20 行的 perInstanceScanRanges 就有 3 个 list，
每个 list 的内容都是 range 1 + range 2。

第 22 行开始，遍历这 3 个 list，把这三个 list 添加到 fragmentExecParamsMap 中对应的位置。
具体来说，26 行 `FInstanceExecParam instanceParam = new FInstanceExecParam(null, key, 0, params);` 这里注意 params 是第 6 行获取的 fragmentExecParamsMap 的 value 的引用。
```java
protected class FragmentExecParams {
    ...
    public List<FInstanceExecParam> instanceExecParams
}
```
22 到 29 行的循环结束之后，FragmentExecParams.instanceExecParams 的长度将会增加 3，增加的每个 FInstanceExecParam 都一样，
```java
static class FInstanceExecParam {
    TUniqueId instanceId;
    TNetworkAddress host;
    Map<Integer, List<TScanRangeParams>> perNodeScanRanges = Maps.newHashMap();
    Map<Integer, Boolean> perNodeSharedScans = Maps.newHashMap();

    int perFragmentInstanceIdx;
    ...
}
```
FInstanceExecParam.perNodeScanRanges 将会是 `<NodeId -> [ScanRange1, ScanRange2]>`

**说实话，这段代码真的写的很难以理解。**





FragmentExecParams 的 thrift 方法用于产生 发送给 BE 的 rpc 参数
```cpp
protected class FragmentExecParams {
    List<TExecPlanFragmentParams> toThrift(int backendNum) {

    }
}
```

BE 上如何执行 ScanNode
```cpp
Status PipelineFragmentContext::prepare(const doris::TPipelineFragmentParams& request,
                                        const size_t idx) {
    const auto& local_params = request.local_params[idx];
    ...
    std::vector<ExecNode*> scan_nodes;
    std::vector<TScanRangeParams> no_scan_ranges;
    _root_plan->collect_scan_nodes(&scan_nodes);

    // set scan range in ScanNode
    for (int i = 0; i < scan_nodes.size(); ++i) {
        ExecNode* node = scan_nodes[i];
        if (typeid(*node) == typeid(vectorized::NewOlapScanNode) ||
            typeid(*node) == typeid(vectorized::NewFileScanNode) ||
            typeid(*node) == typeid(vectorized::NewOdbcScanNode) ||
            typeid(*node) == typeid(vectorized::NewEsScanNode) ||
            typeid(*node) == typeid(vectorized::VMetaScanNode) ||
            typeid(*node) == typeid(vectorized::NewJdbcScanNode)) {
            auto* scan_node = static_cast<vectorized::VScanNode*>(scan_nodes[i]);
            auto scan_ranges = find_with_default(local_params.per_node_scan_ranges, scan_node->id(),
                                                 no_scan_ranges);
            const bool shared_scan =
                    find_with_default(local_params.per_node_shared_scans, scan_node->id(), false);
            scan_node->set_scan_ranges(scan_ranges);
            scan_node->set_shared_scan(_runtime_state.get(), shared_scan);
        } else {
            ScanNode* scan_node = static_cast<ScanNode*>(node);
            auto scan_ranges = find_with_default(local_params.per_node_scan_ranges, scan_node->id(),
                                                 no_scan_ranges);
            static_cast<void>(scan_node->set_scan_ranges(scan_ranges));
        }


    }
}
```
对于每一个 instance，
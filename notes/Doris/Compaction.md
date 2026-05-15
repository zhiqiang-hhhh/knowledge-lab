```plantuml
class BaseCompaction {
    Status prepare_compact() override;

    Status execute_compact() override;
}
class CompactionMixin
class SingleReplicaCompaction
class Compaction {
    # Status prepare_compact()
    # Status execute_compact()
}


CompactionMixin -up-> Compaction
BaseCompaction -up-> CompactionMixin
SingleReplicaCompaction -up-> CompactionMixin
```

```cpp
StorageEngine::_submit_compaction_task(...) {
    Status st = Tablet::prepare_compaction_and_calculate_permits(compaction_type, tablet,
                                                                 compaction, permits);
    ...
    auto status = thread_pool->submit_func([tablet, compaction = std::move(compaction),
                                                compaction_type, permits, force, this]() {
                                                    ...});
}

Tablet::prepare_compaction_and_calculate_permits (...) {
    compaction = std::make_shared<CumulativeCompaction>(tablet->_engine, tablet);
    Status res = compaction->prepare_compact();
}
```

```plantuml
```

## Doris 三类 Compaction 的本质区别

### 核心概念：Cumulative Layer Point（累积层分界点）

理解三类 compaction 的关键在于理解 **cumulative_layer_point**，这是一个版本号分界点，将所有 rowset 分成两个区域：

```
                        cumulative_layer_point
                               ↓
[0-1] [2-3] [4-5] [6-7] │ [8-8] [9-9] [10-10] [11-11]
                        │
←── Base Compaction ───→│←── Cumulative Compaction ──→
        处理区域         │          处理区域
```

---

### 1. Cumulative Compaction（累积合并）

**处理范围**：`cumulative_layer_point` 到 `max_version` 之间的 rowsets

**调用逻辑**（tablet.cpp）：
```cpp
std::vector<RowsetSharedPtr> Tablet::pick_candidate_rowsets_to_cumulative_compaction() {
    return _pick_visible_rowsets_to_compaction(_cumulative_point,
                                               std::numeric_limits<int64_t>::max());
}
```

**本质特点**：
- 处理**新近写入**的小 rowset（每次导入产生一个）
- 频率高，增量合并
- 目的：减少小文件数量，降低查询时需要 merge 的 rowset 数量
- 合并后会**推进** cumulative_layer_point

---

### 2. Base Compaction（基础合并）

**处理范围**：`version 0` 到 `cumulative_layer_point - 1` 之间的 rowsets

**调用逻辑**（tablet.cpp）：
```cpp
std::vector<RowsetSharedPtr> Tablet::pick_candidate_rowsets_to_base_compaction() {
    return _pick_visible_rowsets_to_compaction(std::numeric_limits<int64_t>::min(),
                                               _cumulative_point - 1);
}
```

**本质特点**：
- 处理**已经稳定**的大 rowset（经过多次 cumu compaction 形成的）
- 频率较低，资源消耗较大
- 目的：将 base rowset（version 0-x）与其他稳定 rowset 合并成更大的 base rowset
- 对于 DUP_KEY 表，会跳过特别大的文件（base_compaction.cpp）

---

### 3. Full Compaction（全量合并）

**处理范围**：**所有** rowsets（version 0 到 max_version）

**调用逻辑**（tablet.cpp）：
```cpp
std::vector<RowsetSharedPtr> Tablet::pick_candidate_rowsets_to_full_compaction() {
    traverse_rowsets([&candidate_rowsets](const auto& rs) {
        if (rs->is_local()) {
            candidate_rowsets.emplace_back(rs);  // 所有本地 rowset
        }
    });
}
```

**本质特点**：
- 处理**整个** tablet 的所有 rowset
- 频率最低，通常需要手动触发
- 目的：彻底清理历史版本，将所有数据合并成单个大 rowset
- 执行时会同时持有 `base_compaction_lock` 和 `cumulative_compaction_lock`，阻塞其他两类 compaction
- 对 MOW 表会重新计算 delete bitmap

---

### 对比总结

| 特性 | Cumulative | Base | Full |
|------|------------|------|------|
| **版本范围** | `cumu_point → max` | `0 → cumu_point-1` | `0 → max`（全部）|
| **频率** | 高 | 中 | 低（通常手动） |
| **触发** | 自动 | 自动 | 通常手动 |
| **资源消耗** | 低 | 中 | 高 |
| **目的** | 合并小文件 | 合并稳定文件 | 彻底整理 |
| **是否阻塞其他** | 否 | 否 | 是（同时锁两个） |

---

### 生命周期流程

```
导入数据 → [小 rowset] 
              ↓
        Cumulative Compaction（多次）
              ↓
        [大 rowset] + 推进 cumu_point
              ↓
        Base Compaction
              ↓
        [更大的 base rowset]
              ↓
        Full Compaction（可选，彻底整理）
              ↓
        [单个完整 rowset]
```
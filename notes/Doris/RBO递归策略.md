# 为什么需要 Top-Down 和 Bottom-Up 两种 Plan 重写模式？

在查询优化器中，Plan 重写（Rewrite）是一种通过模式匹配和规则替换来优化执行计划的技术。为了更高效和更彻底地进行重写，系统通常支持两种遍历模式：

* **Top-Down（自顶向下）**：优先处理当前节点，再处理子节点；
* **Bottom-Up（自底向上）**：优先处理子节点，再处理当前节点。

这两种模式分别适用于不同的规则和优化场景，下面通过一个例子来说明它们的作用和差异。

---

## 示例 SQL

```sql
SELECT * FROM t1 WHERE a > 10 AND b < 5;
```

其逻辑计划树如下：

```
Filter(condition: a > 10 AND b < 5)
  |
Scan(t1)
```

---

## 两条 Rewrite Rule

### Rule 1: 拆解 AND 谓词

**匹配模式：**

```
Filter(a AND b)
```

**重写为：**

```
Filter(a)
  |
Filter(b)
  |
...
```

示例应用：

```
Filter(a > 10 AND b < 5)
→
Filter(a > 10)
  |
Filter(b < 5)
  |
Scan(t1)
```

---

### Rule 2: 谓词下推

**匹配模式：**

```
Filter(expr)
  |
Scan(table)
```

**重写为：**

```
Scan(table WHERE expr)
```

---

## Top-Down 模式执行过程

1. 从根节点 `Filter(a > 10 AND b < 5)` 开始；
2. 匹配 `Rule 1`，拆成两个 Filter：

```
Filter(a > 10)
  |
Filter(b < 5)
  |
Scan(t1)
```

3. 继续处理 `Filter(a > 10)`，未匹配；
4. 处理其子节点 `Filter(b < 5)`，匹配 `Rule 2`，下推：

```
Filter(a > 10)
  |
Scan(t1 WHERE b < 5)
```

**最终结果：**

```
Filter(a > 10)
  |
Scan(t1 WHERE b < 5)
```

> ⚠️ Top-Down 只会重写一次当前节点，不会回溯整棵子树，可能错过联动优化机会。

---

## Bottom-Up 模式执行过程

1. 从 `Scan(t1)` 开始，无规则匹配；
2. 到达 `Filter(a > 10 AND b < 5)`，匹配 `Rule 1`，拆解：

```
Filter(a > 10)
  |
Filter(b < 5)
  |
Scan(t1)
```

3. 因为发生了重写，**必须回溯子树，重新从底向上处理**：

* `Scan(t1)`：无规则；
* `Filter(b < 5)`：匹配 `Rule 2`，下推：

```
Scan(t1 WHERE b < 5)
```

* `Filter(a > 10)`：匹配 `Rule 2`，下推：

```
Scan(t1 WHERE a > 10 AND b < 5)
```

**最终结果：**

```
Scan(t1 WHERE a > 10 AND b < 5)
```

> ✅ Bottom-Up 可以通过回溯子树，捕捉多个规则之间的联动效果，实现更彻底的优化。

---

## 模式对比总结

| 维度     | Top-Down 模式          | Bottom-Up 模式             |
| ------ | -------------------- | ------------------------ |
| 处理顺序   | 当前节点 → 子节点           | 子节点 → 当前节点               |
| 重写逻辑   | 当前节点重写后继续尝试自己，再递归子节点 | 子节点重写后再处理当前节点（可递归回溯）     |
| 性能优点   | 重写局部，效率高             | 能捕捉规则联动，保证更彻底的优化         |
| 使用场景   | 简单变换（拆解、模式替换）        | 依赖上下文变化（谓词下推、连接重排、表达式融合） |
| 是否回溯子树 | 否，只重写当前节点            | 是，必要时会整棵子树重新遍历           |

---

## 小结

我们需要同时支持 **Top-Down** 和 **Bottom-Up** 两种 Plan 重写模式，原因在于：

* **Top-Down 更高效**，适合单点变换；
* **Bottom-Up 更彻底**，适合处理规则间的联动；
* 实际系统（如 Doris、Calcite、Spark Catalyst）通常都同时支持这两种模式，并结合 Cost-Based 策略来调度规则应用顺序。

> 最佳实践：为每条 Rule 指定重写策略（Top-Down 或 Bottom-Up），并使用 Cost-Based 或 Heuristic 控制调度顺序。

---

如需扩展实际系统的设计或进一步案例代码，也可以继续交流。

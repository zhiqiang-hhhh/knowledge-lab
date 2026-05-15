
<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [15.1 Overview](#151-overview)
- [15.4 Sorting](#154-sorting)
- [15.5 Join Operation](#155-join-operation)
  - [15.5.1 Nested-Loop Join](#1551-nested-loop-join)
  - [15.5.2 Block Nested-Loop Join](#1552-block-nested-loop-join)
  - [15.5.3 Indexed Nested-Loop Join](#1553-indexed-nested-loop-join)
  - [15.5.4 Merge Join](#1554-merge-join)
    - [15.5.4.1 Merge-Join Algorithm](#15541-merge-join-algorithm)
  - [15.5.5 Hash Join](#1555-hash-join)
    - [15.5.5.2 Recursive Partitioning](#15552-recursive-partitioning)
    - [15.5.5.3 Handling of Overflows](#15553-handling-of-overflows)
    - [15.5.5.4 Cost of Hash Join](#15554-cost-of-hash-join)
  - [15.5.6 Complex Joins](#1556-complex-joins)
  - [15.5.7 Joins over Spatial Data](#1557-joins-over-spatial-data)
- [15.7 Evaluation of Expression](#157-evaluation-of-expression)
  - [15.7.1 Materialization](#1571-materialization)
  - [15.7.2 Pipeline](#1572-pipeline)

<!-- /code_chunk_output -->
## 15.1 Overview
1. Parsing and translation
2. Optimization
3. Evaluation

## 15.4 Sorting


## 15.5 Join Operation

equi-join 

student $\Join$ takes

* Number of records of student: $n_{student}$ = 5000;
* Number of blocks of student: $b_{student}$ = 100;
* Number of records of takes: $n_{takes}$ = 10,000;
* Number of blocks of takes: $b_{takes}$ = 400;


### 15.5.1 Nested-Loop Join

`r` $\Join_{\theta}$ `s`

`r` 被称为外表，因为它的 for loop 在外，`s` 被称为内表。

```txt
for each tuple tr in r do:
    for each tuple ts in s do:
        test pair(tr, ts) to see if they satisfy the join condition
        if they do, add tr * ts to the result
    end
end
```
Cost

一共需要处理的 tuples 数量：$n_{r} * n_{s}$

最差情况：对于每个表内存中只能保存一个 block，即内存中只能保存两个 block，**for each record in r, we have to do a full scan on s**. So, we have $b_{r} + n_{r} * b_{s}$ blocks to transfer in total. For inner table s, we only have one seek since it is scanned sequentially, and a total of $b_{r}$ seek for outer table r, which leading to $b_{r} + n_{r}$ seeks in total.

最常见的最优情况：One of the relations fits entirely in the memory.

注意到 nested-loop join 中内表被读取的次数是最多的，因此为了避免过多的 IO 开销，我们需要把小表作为 inner table。如果 inner table 可以完全放进内存，那么对于 inner table 只需要一次 seek。对于外表来说，考虑到后续读外表都是顺序读且有 page cache，那么只有第一次读 block 需要一次 seek，后续都不需要。因此此时总体来看我们只需要两次 seek。

We should make that table a inner table, so that we just need to do 1 + 1 seek for table r and s (we have page cache and memory processing is much faster than reading from disk, so that we can read blocks from table r sequentially), and $b_{r} + b_{s}$ blocks to transform in total.

Consider using that table a outer table. We have still $b_{r} + b_{s}$ blocks to transform. After 1 seek to read table r, we need $n_{r}$ times seek for continue processing, leading to $1 + n_{r}$ seeks in total.

|`r` $\Join_{\theta}$ `s`|bast case|worst case|
|--|--|--|
|nested loop join|$b_{r}$ + $b_{s}$ blocks|$n_{r}$*$b_{s}$ + $b_{r}$ blocks|

具体到 student $\Join$ takes 的情况，假设没有任何索引。

Using student as outer relation, we have $n_{s} * n_{t} = 5000 * 10,000 = 50 * 10^{6}$ pairs of tuples to processing. In the worst case, number of block transfers is $b_{student} + n_{student} * b_{takes} = 100 * 5000 * 400 = 200100$ plus $b_{student} + n_{student} = 5000 + 100 = 5100$ seeks. In best cases, both relation can be read in memory, so we have $100 + 400$ blocks to transfer, and 2 seeks.
If we use takes as outer relation. In worst cases, we need to transfor $b_{takes} + n_{takes} * b_{student} = 400 +  10000 * 100 = 100400$ blocks plus $b_{takes} + n_{takes} = 10000 + 400 = 10400$ seeks.

|outer relation|worst|best|
|--|--|--|
|student|200100 block transfer and 5100 seeks|500 block transfer and 2 seek|
|takes|100400 block transfer and 10400 seeks|500 block transfer and 2 seek|

通常一次 seek 花费的时间是 tranfer 一个 block 的 40 倍。 $Time_{seek} \simeq 40 * Time_{transfer}$，估算两种计算方式的相对开销：
`2 * 1 + 1/20 * 40 = 2 + 2 = 4`
`1 * 1 + 1/10 * 40 = 1 + 4 = 5`

### 15.5.2 Block Nested-Loop Join
15.5.1 中的算法是针对行的：每次对 outer table 的一行进行计算，因此一个明显的优化是改成基于 block 的计算。
```txt
for each block Br of d:
    for each Block Bs of s:
        for each Tuple Tr of Br:
            for each Tuple Ts of Bs:
                test pair(Tr, Ts) to see if they satisfy the join condition
                if they do, add Tr * Ts to the result
            end
        end
    end
end
```
由于内表被读取的单位是 block，并且被处理的单位也是 block，那么对于外表的每一行来说，内表的每个 block 只会被磁盘读取一次，而不是多次。

因此在最差情况下（内外表各自有一个 block 在内存）block nested-loop join 一共需要 transfer $b_{r} * b_{s} + b_{r}$ 个 block，内外表的 block 是交叉顺序读入的，所以外表的 block 一共需要 $b_{r}$ 次 seek，内表也需要 $b_{r}$ 次 seek，所以一共需要 $2 * b_{r}$ 次 seek。

|`r` $\Join_{\theta}$ `s`|bast case|worst case|
|--|--|--|
|nested loop join|$b_{r}$ + $b_{s}$ blocks|$n_{r}$*$b_{s}$ + $b_{r}$ blocks|
|block nested loop join|$b_{r}$ + $b_{s}$ blocks|$b_{r}$*$b_{s}$ + ${b_{r}}$|

### 15.5.3 Indexed Nested-Loop Join

### 15.5.4 Merge Join
Sort-merge-join
#### 15.5.4.1 Merge-Join Algorithm

### 15.5.5 Hash Join
Basic idea: partition the tuples of each of the relations into sets that have the same hash value on the join attributes.

![Alt text](image.png)

After the partition of the relations, the rest of code performs a separate indexed nested-loop join on each of the partitions pairs. To do so, it first builds a hash index on each $s_{i}$, and then probes (that is, looks up $s_{i}$) with tuples from $r_{i}$. The relation s is the build input, and r is the probe input.



The hash function used to build this hash index must be different from the hash function h used earlier, but it is still applied to only the join attributes.
```text
/*Partition s*/
for each tuple ts in s:
    i := h(ts[JoinAttrs])
    H_si := H_si 求并 {ts}
end
/*Partition r*/
for each tuple tr in r:
    i := h(tr[JoinAttrs])
    H_ri := H_ri 求并 {tr}
end

/*Perform join on each partition*/
for i:= 0 to n_h:
    read H_si and build an in-memory hash index on it;
    for each tuple tr in H_ri do
        probe the hash index of H_si to locate all tuples ts
            such that ts[JoinAttrs] = tr[JoinAttrs];
        for each mathcing tuple ts in H_si do
            add ts * ts to result
        end
    end
end
```

**It is best to use the smaller input relation as the build relation.**
#### 15.5.5.2 Recursive Partitioning
如果一次 Partition 之后依然无法对两个 parititon 做 join，那么就需要更进一步的 partition。

#### 15.5.5.3 Handling of Overflows
Hash-table overflow：在 build 侧的 relation s 的 parititon i 上构建的 hash index 大小超出主存。如果在 build 侧的 relaton s 有大量相同的 record，那么这个 partition 中就会包含过多的数据，同时注意本文提到的 hash index 的 bucket 中保存的是 record 而不是更加常见的 rowid，那么此时就会导致 hash index 过大。

#### 15.5.5.4 Cost of Hash Join


### 15.5.6 Complex Joins
### 15.5.7 Joins over Spatial Data
如何对不支持 equality，less than 以及 greater than 的数据类型做 join。

Selection and join conditions on spatial data involve comparison operators that check if one region contains or overlaps another, or whether a region contains a partic- ular point; and the regions may be multi-dimensional. Comparisons may pertain also to the distance between points, for example, finding a set of points closest to a given point in a two-dimensional space.



## 15.7 Evaluation of Expression
### 15.7.1 Materialization
### 15.7.2 Pipeline
We can improve query-evaluation efficiency by reducing the number of temporary files that are produced. We achieve this reduction by combining several relational operations into a pipeline of operations, in which the results of one operation are passed along to the next operation in the pipeline. Evaluation as just described is called pipelined evaluation.
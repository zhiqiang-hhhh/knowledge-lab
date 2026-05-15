
<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [Big Data](#big-data)
  - [Motivation](#motivation)
  - [Big Data Storage Systems](#big-data-storage-systems)
    - [Distrubuted File Systems.](#distrubuted-file-systems)
    - [Sharding across multiple databases.](#sharding-across-multiple-databases)
    - [Key-Value Storage Systems.](#key-value-storage-systems)
    - [Parallel and Distributed Databases.](#parallel-and-distributed-databases)
    - [Replication and Consistency.](#replication-and-consistency)
  - [The MapReduce Paradigm](#the-mapreduce-paradigm)
    - [Why MapReduce](#why-mapreduce)
      - [MapReduce By Example 1: Word Count](#mapreduce-by-example-1-word-count)
      - [MapReduce By Example 2: Log Processing](#mapreduce-by-example-2-log-processing)
    - [Parallel Processing of MapReduce Tasks](#parallel-processing-of-mapreduce-tasks)
    - [SQL on MapReduce](#sql-on-mapreduce)

<!-- /code_chunk_output -->



# Big Data
## Motivation
Building a relational database that supports SQL along with other database features, such as transactions and at the same time can support very high performance by running on a very number of machines, is not an easy task. 通常有两类应用场景：

1. 需要高可扩展性的事务处理系统。事务处理系统支持处理大量段时间执行的查询与数据更新。
2. 需要高可扩展性的查询处理系统，同时需要去支持非关系数据模型。这类系统的典型应用场景是用于处理网站产生的大量日志数据。

## Big Data Storage Systems
### Distrubuted File Systems.
A distributed file system stores files across a large collection of machines while giving a single-file-system view to clients.

The data in a distributed file systemis stored across a number of machines. Files are broken up into multiple blocks. The blocks of a single file can be partitioned across multiple machines. Further, each file block is replicated across multiple (typically three) machines, so that a machine failure does not result in the file becoming inaccessible.

### Sharding across multiple databases.
The term sharding refers to the partitioning of data across multiple databases or machines.

Partitioning can be done by defining a range of keys that each of the databases handles, such partitioning is called range partitioning. Partitioning may also be done by computing a hash function that maps a key value to a partition number; such partitioning is called hash partitioning.

### Key-Value Storage Systems.

### Parallel and Distributed Databases.

### Replication and Consistency.

A key requirement here is consistency, that is, all live replicas of a data item have the same value, and each read sees the latest version of the data item.

在存在网络分区的情况下，没有任何的协议能够同时保证一致性（consistenct）和可用性（availability）。

## The MapReduce Paradigm
MapReduce 模式模拟了一种常见的并行数据处理模式。首先对于大量的输入记录，应用 map 函数，然后使用 reduce 函数对 map 函数得到的结果进行聚合运算。

### Why MapReduce
以一个 word count 应用为例子，该应用使用大量文件作为输入，然后输出所有文件中不同单词的出现次数。
首先，我们考虑处理单个文件的情况，那么程序可以使用一个内存中的数据结构去记录每个单词出现的次数，然后顺序地读取文件内容。如果要处理海量的文件，那么我们需要多台机器，各自并行地处理一部分文件，然后再将多台机器的处理结果合并到一台机器上。为了完成这项工作，程序员需要写很多“管道”代码，比如用于在不同机器上起任务的代码，拉取不同机器的处理结果的代码等等。

上述“管道”代码在实现时，会非常复杂，那么将这些代码单独实现，来让不同的任务复用这些代码是有必要的。

MapReduce 系统就为程序员提供了一套应用，让他们能够专注于实现自己的应用的逻辑，前面提到的管道代码负责的功能都交给了 MapReduce 系统来实现。

#### MapReduce By Example 1: Word Count
MapReduce 系统默认会将输入文件的每一行作为一条记录。对于 Word Count 应用来说，map() 函数会将输入的每个记录分割成单独的单词，然后输出一个形如（word，count）的 pair，count 是单词在 record 中出现的次数。在我们的简化版实现里，map() 只需要输出 count 1，count 后续由 reduce() 函数进行累加。
```txt
"One a penny, two a penny, hot cross buns."
```
对于上述 record，我们的 map() 函数将会输出 
```txt
("One", 1),("a", 1),("penny", 1),("two", 1),("a", 1),("penny", 1),("hot", 1),("cross", 1),("buns", 1)
```
通常来说，map() 函数会为每一条记录输出一个 (key, value) 集合。map() 函数输出的第一个属性 key 被称为 recude key。

MapReduce 系统接收 map() 函数产生（emit）的所有 (key, value) 对，然后以一个特定键将它们排序（or at least, groups them)。所有 key 匹配的记录将会 gather together，然后生成一条新的记录，该记录将所有的 value 作为一个 list 保存。
```txt
("a", [1,1]),("buns", [1]),("cross", [1]),("hot", [1]),("one", [1]),("penny", [1,1]),("two", [1])
```
reduce 函数会将所有的 list 相加。
```txt
("one", 1)("a", 2),("penny", 2),("two", 1),("hot", 1),("cross", 1),("buns", 1)
```
当文件数量变得很多，需要大量机器参与计算过程时，问题会变得复杂，因为处理 map 函数的计算结果无法在一台机器上完成。这就需要我们按照不同的 reduce key 来将 map 的输出结果发送到不同的机器上。这个工作由 shuffle 步骤完成。

#### MapReduce By Example 2: Log Processing
假设我们有一个日志文件，记录了某个网站的访问信息。其内容具有类似如下的结构
```txt
...
2013/02/21 10:31:22.00EST /slide-dir/11.ppt
2013/02/21 10:43:12.00EST /slide-dir/12.ppt
2013/02/22 18:26:45.00EST /slide-dir/13.ppt
2013/02/22 18:26:48.00EST /exer-dir/2.ppt
2013/02/22 20:53:29.00EST /slide-dir/12.ppt
...
```
我们的 log processing 应用的目标是计算，slide-dir 目录下的每个文件，在 2013/01/01 和 2013/01/31 之间被被访问过多少次。将输入文件的每一行作为 record 输入到 map 函数。map 函数将 record 分割成一个个 token，如果日期列在要求的日志范围内，则输出一条结果（filename，1）。shuffle 阶段将所有特定的 reduce key 拍在一起，并且将所有结果组成一个 list，然后 reduce 函数去处理每个 shuffle 得到的数据集。

### Parallel Processing of MapReduce Tasks
MapReduce 系统的设计目标是在多台机器上并行处理任务。Map 函数 Reduce 函数都被作为 task 下发给多台机器，Map 函数的处理结果将会以文件的形式保存，并且以文件的形式发送给 reduce task。MapReduce 支持使用分布式文件系统实现文件的分发。

### SQL on MapReduce
如果数据保存在文件而不是数据库中，并且查询很容易使用 SQL 来表达的话，那么使用 SQL on MapReduce 来进行计算就要比将数据重新导入数据库再用 SQL 查询方便的多。

关系操作可以使用 map 和 reduce 步骤来实现：

* The relational selection operation can be implemented by a single map() function, without a reduce() function.
* The relational group by and aggregate function γ can be implemented using a single MapReduce step: the map() outputs records with the group by attribute values as the reduce key; the reduce() function receives a list of all the attribute values for a particular group by key and computes the required aggregate on the values in its input list.
* 
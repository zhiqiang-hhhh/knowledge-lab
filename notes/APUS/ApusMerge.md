[TOC]

# 云原生的Merge策略

# 问题背景

- 当前Clickhouse的MergeTree引擎会在数据写入之后做Merge，逐渐把小文件合并成大文件；合并成大文件之后，由于数据都是有序的，所以读取的时候能减少读取的文件块的数量，加速查询。通过一些业务方的线上使用来看，即使使用bulk这样的微批导入（比如微信log，每个批次2w条，大概6MB），写放大可以到8倍，调整一系列参数（例如，最大的part大小，每次merge的part数目）之后，也会有4，5倍左右，参见 [微信日志Clickhouse的优化]( https://km.woa.com/group/24938/articles/show/446018?kmref=search&from_page=1&no=1)。由于COS 底层也是类似LSM Tree的结构，所以他们会进一步放大，对磁盘的写放大压力最后是乘数关系。另外，COS 本身对于读写次数也是有收费的，所以在成本上也会有一定的提升。

- COS或者S3 之类的系统的SLA基本在[99.95%](https://cloud.tencent.com/document/product/301/1979)左右，这意味着1w次写入可能就会有5次失败，在Merge的时候如果产生的文件太大，直接写COS 会有失败的风险，失败重试，会带来大量的重复计算，有的时候如果频繁失败还会导致 Too Many Parts的问题。

- 当前只有一个节点参与Merge，在高速导入的情况下可能Merge不过来，需要引入多个副本并行Merge的策略。

# 方案思路

- Clickhouse 中引入一种 VolatilePart，这种 Part 的特点是：
	- 它是由 merge 或者 mutation 产生，insert 不能产生这种 part，insert 只能产生 normal part；
	- volatile part 产生后，由 materialize 方法将其写入到本地磁盘，不会写入到COS，所以它的数据可能丢失；
	- 当 materialized part 被上传到 cos 后，它将会变为 normal part；
	- 所有 normal part 写入的时候直接写入COS；
	- 当读取的时候如果 volatile part 不存在，那么就要从其对应的 source normal part 中读取若干小 part。
  
我们为 volatile part 引入一个新的数据类型：
```c++
struct VolatilePartEntry
{
    using DataPartsVector = MergeTreeData::DataPartsVector;
    using DataPartPtr = MergeTreeData::DataPartPtr;

    VolatilePartEntry() = default;

    VolatilePartEntry(const DataPartPtr & to_part_, const DataPartsVector & from_parts_) : to_part(to_part_), from_parts(from_parts_) { }

    DataPartPtr to_part;
    DataPartsVector from_parts;
};
```
对于 materialized part，其使用方式与 normal part 几乎一致，所以沿用 normal part 的数据类型。这样我们在 StorageShareDiskMergeTree 中将会包含如下 part 相关数据成员：
```c++
class StorageShareDiskMergeTree
{
	class MergeTreeData
	{
		mutable std::mutex data_parts_mutex;
		DataPartsIndexes data_parts_indexes;
		DataPartsIndexes::index<TagByInfo>::type & data_parts_by_info;
		DataPartsIndexes::index<TagByStateAndInfo>::type & data_parts_by_state_and_info;
	};

	std::vector<VolatilePartEntry> volatile_parts;

	MergeTreeData::DataPartsIndexes materialized_parts;
	MergeTreeData::DataPartsIndexes::index<TagByInfo>::type & materialized_parts_by_info;
	MergeTreeData::DataPartsIndexes::index<TagByStateAndInfo>::type & materialized_parts_by_state_and_info;
}
```
所有对内存中 part 信息的操作都需要保证在加 parts_lock 前后，normal parts，volatile parts，以及 materialized parts 三者的逻辑关系保持一致。
为了简便表述，我们称 nparts(normal parts)，vparts(volatile parts), mparts(materialized parts)，三者的并集为大集合，vparts 与 mparts 的集合为小集合。一致的关系具体为：
1. volatile_parts.from_parts 中的每个 parts 必须存在于大集合中
2. mparts 与 vparts 的交集为空
3. 大集合一定是小集合的超集

关系 1 是因为，当 vpart 产生时，它的 source part 一定属于某个节点本地的 nparts + mparts，而 mpart 实际上也是从 vpart 转化来的，那么在其他节点上，当它 replay 一条 add volatile parts 的 log 时，它可能还没有进行过 materialization，那么它看到的 source parts 就可能是 nparts + vparts；
关系 2 是因为 mparts 都是从 vparts 转化来的，一一对应
关系 3 是因为，npart 只有在有 mpart 被 upload 到 cos 之后，才可能被删除，在此之前，nparts 一定存在，同时 nparts 还在不停的接收 insert parts 


**Merge**

原先的 Merge 过程是先在本地 selectPartsToMerge，然后执行 merge，最后通过 addPartAndReplace 将 new_merged_part 添加到 manifest 中。
引入 volatile part 后，整个 merge 流程会产生较大的 改动：
1. selectPartsToMerge 的 source parts 将会是 normal parts 和 materialized part 的并集，由于 materialized part 一定有对应的 normal part，所以实际上结果中将是 materialized part + normal part 中不被 materialized part 包含的部分；
2. 一旦产生了一条 MergeEntry，那么先 commit 一条 add volatile part 类型的 op log，如果 commit 不成功，本次 merge 结束；
3. commit 成功后，原始节点执行 materialization 过程，materialization 与之前的 merge 动作一样
4. materialization 结束后，不再产生 oplog，而是修改内存，将 volatile part 添加到 materialized_part 中，注意，此时不删除 normal parts
5. 后台的 uploader 线程根据一定的规则，选择本地 materialize part，将其上传到 cos
6. upload 过程需要先上传 cos，再添加一条 upsert part log，最后修改内存，如果 commit op log失败，需要将 uploaded part 从 cos 删除
7. upload 成功后，将对应的 normal parts 删除

Merge 过程中比较复杂的地方是：
1. 如何判断当前的 add vpart log 是没有冲突的
2. 内存状态应该如何修改

对于第一个点，由于任何一个节点都可以尝试添加 add vpart log，并且其在创建 add vpart log时内存的状态可能都不一样，因此我们可能需要将判定 log 内容冲突的条件放宽一些。
1. 逐条 compare op log
2. 如果有另一条 add vpart 或者 upsert part，且其 min_block + max_block 覆盖/等于/相交 当前 log 的 vpart，那么本次 commit 需要被放弃

对于第二个点。由于内存修改一定是在成功 commit op log 之后，所以这里我们假设内存状态一定是正确的。
1. add vpart log 只需要添加新元素即可
2. add materialized 需要将对应的 vpart 删除，且添加新的 mpart
3. upload mpart 需要将小集合中对应的 part 以及 nparts 中 covered parts 删除

**Mutation 操作**

- 选择Part列表的时候，从VolatilePart内选择
- 执行的时候，直接写COS，所以生成的全部为Normal Part。
- 判断一个mutation是否执行完毕的时候，要拿出NormalPartsVector来比较判断。

**Grab Old Parts**

- 直接遍历NormalPartsVector


**Read操作**

- 获取VolatilePartVector来操作

**Detach Attach操作**

- 暂时不支持

**Truncate Table操作**



# 实现细节
data_parts 数据结构保存本地处于 active 状态的 normal parts 和 materialized parts

```c++
selectPartsToMaterialize
{
	res;
	for v_part in volatile_parts
	{
		bool can_materialize = true;
		for src_part in v_part.src_parts
		{
			if !data_parts.contains(src_part) || partIsBeingMergedMutated(src_pars)
			{
				can_materialize = false;
				break;
			}
		}
		if(can_materialize)
		{
			for (src_part in v_part.src_parts)
				tagPartBeingMergedMutated(src_part);
			
			res.push_back(v_part);
		}
	}
	return res;
}
```
materialized part 一定是本地 materialize 或者进程启动时 load 进来的。
mpart 需要 replace 的 part 可以是 normal parts 以及 meterialized parts。如果不是在loadDataParts时调用的该函数，那么m_part的origin_vpart一定还存在内存中，需要将该vpart删除。在将mpart添加到内存中时，需要被它覆盖的parts全部replace，normal parts不能被删除（还未被upload），mparts需要从本地磁盘删除。在产生snapshot时，
```c++
addMaterializedPart(m_part, is_load)
{
	parts_to_replace = getDataPartsToReplace(m_part);

	if (!is_load)
	{
		origin_vpart = getVolatilePart(m_part->uuid);
		assert(origin_vpart != nullptr);

		volatile_parts.erase(origin_vpart);
	}
	
	for (part : parts_to_replace)
	{
		data_parts.erase(part);
		if (part.isStoredOnRemote())
		{
			replaced_normal_parts.insert(part);
		}
		else
		{
			part.remove();
		}
	}
}
```


## PartRemove

### MergeTreeData::grabOldParts
```c++
MergeTreeData::DataPartsVector MergeTreeData::grabOldParts(bool force)
{
    DataPartsVector res;

    /// A
    /// If the method is already called from another thread, then we don't need to to anything.
    std::unique_lock lock(grab_old_parts_mutex, std::defer_lock);
    if (!lock.try_lock())
        return res;
    
    time_t now = time(nullptr);
    std::vector<DataPartIteratorByStateAndInfo> parts_to_delete;

    {
        auto parts_lock = lockParts();
        auto outdated_parts_range = getDataPartsStateRange(DataPartState::Outdated);

        for (auto it = outdated_parts_range.begin(); it != outdated_parts_range.end(); ++it)
        {
            const DataPartPtr & part = *it;

            auto part_remove_time = part->remove_time.load(std::memory_order_relaxed);

            /// B
            if (part.unique() && /// Grab only parts that are not used by anyone (SELECTs for example).
                ((part_remove_time < now &&
                now - part_remove_time > getSettings()->old_parts_lifetime.totalSeconds())
                || force /// C
                || isInMemoryPart(part))) /// Remove in-memory parts immediately to not store excessive data in RAM
            {
                parts_to_delete.emplace_back(it);
            }
        }

        res.reserve(parts_to_delete.size());
        for (const auto & it_to_delete : parts_to_delete)
        {
            res.emplace_back(*it_to_delete);
            /// D
            modifyPartState(it_to_delete, DataPartState::Deleting);
        }
    }

    if (!res.empty())
        LOG_TRACE(log, "Found {} old parts to remove.", res.size());

    return res;
}
```
* A 
  通过尝试对 grab_old_parts_mutex 加锁判断是否有其他线程正在执行 grabOldParts 函数。

* B 
  DataPartPtr 是 shared_ptr 类型，通过其引用计数判断当前 part 是否被其他线程使用。
  这里之所以可以使用 unique 方法，是因为在前面已经配合使用了 grab_old_parts_mutex，排除了了 shared_ptr.unique 方法在多线程下可能出现的[判断错误问题](https://zhuanlan.zhihu.com/p/337294239)。
  如果 part 没有被其他线程使用，且 part 删除时间已经过期，且过期时长超过 old_parts_lifetime，则可以将 part 删除。

* C
  `force` 为 true，会无视 part 是否在当前线程为 unique。也就是说，如果有 Select 正在使用该 part，则依然会将 part 添加到 parts_to_delete 中。
  

* D
  将所有的过期 part 状态设置为 Deleting

```c++
size_t MergeTreeData::clearOldPartsFromFilesystem(bool force)
{
    DataPartsVector parts_to_remove = grabOldParts(force);
    clearPartsFromFilesystem(parts_to_remove);
    removePartsFinally(parts_to_remove);

    /// This is needed to close files to avoid they reside on disk after being deleted.
    /// NOTE: we can drop files from cache more selectively but this is good enough.
    if (!parts_to_remove.empty())
        getContext()->dropMMappedFileCache();

    return parts_to_remove.size();
}

void MergeTreeData::clearPartsFromFilesystem(const DataPartsVector & parts_to_remove)
{
    const auto settings = getSettings();
    if (parts_to_remove.size() > 1 && settings->max_part_removal_threads > 1 && parts_to_remove.size() > settings->concurrent_part_removal_threshold)
    {
        /// Parallel parts removal.

        size_t num_threads = std::min<size_t>(settings->max_part_removal_threads, parts_to_remove.size());
        ThreadPool pool(num_threads);

        /// NOTE: Under heavy system load you may get "Cannot schedule a task" from ThreadPool.
        for (const DataPartPtr & part : parts_to_remove)
        {
            pool.scheduleOrThrowOnError([&, thread_group = CurrentThread::getGroup()]
            {
                if (thread_group)
                    CurrentThread::attachToIfDetached(thread_group);

                LOG_DEBUG(log, "Removing part from filesystem {}", part->name);
                part->remove();
            });
        }

        pool.wait();
    }
    else
    {
        for (const DataPartPtr & part : parts_to_remove)
        {
            LOG_DEBUG(log, "Removing part from filesystem {}", part->name);
            part->remove();
        }
    }
}

void MergeTreeData::removePartsFinally(const MergeTreeData::DataPartsVector & parts)
{
    {
        auto lock = lockParts();

        /// TODO: use data_parts iterators instead of pointers
        for (const auto & part : parts)
        {
            /// A
            /// Temporary does not present in data_parts_by_info.
            if (part->getState() == DataPartState::Temporary)
                continue;

            auto it = data_parts_by_info.find(part->info);
            if (it == data_parts_by_info.end())
                throw Exception("Deleting data part " + part->name + " doesn't exist", ErrorCodes::LOGICAL_ERROR);

            (*it)->assertState({DataPartState::Deleting});

            data_parts_indexes.erase(it);
        }
    }

    /// Data parts is still alive (since DataPartsVector holds shared_ptrs) and contain useful metainformation for logging
    /// NOTE: There is no need to log parts deletion somewhere else, all deleting parts pass through this function and pass away

    auto table_id = getStorageID();
    if (auto part_log = getContext()->getPartLog(table_id.database_name))
    {
        PartLogElement part_log_elem;

        part_log_elem.event_type = PartLogElement::REMOVE_PART;

        const auto time_now = std::chrono::system_clock::now();
        part_log_elem.event_time = time_in_seconds(time_now);
        part_log_elem.event_time_microseconds = time_in_microseconds(time_now);

        part_log_elem.duration_ms = 0; //-V1048

        part_log_elem.database_name = table_id.database_name;
        part_log_elem.table_name = table_id.table_name;

        for (const auto & part : parts)
        {
            part_log_elem.partition_id = part->info.partition_id;
            part_log_elem.part_name = part->name;
            part_log_elem.bytes_compressed_on_disk = part->getBytesOnDisk();
            part_log_elem.rows = part->rows_count;

            part_log->add(part_log_elem);
        }
    }
}

```
在 MergeTree 中，首先尝试多线程将 part 从本地磁盘删除。然后尝试将 part 从内存中最后删除。

* A
  从这行注释可以对 Temporary part 有更深的理解：它们不会被添加到 data_parts_indexes 中。

```c++

```
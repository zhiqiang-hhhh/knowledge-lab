```plantuml
class PageCacheHandle {
    - _cache : LRUCachePolicy*
    - _handle : Cache::Handle*
}

PageCacheHandle *-- LRUCachePolicy

class CachePolicy {

}

LRUCachePolicy -up-> CachePolicy
LRUCachePolicy *-- Cache
class LRUCachePolicy {
    _cache : std::shared_ptr<Cache>
    _lru_cache_type : LRUCacheType
    + Cache::Handle* insert(const CacheKey& key, void* value, size_t charge,
                          size_t value_tracking_bytes,
                          CachePriority priority = CachePriority::NORMAL) 
}

interface Cache {
    {abstract} lookup(CacheKey) : Handle*
    {abstract} insert(CacheKey, void* data, size_t charge) : Handle*
}

LRUCachePolicyTrackingAllocator -up-> LRUCachePolicy
LRUCachePolicyTrackingManual -up-> LRUCachePolicy

DataPageCache -up-> LRUCachePolicyTrackingAllocator
IndexPageCache -up-> LRUCachePolicyTrackingAllocator
PKIndexPageCache -up-> LRUCachePolicyTrackingAllocator

class StoragePageCache {
    - _data_page_cache : DataPageCache*
    - _index_page_cache : IndexPageCache*
    - _pk_index_page_cache : PKIndexPageCache*
}

StoragePageCache *-- DataPageCache
StoragePageCache *-- IndexPageCache
StoragePageCache *-- PKIndexPageCache

ShardedLRUCache -up-> Cache
ShardedLRUCache *-- LRUCache
class ShardedLRUCache {
    _shards : LRUCache**
}

class LRUCache {
    - _table : HandleTable
    - _lru_normal : LRUHandle
    + insert(CacheKey, uint32_t hash, void* value, size_t charge) : Cache::Handle
}

LRUCache *-- LRUHandle

class LRUHandle {
    - _value : LRUCacheValueBase*
}

LRUHandle *-- LRUCacheValueBase

class LRUCacheValueBase {

}

ScahemaCache_CacheValue -left-> LRUCacheValueBase
SegmentCache_CacheValue -left-> LRUCacheValueBase

SegmentCache -up-> LRUCachePolicy
SegmentCache *-- LRUCacheValueBase
```
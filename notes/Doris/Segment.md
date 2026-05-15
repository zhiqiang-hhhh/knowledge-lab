```cpp
class Segment {
    ...
    std::map<int32_t, std::unique_ptr<ColumnReader>> _column_readers;
}

class ColumnReader {
    IndexReaderPtr _index_reader;
}
```


```text
SegmentIterator::_init_index_iterator() {
    for (cid : _schema->column_ids()) {
        _index_iterators[cid] = _segment->new_index_iterator(...)
    }
}
```

```text
Segment::new_index_iterator
    |
    |-_create_column_reader_once
        |
        |-_get_segment_footer
        |
        |-_create_column_readers
            |
            // 遍历 tablet schema 里面的所有列，为所有列创建 column reader
            // 无论这个列是否被当前 sql 使用到
            for (column : _tablet_schema.columns())
            {
                _column_readers.emplace(column.unique_id(), std::move(reader));
            }
```
内存中的ANN索引是属于 AnnIndexIterator 的，为了节省内存防止重复的 load index，我们不能把索引对象的所有权交给 AnnIndexIterator，因为一旦 Segment 对象被重新构造，那么就会导致 Ann 索引被重新加载。

什么时候 Segment 对象会被重新构造？Segment对象有缓存么。
```cpp
FlushToken::_do_flush_memtable () {
    ...
    std::unique_ptr<vectorized::Block> block;
    RETURN_IF_ERROR(memtable->to_block(&block));
    RETURN_IF_ERROR(_rowset_writer->flush_memtable(block.get(), segment_id, flush_size));
    ...
}

BetaRowsetWriterV2::flush_memtable {
    ...
    RETURN_IF_ERROR(_segment_creator.flush_single_block(block, segment_id, flush_size));
    ...
}

SegmentCreator::flush_single_block {
    RETURN_IF_ERROR(_segment_flusher.flush_single_block(block, segment_id, flush_size));
}


SegmentFlusher::flush_single_block {
    ...
    RETURN_IF_ERROR(_create_segment_writer(writer, segment_id, no_compression));
    RETURN_IF_ERROR_OR_CATCH_EXCEPTION(_add_rows(writer, &flush_block, 0, flush_block.rows()));
    RETURN_IF_ERROR(_flush_segment_writer(writer, flush_size));
}

SegmentFlusher::_add_rows {
    RETURN_IF_ERROR(segment_writer->batch_block(block, row_offset, row_num));
    RETURN_IF_ERROR(segment_writer->write_batch());
}

VerticalSegmentWriter::write_batch() {
    for (uint32_t cid = 0; cid < _tablet_schema->num_columns(); ++cid) {
        RETURN_IF_ERROR(
                _create_column_writer(cid, _tablet_schema->column(cid), _tablet_schema));
    }
}
```
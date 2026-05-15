```cpp
Status OlapScanLocalState::hold_tablets() {
    ...
    _tablets.resize(_scan_ranges.size());

    ...
    for (size_t i = 0; i < _scan_ranges.size(); i++) {
            int64_t version = 0;
            std::from_chars(_scan_ranges[i]->version.data(),
                            _scan_ranges[i]->version.data() + _scan_ranges[i]->version.size(),
                            version);
            auto tablet = DORIS_TRY(ExecEnv::get_tablet(_scan_ranges[i]->tablet_id));
            _tablets[i] = {std::move(tablet), version};
        }
}


Status ParallelScannerBuilder::_build_scanners_by_rowid(std::list<ScannerSPtr>& scanners) {
    for (auto&& [tablet, version] : _tablets) {

    }
}
```

```cpp
BetaRowsetReader::get_segment_iterators(...) {
    ...
    _read_options.version = _rowset->version();
}

```

## schema change

分为 heavy schema change 和 light schema change。

hsc 会生成新的 tablet（新的 tablet id，新的 schema hash）。

lsc 不会生成新的 tablet，直接在 fe 更新内存以及 fe 中持久化的 meta。当查询/导入行为发生时，fe 会在 plan 中带上新的 schema，当 be 接收到新的 schema 之后会更新 be 内存中的数据结构。
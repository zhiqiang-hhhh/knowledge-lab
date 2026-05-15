```plantuml
class IndexBuilder {
    - map<pair<segment_id, index_id>, IndexColumnWriter>
    - map<int64_t, unique_ptr<XIndexFileWriter>> _x_index_file_writers; 
}

class XIndexFileWriter {}

IndexBuilder *-- XIndexFileWriter
```

```plantuml
interface IMergeTreeDataPartWriter
{
    - data_part : DataPart
    - storage : MergeTreeData
    + {abstract} write(Block) : void
}

IMergeTreeDataPartWriter <-- MergeTreeDataPartWriterOnDisk

interface MergeTreeDataPartWriterOnDisk

MergeTreeDataPartWriterOnDisk <-- MergeTreeDataPartWriterWide

class MergeTreeDataPartWriterWide
{
    + write(Block) : void
}

interface IMergedBlockOutputStream
{
    # writer : IMergeTreeDataPartWriter
    + {abstract} write(Block) : void
}

IMergedBlockOutputStream <--  MergedBlockOutputStream



IMergedBlockOutputStream *-- IMergeTreeDataPartWriter


```

<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [ColumnConst](#columnconst)
- [ColumnNullable](#columnnullable)
- [Methods](#methods)
  - [Scatter](#scatter)

<!-- /code_chunk_output -->

## ColumnConst
## ColumnNullable

/// Class that specifies nullable columns. A nullable column represents
/// a column, which may have any type, provided with the possibility of
/// storing NULL values. For this purpose, a ColumNullable object stores
/// an ordinary column along with a special column, namely a byte map,
/// whose type is ColumnUInt8. The latter column indicates whether the
/// value of a given row is a NULL or not. Such a design is preferred
/// over a bitmap because columns are usually stored on disk as compressed
/// files. In this regard, using a bitmap instead of a byte map would
/// greatly complicate the implementation with little to no benefits.

ColumnNullable 的注释很清晰了，ColumnNullable 包含两个列，一个普通列，一个 ColumnUInt8，后者用于指示前者的哪些行是 NULL。



## Methods
### Scatter

遍历当前列的每一行，按照某个规则将每一行都 scatter(散射) 到结果 `vector<IColumn::MutablePtr>` 的某一个位置。
比如举个例子，有一个列中的元素都为整数，内容是这样的一个向量
```txt
[1,2,3,4,5,6,7,8,9,10]
```
现在希望将这个列的元素按照某个规则进行重新分类，得到一个 `vector<IColumn::MutablePtr>`，结果的第一个列中只包含原始列中小于 5 的行，第二个列中只包含大于等于 5 的偶数，第三个列是大于等于 5 的奇数。

为了实现我们的目的，我们需要一个 selector 数组，对原始 column 使用 selector 进行 scatter 之后，我们可以得到我们想要的结果。selector 数组的作用是用来描述输入对应的行应当被保存到输出结果的哪一行中。
```
column  selector    result[0]   result[1]   result[2]
1       0           1           6           5
2       0           2           8           7
3       0           3           10          9
4       0           4
5       2           
6       1           
7       2
8       1
9       2
10      1
```

```cpp
using ColumnIndex = UInt64;
using Selector = PaddedPODArray<ColumnIndex>;

template <typename Derived>
std::vector<IColumn::MutablePtr> IColumn::scatterImpl(ColumnIndex num_columns,
                                             const Selector & selector) const
{
    size_t num_rows = size();

    if (num_rows != selector.size())
        throw Exception(...);
    
    std::vector<MutablePtr> columns(num_columns);
    for (auto & column : columns)
        column = cloneEmpty();

    {
        size_t reserve_size = static_cast<size_t>(num_rows * 1.1 / num_columns);    /// 1.1 is just a guess. Better to use n-sigma rule.

        if (reserve_size > 1)
            for (auto & column : columns)
                column->reserve(reserve_size);
    }

    for (size_t i = 0; i < num_rows; ++i)
        static_cast<Derived &>(*columns[].insertFrom(*this, i));

    return columns;
}
```
scatter 的核心操作就是这一行：
```cpp
for (size_t i = 0; i < num_rows; ++i)
    static_cast<Derived &>(*columns[selector[i]].insertFrom(*this, i));
```
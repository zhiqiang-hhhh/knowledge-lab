```plantuml
class PaddedPODArray
class DecimalPODArray {
    + DecimalPODArray(size, scale)
    + get_scale() : UInt32
    - scale : UInt32
}

DecimalPODArray -up-> PaddedPODArray

ColumnDecimal *-right- DecimalPODArray
ColumnDecimal -up-> COWHelper
class ColumnDecimal {
    + ColumnDecimal(size, scale)
}

struct Decimal {
    
}

```
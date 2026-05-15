[TOC]

# Apache Arrow
Apache Arrow 开创了一种对列存数据的内存中的统一表示格式。这种内存格式可以被高效地用于在支持 SIMD 的 CPU 上进行数据的向量化处理。
标准化的内存数据格式的好处：
* High-level language 通过将指向数据的指针传递给 Rust 或者 C++ 代码，就可以实现更加高效的数据处理工作。减少数据拷贝。
* 无需序列化的代价，数据便可以在不同的进程之间传递。

# Choosing a Type System
构建一个查询引擎的第一步是构建一个类型系统，用于表示不同的数据类型。
## Row-Based or Columnar?
Query engine 是一行一行地处理数据还是列式处理数据。现今很多查询引擎都是基于火山查询计划的，火山查询计划中的每个步骤中，物理计划将会在数行数据上进行迭代。这种模型实现起来比较简单，但是当行数比较多时，per-row overheads 将会变得非常大。这种代价可以通过把按行迭代改为按 batch 迭代来降低，不过，如果能够将一个 batch 中的数据都由行式数据转为列式数据，那么我们就可以使用“向量化”（vectorized processing）技术，利用 SIMD（Same Instruction Multiple Data) 来在一条 CPU 指令里处理多条数据。甚至在未来可以考虑使用 GPU 来处理这些数据。

## Interoperability
是否支持用户使用其他语言访问查询引擎。

## Type System
使用 Apache Arrow 作为系统类型的基础。在 Apache Arrow 之上抽象出了下面的类

* Schema provides meta data for a data source or the results from a query. A schema consists of one or more fields.
* Field provides the name and data type for a field within a schema.
* FieldVector provides columnar storage for data for a field.
* ArrowType represents a data type.

# Data Sources
## Data Source Interface
在查询规划期间，我们需要知道数据源的 schema，这样查询计划才能够确定目标列存在，并且数据类型是相互兼容的。在有些情况下，我们可能无法获得数据源的 schema，因为数据源本身可能没有固定的 schema，这种数据源被称为是“schema-less"，比如 JSON 文档。

在查询执行期间我们需要从数据源获取数据，并且需要说明我们要将哪些列夹在进内存。

## Dataa Source Examples
* Comma-Separated Values(CSV)
  文本文件，一条记录一行，每个字段用逗号分开。CSV 文件不包含任何的 schema 信息。
* Parquet
  Parquet 的作用是提供压缩后的，高效的，列存数据表达方式，并且是一种 Hadoop 生态系统下非常流行的文件格式。
  Parquet files contain schema information and data is stored in batches (referred to as “row groups”) where each batch consists of columns.
* Orc
  Optimized Row Columnar (ORC) 格式与 Parquet 文件类似。数据以 columnar batch 为单位保存，每个存储单位称为 stripes

# Logical Plans & Expressions

A logical plan represents a relation (a set of tuples) with a known schema.

## Logical Expressions

构成一个 logical plan 的最重要的基本组件是 logical expression。一些 logical expression 的例子：
|Expression|Examples|
|--|--|
|Literal Value|"hello", 12.34|
|Column Reference|user_id,first_name|
|Math Expression|salary * state_tax|
|Comparison Expression|x >= y|
|Boolean Expression|birthday = today() AND age >= 21|
|Aggregate Expression|MIN(salary),MAX(salary),SUM(salary),AVG(salary),COUNT(*)|
|Scalar Function|CONCAT(first_name, "", last_name)|
|Aliased Expression|salary * 0.02 AS pay_increase|

对于一个 logical expression 来说，它必须具备以下的属性：
1. name，这样其他的 expression 才能引用它；
2. data type of the values that the expression will produce when evaluated.


When we are planning queries we will need to know some basic meta-data about the output of an expression. Specifically we need to have a name for the expression so that other expressions can reference it and we need to know the data type of the values that the expression will produce when evaluated so that we can validate that the query plan is valid.

### Column Expressions

column expression：简单来说可以理解为访问某个列。但是，这里的“列”不光可以指 column in a data source，也可以指 a column produced by the input logical plan or it could represent the result of an expression being evaluated against other inputs.


### Literal Expressions
字面值表达式。

### Binary Expressions
 Expressions that take two inputs. 包括有：comparision expression, boolean expressions and math expressions. 

#### Comparison Expressions
#### Boolean Expressions
#### Math Expressions

### Aggregate Expressions
Aggregate expressions perform an aggregate function such as MIN, MAX, COUNT, SUM, or AVG on an input expression.


### Logical Plans
#### Scan
The Scan logical plan represents fetching data from a DataSource with an optional projection. Scan is the only logical plan in our query engine that does not have another logical plan as an input. It is a leaf node in the query tree.

#### Projection 
A projection is a list of expressions to be evaluated against the input data. 
```sql
# simple
SELECT a, b, c from foo

# complex
SELECT (CAST(a AS folat) * 3.1415926) AS my_float FROM foo
```

#### Selection
Apply a filter expression to detemine which rows should be selected in its output. 对应 sql 中的 where 子句

#### Aggregate

# Building Logical Plans
执行如下 sql，数据源是一个 CSV 文件，其中包含如下列：id, first_name, last_name, state, job_title, salary.
```sql
SELECT * FROM employee WHERE state = 'CO'
```
一种方式是，我们直接针对该 sql 写代码，构造一个 logical plan：
```
val plan = Projection(
  Selection(
  Scan("employee", CsvDataSource("employee.csv"), listOf()),
  Eq(Column(3), LiteralString("CO"))
  ),
  listOf(Column("id"),
  Column("first_name"),
  Column("last_name"),
  Column("state"),
  Column("salary"))
)
println(format(plan))
```
不便于理解。

better: data frames

# Physical Plans & Expressions
```kotlin
interface Expression {
  func evaluate(input: RecordBatch) : ColumnVector
}
```
## Comlumn Expression
```kotlin
class ColumnExpression(val i : Int) : Expression {
  override fun evaluate(input: RecordBatch): ColumnVector {
    return input.field(i)
  }

  override fun toString(): String {
    return "#$i"
  }
}
```

### Aggregate Expressions
Complex.

Aggregate values from multiple batches of data and then produce final value.
```kotlin
interface AggregateExpression {
  fun inputExpression() : Expression
  fun createAccumulator : Accumulator
}

interface Accumulator {
  fun accumulate(value : Any?)
  fun finalValue() : Any?
}

class MaxExpression(private val expr : Expression) : AggregateExpression {
  override fun inputExpression() : Expression {
    return expr
  }

  override func createAccumulator() : Accumulator {
    return MaxAccumulator()
  }

  override fun toString() : String {
    return "MAX($expr)"
  }
}

clas MaxAccumulator : Accumulator {
  var value: Any? = null

  override fun accumulate(value: Any?) {
    if (value != null) {
      if (this.value == null) {
        this.value = value
      } else {
        val isMax = when(value) {
          is Byte -> value > this.value as Byte
          is Shot -> value > this.value as Short
          is Int -> value > this.value as Int
          is Long -> value > this.value as Long
          
        }
      }
    }
  }
}

```

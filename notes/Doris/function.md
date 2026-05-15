```plantuml
interface IFunctionBase {
    + {abstract} get_argument_types()
    + {abstract} get_return_type()
    + {abstract} prepare(FunctionContext, Block, ColumnNumbers, ResultIndex) : PreparedFunctionPtr
    + {abstract} open(FunctionContext, FunctionStateScope) : Status
    + {abstract} execute(FunctionContext, Block, ColumnNumbers, ResultIndex, InputRowsCount) : Status
    + {abstract} close(FunctionContext, FunctionStateScope) : Status
}

interface IFunctionBuilder {
    + {abstract} is_variadic() : bool
    + {abstract} get_number_of_arguments() : size_t
    + {abstract} build(ColumnsWithTypeAndName, DataTypePtr return_type) : FunctionBasePtr
    + {abstract} get_variadic_argument_types() : DataTypes
    + {abstract} get_arguments_that_are_always_constant() : ColumnNumbers
}

DefaultFunction -up-> IFunctionBase
FunctionBuilderImpl -up-> IFunctionBuilder

class FunctionBuilderImpl {
    + build(ColumnsWithTypeAndName, DataTypePtr return_type) : FunctionBasePtr
    # {abstract} build_impl(ColumnsWithTypeAndName, DataTypePtr return_type) : FunctionBasePtr
}

DefaultFunctionBuilder -up-> FunctionBuilderImpl
class DefaultFunctionBuilder {
    # build_impl(ColumnsWithTypeAndName, DataTypePtr) : FunctionBasePtr
}

IFunction -up-> IFunctionBase
IFunction -up-> FunctionBuilderImpl
IFunction -up-> PreparedFunctionImpl

FunctionRounding -up-> IFunction
```

```plantuml
class SimpleFunctionFactory {
    + register_function(const std::string& name, std::function<FunctionBuilderPtr()>) : void
    + register_function<Function>() : void
    + register_function<Function>(std::string name) : void
}
```

round 函数注册：
```cpp
// round.cpp
factory.register_function<                                                                   
            FunctionRounding<IMPL<TruncateName>, RoundingMode::Trunc, TieBreakingMode::Auto>>();

class SimpleFunctionFactory {
template <class Function>
    void register_function() {
        if constexpr (std::is_base_of<IFunction, Function>::value) {
            register_function(Function::name, &createDefaultFunctionBuilder<Function>);
        } else {
            register_function(Function::name, &Function::create);
        }
    }
}
```
FunctionRounding 继承自 IFunction，所以我们会为它创建一个默认的 builder
```cpp
class SimpleFunctionFactory {
template <typename Function>
    static FunctionBuilderPtr createDefaultFunctionBuilder() {
        return std::make_shared<DefaultFunctionBuilder>(Function::create());
    }
}

class DefaultFunctionBuilder : public FunctionBuilderImpl {
public:
    explicit DefaultFunctionBuilder(std::shared_ptr<IFunction> function)
            : _function(std::move(function)) {}
    ...           
}
```
SimpleFunctionFactory 的 builder map ，字符串作为 Key，Value 为 `std::shared_ptr<DefaultFunctionBuilder>`，字符串为 `函数名 + 参数名`

可以在 FunctionRounding 中获取到返回值类型为 

```cpp
// be/src/vec/data_types/data_type_decimal.cpp
DataTypePtr create_decimal(UInt64 precision_value, UInt64 scale_value, bool use_v2) {
if (precision_value <= max_decimal_precision<Decimal32>()) {
        return std::make_shared<DataTypeDecimal<Decimal32>>(precision_value, scale_value);
    } else if (precision_value <= max_decimal_precision<Decimal64>()) {
        return std::make_shared<DataTypeDecimal<Decimal64>>(precision_value, scale_value);
    } else if (precision_value <= max_decimal_precision<Decimal128V3>()) {
        return std::make_shared<DataTypeDecimal<Decimal128V3>>(precision_value, scale_value);
    }
}
```
不同的 client 通过不同的 port 链接到 ck server
不同的 port 对应不同的 handler
在不同的 handler 里，为每个创建的链接创建一个 session，创建 session 的时候指定 output format，mysql 有 MySQLOutputFormat
所有的 hander 都会执行 executeQuery 函数，这个函数里统一创建一个 out put stream，这个 output stream决定最终结果用哪个形式输出，代码片段：
```cpp
WriteBuffer * out_buf = &ostr;
if (ast_query_with_output && ast_query_with_output->out_file)
{
    if (!allow_into_outfile)
        throw Exception(ErrorCodes::INTO_OUTFILE_NOT_ALLOWED, "INTO OUTFILE is not allowed");

    const auto & out_file = typeid_cast<const ASTLiteral &>e(*ast_query_with_output->out_file).value.safeGet<std::string>();

    std::string compression_method;
    if (ast_query_with_output->compression)
    {
        const auto & compression_method_node = ast_query_with_output->compression->as<ASTLiteral &>();
        compression_method = compression_method_node.value.safeGet<std::string>();
    }

    compressed_buffer = wrapWriteBufferWithCompressionMethod(
        std::make_unique<WriteBufferFromFile>(out_file, DBMS_DEFAULT_BUFFER_SIZE, O_WRONLY | O_EXCL | O_CREAT),
        chooseCompressionMethod(out_file, compression_method),
        /* compression level = */ 3
    );
}

String format_name = ast_query_with_output && (ast_query_with_output->format != nullptr)
                        ? getIdentifierName(ast_query_with_output->format)
                        : context->getDefaultFormat();

auto out = FormatFactory::instance().getOutputFormatParallelIfPossible(
    format_name,
    compressed_buffer ? *compressed_buffer : *out_buf,
    materializeBlock(pipeline.getHeader()),
    context,
    output_format_settings);
```
这样所有的client都被视为是一种特别的OUTPUT FORMAT，这样就跟 select xx from xx OUTPUT yyy 这样的语句能够
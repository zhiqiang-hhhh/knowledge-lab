
<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [Sink](#sink)
    - [OLAPTableSink](#olaptablesink)
      - [TabletWriter](#tabletwriter)
      - [try_close & close](#try_close--close)

<!-- /code_chunk_output -->

# Sink

```plantuml
@startuml
class PipelineTask {
    - _pipeline : PipelinePtr
    - _operators : Operators
    - _source: Operator
    - _root : Operatpr
    - _sink : Operator
}

class DataSinkOperator extends OperatorBase
class StreamingOperator extends OperatorBase
class SourceOperator extends StreamingOperator
class ExchangeSourceOperator extends SourceOperator
class ExchangeSinkOperator implements DataSinkOperator
class ResultFileSinkOperator implements DataSinkOperator
class VExchangeNode implements ExecNode
class AsyncWriterSink implements DataSink
class VResultFileSink implements AsyncWriterSink
class VDataStreamSender implements DataSink
class VFileResultWriter implements AsyncResultWriter
class VMysqlTableWriter implements AsyncResultWriter
class VOdbcTableWriter implements AsyncResultWriter
class VJdbcTableWriter implements AsyncResultWriter
class VTabletWriter implements AsyncResultWriter
class AsyncResultWriter extends ResultWriter
class VOlapTableSink implements AsyncWriterSink
class VOdbcTableSink implements AsyncWriterSink
class VMysqlTableSink implements AsyncWriterSink
class VJdbcTableSink implements AsyncWriterSink


PipelineTask *-- OperatorBase
ExchangeSinkOperator *-- ExchangeSinkBuffer
VDataStreamSender *-- BlockSerializer
VExchangeNode *-- VDataStreamRecvr
VDataStreamRecvr *-- SenderQueue
ResultFileSinkOperator *-- VResultFileSink
ExchangeSinkOperator *-- VDataStreamSender 
ExchangeSourceOperator *-- VExchangeNode
VResultFileSink *-- VFileResultWriter
VMysqlTableSink *-- VMysqlTableWriter
VOdbcTableSink *-- VOdbcTableWriter
VJdbcTableSink *-- VJdbcTableWriter
VOlapTableSink *-- VTabletWriter

interface OperatorBase {
    + {abstract} is_sink() : bool
    + {abstract} is_source() : bool
    + {abstract} init(TSink) : Status
    + {abstract} prepare(RuntimeState*) : Status
    + {abstract} open(RuntimeState*) : Status
    + {abstract} get_block(RuntimeState*, Block*, SourceState&) : Status
    + {abstract} sink(RuntimeState*, Block*, SourceState) : Status
    + {abstract} is_pending_finish() : bool
    + {abstract} close(RuntimeState*) : Status
    + {abstract} try_close(RuntimeState) : Status
    + {abstract} is_close() : bool
    + {abstract} can_write() : bool
    + {abstract} can_read() : bool
    - _child : OperatorPtr
}

interface DataSinkOperator <<DataSinkType>> {
    - _sink : DataSinkType*
    + prepare(RuntimeState*) : Status
    + open(RuntimeState*) : Status
    + sink(RUntimeState, Block* SourceState) : Status
    + try_close(RuntimeState*) : Status
    + close(RuntimeState*) : Status
}

class ResultFileSinkOperator <VResultFileSink> {
    - _sink : VResultFileSink
    + can_write() : bool
}

class ExchangeSinkOperator <VDataStreamSender> {
    - _sink : VDataStreamSender
}

class ExchangeSinkBuffer {
    + register_sink(TUID) : void
    + add_block(TransmitInfo) : Status
    + add_block(BroadcastTransmitInfo) : Status
    + can_write() : bool
    + is_pending_finish() : bool
    + set_should_stop() : void
}

interface DataSink {
    # _closed : bool
    # _row_desc : RowDescriptor
    + {static} create_data_sink(...) : Status
    + {abstract} init(RuntimeState*) : Status
    + {abstract} prepare(RuntimeState*) : Status
    + {abstract} open(RuntimeState*) : Status
    + {abstract} send(RuntimeState*, Block*, eos) : Status
    + {abstract} sink(RuntimeState*, Block*, eos) : Status
    + {abstract} try_close(RuntimeState*, exec_status) : Status
    + {abstract} is_close_done() : bool
    + {abstract} close(RuntimeState*, exec_status) : Status
}

class VDataStreamSender {
    - _channels : vector<Channel<VDataStreamSender>*>
    - _serializer : BlocKSerializer<VDataStreamSender>
    - _broadcast_pb_blocks : BroadcastPBlockHolderQueuePtr
}

class BlockSerializer {
    - _mutable_block : MutableBlockPtr
    - _is_local : bool
    + next_serialized_block(Block* src, PBlock* dest, int num_receivers, bool* serialized, bool eos, vector<size_t>* rows) : Status
    + serialize_block(PBlock* dest, nt num_receivers = 1) : Status
    + serialize_block(const Block* src, PBlock* dest, int num_receivers = 1) : Status
    + get_block() : MutableBlock*
}

interface StreamingOperator <<ExecNodeType>> {
    - _node : ExecNodeType
    + {abstract} close(RuntimeState*) : Status
}

interface SourceOperator <<ExecNodeType>> {
    + {abstract} get_block(RuntimeState*, Block*, SourceState&) : Status
}

class ExchangeSourceOperator <VExchangeNode> {
    + {abstract} can_read() : bool
    + {abstract} is_pending_finish() : bool
}

interface ExecNode {
    + {abstract} init(TPlanNode&, RuntimeState*) : Status
    + {abstract} prepare(RuntimeState*) : Status
    + {abstract} alloc_resource(RuntimeState*) : Status
    + {abstract} open(RuntimeState*) : Status
    + {abstract} get_next(RuntimeState*, Block*, bool* eos) : Status
    + {abstract} release_resource(RuntimeState*) : void
    + {abstract} collect_query_statistics(QueryStatistics* statistics) : Status
    + {abstract} close(RuntimeState* state) : Status
    - _children : vector<ExecNode>
}

class VExchangeNode {
    - _stream_recvr : VDataStreamRecvr
    - _is_merging : bool
    - _num_senders : int
    - _is_ready: bool
}

note "A VExchange only has one VDataStreamRecvr" as N0
VExchangeNode .. N0
N0 .. VDataStreamRecvr

class VDataStreamRecvr {
    - _send_queue_pool : ObjectPool
    - _sender_queues : vector<SenderQueue*>
}

note "A VExchange may have multiple \n SenderQueue (eg. MergeExchange)" as N1
VDataStreamRecvr .. N1
N1 .. SenderQueue
class SenderQueue {
    - _recvr : VDataStreamRecvr
}

class AsyncWriterSink <<WriterType>> {
    # _writer : WriterTypePtr
    + init(TDataSink)
    + prepare(RuntimeState*) : Status
    + open(RuntimeState*) : Status
    + send(RuntimeState*, Block*, eos) : Status
    + sink(RuntimeState*, Block*, eos) : Status
    + can_write() : bool
    + close(RuntimeState*, exec_status) : Status
    + try_close(RuntimeState*, exec_status) : Status
    + is_close_done() : bool
}

class VResultFileSink <VFileResultWriter> {
    - _writer : VFileResultWriter
}

interface ResultWriter {
    + {abstract} init(RuntimeState*) : Status
    + {abstract} append_block(Block&) : Status
    + {abstract} close(RuntimeState*) : Status
}

interface AsyncResultWriter {
    + force_close(Status) : void
    + {abstract} open(RuntimeState*) : Status
    + start_writer(RuntimeState* state, RuntimeProfile* profile)
}

class VFileResultWriter {
    + open(RuntimeState*) : Status
    + append_block(Block&) : Status
    - _sinker : BufferControlBlock*
    - _output_block : Block*
}

class VOlapTableSink <VTabletWriter> {
    
}

class VJdbcTableSink <VJdbcTableWriter> {
    
}

class VOdbcTableSink <VOdbcTableWriter> {
    
}

class VMysqlTableSink <VMysqlTableWriter> {
    
}

class VMysqlTableWriter {
}

class VTabletWriter {
    - _send_batch_process() : void
    - _channel : IndexChannel
    - _index_id_to_channel Map<id, IndexChannel>
}

VtabletWriter *-- IndexChannel

class IndexChannel {
    - _index_id : int
    - _tablets_by_channel : Map<BeId, Set<TabletId>>
    - _node_channels : Map<BeId, VNodeChannelPtr>
    - _channels_by_tablet : Map<TableId, Vector<VNodeChannelPtr>>
}

@enduml
```

```cpp {.line-numbers}
class PipelineTask::prepare(RuntimeState* state)
{
    ...
    DataSinkOperator::preapare(state);
    for (auto& o : _operators) {
        RETURN_IF_ERROR(o->prepare(state));
    }
    ...
    set_state(PipelineTaskState::RUNNABLE);
}
```

```cpp
TaskScheduler::_do_work(size_t index)
{
    while (_markers[index])
    {
        // Open all operatprs
        Status PipelineTask::execute(&eos)
        {
            Status PipelineTasl::_open()
            {
                for (auto& opera : _operators)
                {
                    opera->open(RuntimeState*);
                }
                DataSinkOperator::open(RuntimeState*);
            }
        }

        while (!_fragment_context->is_cancelled())
        {
            _root->get_block(RuntimeState*, Block*, SourceState*);
        }

        *eos = _data_state == SourceState::FINISHED;

        if (_block->rows() != 0 || *eos)
        {
            Status = DataSinkOperator()::sink(RuntimeState*, Block*, SourceState*);
            // Sink EOF
            if (!status.is<ErrorCode::END_OF_FILE>())
            {
                RETURN_IF_ERROR(status);
            }
            // 
            *eos = status.is<ErrorCode::END_OF_FILE>() ? true : *eos;
            if (*eos) { // just return, the scheduler will do finish work
                break;
            }
        }
    }
}
```
```cpp {.line-numbers}
template <typename DataSinkType>
class DataSinkOperator : public OperatorBase
{
    ...
    Status sink(RuntimeState* state, vectorized::Block* in_block,
                SourceState source_state) override {
        if (in_block->rows() > 0 || source_state == SourceState::FINISHED) {
            return _sink->sink(state, in_block, source_state == SourceState::FINISHED);
        }
        return Status::OK();
    }
    ...
}

class VDataStreamSender : public DataSink
{
    // Send a Block into this sink, not blocked thredd API only use in pipeline exec engine
    virtual Status sink(RuntimeState* state, vectorized::Block* block, bool eos = false) {
        return send(state, block, eos);
    }

    // Send a Block into this sink.
    virtual Status send(RuntimeState* state, vectorized::Block* block, bool eos = false) {
        return Status::NotSupported("Not support send block");
    }
}

```
这里不知道为啥要有 sink 跟 send 两个 API。。。。除了 async_writer_sink 单独实现了 sink 外，其他的都是在 sink 里调用的 send。。。

宏观来看，ExchangeSinkOperator 的作用是把当前 pipeline 的 operators 处理完成的一个个 block 按照预设的规则发送给不同的 ExchangeSourceOperator。
从数据结构角度来看，ExchangeSinkOperator 需要把 Block 转为一个个 PBlock，然后把 PBlock 塞进 brpc 的 request 中，通过 brpc 发送给对端。
也就是在下面的几个数据结构之间进行类型转换。
```cpp
class Block 
{
    private:
        using Container = ColumnsWithTypeAndName;
        Container data;
}
```
```protobuf
message PBlock {
    repeated PColumnMeta column_metas = 1;
    optional bytes column_values = 2;
    optional bool compressed = 3 [default = false];
    optional int64 uncompressed_size = 4;
    optional segment_v2.CompressionTypePB compression_type = 5 [default = SNAPPY];
    optional int32 be_exec_version = 6 [default = 0];
}

message PColumnMeta {
    message Decimal {
        optional uint32 precision = 1;
        optional uint32 scale = 2;
    }
    optional string name = 1 [default = ""];
    optional PGenericType.TypeId type = 2 [default = UNKNOWN];
    optional bool is_nullable = 3 [default = false];
    optional Decimal decimal_param = 4;
    repeated PColumnMeta children = 5;
    optional bool result_is_nullable = 6;
    optional string function_name = 7;
}

message PTransmitDataParams {
    required PUniqueId finst_id = 1;
    required int32 node_id = 2;
    // Id of this fragment in its role as a sender.
    required int32 sender_id = 3;
    required int32 be_number = 4;
    // if set to true, indicates that no more row batches will be sent
    // for this dest_node_id
    required bool eos = 5;
    optional PRowBatch row_batch = 6;
    // different per packet
    required int64 packet_seq = 7;
    optional PQueryStatistics query_statistics = 8;

    optional PBlock block = 9;
    // transfer the RowBatch to the Controller Attachment
    optional bool transfer_by_attachment = 10 [default = false];
    optional PUniqueId query_id = 11;
    optional PStatus exec_status = 12;
};
```
这里预设的规则可能有
* UNPARTITION
* HASH PARTITION
* RANGE PRATITION
* RANDOM
等等。
那么从算法的角度来说，一个 Block 需要根据不同的分区规则进行分区，得到 PBlock，按照对端的对应关系，把 PBlock 塞进不同的 PTransmitDataParams 里。

```cpp
class VDataStreamSender : public DataSink
{
    Status send(RuntimeState*, Block*, bool eos = false)
    {
        bool all_receiver_eof = true;
        for (channel : _channels)
        {
            if (!channle->is_receiver_eof())
            {
                bool all_channel_eof = std::all_of(
                    std::begin(_channels), std::end(_channels),
                    [](Channel<VDataStreamSender>* channel) { return channel->is_receiver_eof(); });

                if (all_channel_eof)
                {
                    return Status::EndOfFile("all data stream channels EOF");
                }
            }

            if (_part_type == TPartitionType::UNPARTITIONED || _channels.size() == 1)
            {
                _serializer.next_serialized_block(
                        block, block_holder->get_block(), _channels.size(), &serialized, eos);

                if (serialized)
                {
                    auto cur_block = _serializer.get_block()->to_block();
                    
                    _serializer.serialize_block(&cur_block, block_holder->get_block(), _channels.size());
                    
                    for (auto channel : _channels) {
                        status = channel->send_broadcast_block(block_holder, eos);
                    }

                }
            }
        }
    }
}
```
主要关注 `1status = channel->send_broadcast_block(block_holder, eos);` 这个函数是同步还是异步的。
```cpp
template <typename Parent = VDataStreamSender>
class PipChannel final : public Channel<Parent>
{
    ...
    Status send_broadcast_block(std::shared_ptr<BroadcastPBlockHolder>& block,
                                bool eos = false) override
    {
        if (eos) {
            if (_eos_send) {
                return Status::OK();
            }
            _eos_send = true;
        }
        if (eos || block->get_block()->column_metas_size()) {
            RETURN_IF_ERROR(_buffer->add_block({this, block, eos}));
        }
        return Status::OK();
    }

private:
    pipeline::ExchangeSinkBuffer<Parent>* _buffer = nullptr;
}

template <typename Parent>
class ExchangeSinkBuffer
{
    Status add_block(BroadcastTransmitInfo<Parent>&& request)   
    {
        if (_is_finishing) {
            return Status::OK();
        }
        TUniqueId ins_id = request.channel->_fragment_instance_id;
        if (_is_receiver_eof(ins_id.lo)) {
            return Status::EndOfFile("receiver eof");
        }
        bool send_now = false;
        {
            std::unique_lock<std::mutex> lock(*_instance_to_package_queue_mutex[ins_id.lo]);
            // Do not have in process rpc, directly send
            if (_rpc_channel_is_idle[ins_id.lo]) {
                send_now = true;
                _rpc_channel_is_idle[ins_id.lo] = false;
                _busy_channels++;
            }
            _instance_to_broadcast_package_queue[ins_id.lo].emplace(request);
        }
        if (send_now) {
            RETURN_IF_ERROR(_send_rpc(ins_id.lo));
        }

        return Status::OK();
    }
}
```

---
`AsyncResultWriter::start_writer` 在 AsyncWriterSink::open 中被执行
```cpp
void AsyncResultWriter::process_block(RuntimeState* state, RuntimeProfile* profile) {
    if (auto status = open(state, profile); !status.ok()) {
        force_close(status);
    }

    if (_writer_status.ok()) {
        while (true) {
            if (!_eos && _data_queue.empty() && _writer_status.ok()) {
                std::unique_lock l(_m);
                while (!_eos && _data_queue.empty() && _writer_status.ok()) {
                    _cv.wait(l);
                }
            }

            if ((_eos && _data_queue.empty()) || !_writer_status.ok()) {
                _data_queue.clear();
                break;
            }

            auto block = _get_block_from_queue();
            auto status = write(block);
            if (!status.ok()) [[unlikely]] {
                std::unique_lock l(_m);
                _writer_status = status;
                if (_dependency && _is_finished()) {
                    _dependency->set_ready();
                }
                break;
            }

            _return_free_block(std::move(block));
        }
    }

    // if not in transaction or status is in error or force close we can do close in
    // async IO thread
    if (!_writer_status.ok() || !in_transaction()) {
        _writer_status = close(_writer_status);
        _need_normal_close = false;
    }
    _writer_thread_closed = true;
    if (_finish_dependency) {
        _finish_dependency->set_ready();
    }
}
```



### OLAPTableSink
#### TabletWriter

TabletWriter 并不是绑定到某一个 tablet，甚至不是某一个 table，而是对应本次 insert 需要涉及到的所有目标表。比如 table 绑定了一个物化视图，那么 TabletWriter 就需要把这个 batch 按照预先的 schema 定义写到 table + 物化视图中。

IndexChannel: 除了普通表之外，还有物化视图等其他类型的表，当关联其他类型的表时，一行数据可能需要写到多个表中，这里的 Index 就表示的是每个类型的需要写入的表。

NodeChannel: 由于每一张表都是一个分布式表，对于 TableSink 节点来说，它需要把数据写入到多个分布式表。而 Doris 是按照 Be 来组织分布式表的，所以这里的每个 NodeChannel 就是对应一个 Be，表示需要把一个 Batch 发送到这个 Be 上。

```cpp
Status VTabletWriter::append_block(const Block& block)
{
    // Step 1. Generate row distribution
    ...
    std::shared_ptr<vectorized::Block> block;
    RETURN_IF_ERROR(_row_distribution.generate_rows_distribution(
            input_block, block, ...));

    // Step 2. Generate_index_channels_payloads
    _generate_index_channels_payloads(_row_part_tablet_ids, channel_to_payload);
    ...

    // Step 3. Add block to node channel
    for (size_t i = 0; i < _channels.size(); i++) {
        std::unordered_map<VNodeChannel*, Payload>& channel_to_payload_entry =
                channel_to_payload[i];
        for (auto& pair : channel_to_payload_entry) {
            // if this node channel is already failed, this add_row will be skipped
            VNodeChannel* node_channel_ptr = pair.first;
            const Payload& payload = pair.second; //   [row -> tablet] mapping
            // if it is load single tablet, then append this whole block
            auto st =
                    node_channel_ptr->add_block(block.get(), &payload, load_block_to_single_tablet);
            if (!st.ok()) {
                _channels[i]->mark_as_failed(node_channel_ptr, st.to_string());
            }
        }
    }

}
```
#### try_close & close
```cpp {.line-numbers}
class AsyncWriterSink {
    ...
    bool can_write() override { return _writer->can_write(); }

    bool is_close_done() override { return !_writer->is_pending_finish(); }

    Status try_close(RuntimeState* state, Status exec_status) override {
        if (state->is_cancelled() || !exec_status.ok()) {
            _writer->force_close(!exec_status.ok() ? exec_status : Status::Cancelled("Cancelled"));
        }
        return Status::OK();
    }

    Status close(RuntimeState* state, Status exec_status) override {
        // if the init failed, the _writer may be nullptr. so here need check
        if (_writer) {
            if (_writer->need_normal_close()) {
                if (exec_status.ok() && !state->is_cancelled()) {
                    RETURN_IF_ERROR(_writer->commit_trans());
                }
                RETURN_IF_ERROR(_writer->close(exec_status));
            } else {
                RETURN_IF_ERROR(_writer->get_writer_status());
            }
        }
        return DataSink::close(state, exec_status);
    }
}

class OLAPTableSink
```

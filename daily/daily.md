##### 2023/2/7
上周处理了Blobstore编译的问题。
Plan:
1. Blobstore 联调
2. 面试刷题
3. Golang 实现简单查询引擎

Status:
1. Blobstore 联调：本周解决编译问题，复习了链接过程。等待 yotta client 提供流式接口，buffer client 提供可使用的版本。
2. 面试刷题：三个基本的排序算法进行了复习
3. None

##### 2022/12/2
BlobStore设计文档完成90%，缺接口设计，然后就可以Review了。之所以周五才完成，主要是因为这周重新确认了CGO相关的内存分配原则。
假设下周一完成Review，那么满打满算开发测试时间就一个月。开发过程中预计比较大的工作量：1. 配置文件处理；2. CGO 封装；3. 测试。
同时这个月还有两件事想要做：1. Clickhouse社区的ArrayFold；2. qlib 的使用流程。

##### 2022/11/24

本周目标是完成BlobStore的详细设计文档。今天周四。需要在下周一完成。
TODO：
1. 普通用户通过COS Http接口能够执行哪些操作？
2. 每个普通用户对Object的操作最终会转化成COS对BlobStore的哪些操作？
3. 当前Append操作的流程是什么样的？上线BufferStore以后变成什么样？体现在BlobStore是怎么样的？
4. 还有类似Append的其他操作吗？
5. 撰写文档

算上今天还有3.5天，其中1-4必须在周五下午6点前完成（因为有时需要请教其他同事）。那么也就是1.5天需要完成1-4。那就今天先把3，4做了，明天完成1-2，周末开始撰写文档，下周一review。

##### 2022/11/7

计划：
    
白天：沟通 BlobStore 调研具体应该怎么做（性能测试要不要做，什么时候做）BlobStore 的实现需要参考 COS 现在对各个Client的调用逻辑。
   晚上：阅读 MapReduce 论文，看 6824 Lec1 后半部分视频。20:30去健身。

##### 2022/11/4

为什么 inline 可以修复 ODR?

Cgo 封装 NodeManagerClient 不搞了，弄一个更大的模块出来，BlobStorage

##### 2022/10/20
  
折腾了一天 thrift echo demo，终于完成了 thfit cpp/go echo server demo.
期间遇到很多坑。加深(复习)了对 libc 的认知，对编译器寻找头文件过程的理解，成果：用cmake管理cpp/go/thrift混合项目。
明天：cgo 调用 thrift cpp client。

##### 2022/10/19

折腾了一天 thrift demo ，终于编译完成了 thrift server。
明天目标：thrift echo client， cgo 调用 thrift client。


##### 2022/10/18

想要自动化测试 cgo ，想要一条龙搞定结果可视化，所以尝试了 Go 画图表，Go 生成 Excel，进度：跑通 demo。

尝试编译 trpc-cpp 失败，😊

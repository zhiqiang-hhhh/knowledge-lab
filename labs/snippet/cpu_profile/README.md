## 单核
```
[hezhiqiang@VM-10-8-centos cpu_profile]$ taskset -c 0 perf stat ./main 6 0 196 196 10 0
Running Thread Pool with Timed Task Producer mode, io_flag is 0...
Starting ThreadPool with 196 threads and 196 producers...
Stopping ThreadPool...
ThreadPool is set stopped...
Waiting for 196 workers to join, existing tasks 0...
ThreadPool stopped
Finished 1494364 producers, qps is 149436
Elapsed time: 10.3972 seconds

 Performance counter stats for './main 6 0 196 196 10 0':

         10,350.24 msec task-clock:u              #    0.995 CPUs utilized
                 0      context-switches:u        #    0.000 K/sec
                 0      cpu-migrations:u          #    0.000 K/sec
             1,629      page-faults:u             #    0.157 K/sec
    13,489,759,606      cycles:u                  #    1.303 GHz
    14,169,716,761      instructions:u            #    1.05  insn per cycle
     2,807,271,647      branches:u                #  271.228 M/sec
        57,583,704      branch-misses:u           #    2.05% of all branches

      10.399704008 seconds time elapsed

       4.923130000 seconds user
       5.432143000 seconds sys
```
* task-clock 表示的是期间所有 CPU 核心上用于执行当前进程的任务的执行时间之和。
* cycles 表示期间所有 CPU 核心上有多少个 cycles 用于执行当前任务的指令。

perf 从 task-clock 中计算得到了 0.995 的 CPU 使用率，表示在 perf 统计期间，每个CPU核心上用来执行目标进程指令的时间比例是 0.995，这个值怎么算出来的：`10,350.24 / (10.399704008 * 1)`，这里的 1 表示用到的核心的数量。这里的时间怎么理解？没有继续深入追，我理解这里应该统计方式是，某个时间长度下是否有某个cycles上有当前进程的指令在运行，如果有，那么这个时间长度就算是被当前进程使用，就会增加这里看到的 task-clock。

cycles 表示 `10.399704008` 秒内记录到了 `13,489,759,606` 个 cycle **上有指令在执行**，而 CPU 执行的时间片粒度是 cycles，那么程序的执行频率就是 `13,489,759,606 / 10,350.24 * 1000`，注意这里用到的分母是 task-clock 而不是倒数第三行看到的总运行时间。得到的 `1.303 GHz` 表示当前进程在每个CPU核心上每秒平均可以"消费" 1.303 G 个 cycles。

之所以说是在每个CPU核心上，是因为我们看到的的 task-clock 以及 cycles 都是统计的所有 CPU 核心上的统计值的累加和。所以右侧得到的结果就是平均在每个CPU上的“性能”

这里的性能如何理解呢？假设我们不考虑CPU主频的变化，那么对于一个CPU来说，它的主频就是固定的，所以它在定长时间段内其产生的总的 cycles 数量是固定的，perf stat 统计了在整个 perf 期间，目标进程在多少个 cycles 上有指令在执行，那么用实际计算得到的 cycles / 理论上的最大 cycles，或者说，用计算得到的CPU频率除以期间CPU的主频，就是当前进程用到的CPU最大工作频率的百分比。
```
[hezhiqiang@VM-10-8-centos cpu_profile]$ lscpu
Architecture:        x86_64
CPU op-mode(s):      32-bit, 64-bit
Byte Order:          Little Endian
CPU(s):              96
On-line CPU(s) list: 0-95
Thread(s) per core:  2
Core(s) per socket:  24
Socket(s):           2
NUMA node(s):        2
Vendor ID:           GenuineIntel
CPU family:          6
Model:               85
Model name:          Intel(R) Xeon(R) Platinum 8255C CPU @ 2.50GHz
Stepping:            7
CPU MHz:             3019.285
CPU max MHz:         2501.0000
CPU min MHz:         1000.0000
BogoMIPS:            5000.00
Virtualization:      VT-x
L1d cache:           32K
L1i cache:           32K
L2 cache:            1024K
L3 cache:            36608K
NUMA node0 CPU(s):   0-23,48-71
NUMA node1 CPU(s):   24-47,72-95
```
lscpu 看到我们使用的 Intel CPU 在不启用(Turbo Boost)时的CPU最大工作频率是 2.50GHz，结合之前的 perf 结果，说明在单核运行时，虽然我们看到CPU使用率上单核接近100%，但是实际上这个使用率是从CPU干活的绝对时间比例来算的，从时钟周期上看，我们的单核性能只达到了最大性能的 52%，考虑 Intel CPU 可能的动态频率调整，这个比例还会更低。

## 多核

上述命令执行时我们设置了绑核，代码只能在一个CPU core上运行，如果改成可以在多个CPU core上运行。
```
[hezhiqiang@VM-10-8-centos cpu_profile]$ taskset -c 0-4 perf stat ./main 6 0 196 196 10 0
Running Thread Pool with Timed Task Producer mode, io_flag is 0...
Starting ThreadPool with 196 threads and 196 producers...
Stopping ThreadPool...
ThreadPool is set stopped...
Waiting for 196 workers to join, existing tasks 0...
ThreadPool stopped
Elapsed time: 10.0185 seconds

 Performance counter stats for './main 6 0 196 196 10 0':

         45,912.35 msec task-clock:u              #    4.582 CPUs utilized
                 0      context-switches:u        #    0.000 K/sec
                 0      cpu-migrations:u          #    0.000 K/sec
             1,684      page-faults:u             #    0.037 K/sec
    42,139,430,830      cycles:u                  #    0.918 GHz
    26,472,050,878      instructions:u            #    0.63  insn per cycle
     5,266,248,483      branches:u                #  114.702 M/sec
       137,507,204      branch-misses:u           #    2.61% of all branches

      10.020570649 seconds time elapsed

      15.237847000 seconds user
      31.330834000 seconds sys
```
改成可以在 5 个核上运行之后，第一个 task-clock 变成了 45912.35 ms，这个值等于所有核心上运行的时间相加，约等于 `10.0205 * 1000 * 4.582`，此时的单核性能变成了 0.918 GHz，等于 `42139430830 / 45912.35 * 1000`。
#include <iostream>
#include <thread>
#include <vector>
#include <omp.h>
#include <chrono>

void worker(int tid, int omp_threads) {
    // 限制当前线程中的 OpenMP 并行线程数
    omp_set_num_threads(omp_threads);
    std::cout << "[Thread " << tid << "] Started with OpenMP threads: " << omp_threads << std::endl;

    while (true) {
        // 第一个 OpenMP 并行区域
        #pragma omp parallel
        {
            int omp_tid = omp_get_thread_num();
            int omp_nthreads = omp_get_num_threads();

            // 打印当前 OpenMP 线程的信息
            std::cout << "[Worker Thread " << tid << "] Parallel Region 1: OMP thread " << omp_tid
                      << "/" << omp_nthreads << std::endl;

            // 每个线程 sleep 一下避免刷屏太快
            std::this_thread::sleep_for(std::chrono::milliseconds(500));
        }

        // 第二个 OpenMP 并行区域
        #pragma omp parallel
        {
            int omp_tid = omp_get_thread_num();
            int omp_nthreads = omp_get_num_threads();

            // 打印当前 OpenMP 线程的信息
            std::cout << "[Worker Thread " << tid << "] Parallel Region 2: OMP thread " << omp_tid
                      << "/" << omp_nthreads << std::endl;

            // 每个线程 sleep 一下避免刷屏太快
            std::this_thread::sleep_for(std::chrono::milliseconds(500));
        }

        // 主线程休息一下，避免输出过于频繁
        std::this_thread::sleep_for(std::chrono::milliseconds(1000));
    }
}

int main() {
    int num_workers = 2;      // 主线程启动的 std::thread 数量

    std::vector<std::thread> workers;

    for (int i = 0; i < num_workers; ++i) {
        // 每个worker使用不同数量的OpenMP线程
        int omp_threads = 2 + i;  // 线程0用2个，线程1用3个，线程2用4个，线程3用5个
        workers.emplace_back(worker, i, omp_threads);
    }

    // 等待所有线程（实际上它们是死循环）
    for (auto& t : workers) {
        t.join();
    }

    return 0;
}

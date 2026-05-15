#include <iostream>
#include <thread>
#include <vector>
#include <omp.h>
#include <chrono>
#include <mutex>

std::mutex cout_mtx;

void worker(int tid, int omp_threads) {
    // omp_set_num_threads(omp_threads);
    {
        std::lock_guard<std::mutex> lg(cout_mtx);
        std::cout << "[Thread " << tid << "] Started with omp_set_num_threads(" << omp_threads << ")" << std::endl;
    }

    const int iterations = 3;
    for (int iter = 0; iter < iterations; ++iter) {
        #pragma omp parallel
        {
            int omp_tid = omp_get_thread_num();
            int omp_nthreads = omp_get_num_threads();
            std::lock_guard<std::mutex> lg(cout_mtx);
            std::cout << "[Worker " << tid << "] iter=" << iter << " region=1: OMP thread " << omp_tid
                      << "/" << omp_nthreads << std::endl;
        }

        #pragma omp parallel
        {
            int omp_tid = omp_get_thread_num();
            int omp_nthreads = omp_get_num_threads();
            std::lock_guard<std::mutex> lg(cout_mtx);
            std::cout << "[Worker " << tid << "] iter=" << iter << " region=2: OMP thread " << omp_tid
                      << "/" << omp_nthreads << std::endl;
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }

    {
        std::lock_guard<std::mutex> lg(cout_mtx);
        std::cout << "[Thread " << tid << "] Finished." << std::endl;
    }
}

int main() {
    int num_workers = 2;
    std::vector<std::thread> workers;
    omp_set_num_threads(3);
    for (int i = 0; i < num_workers; ++i) {
        int omp_threads = 2 + i;
        workers.emplace_back(worker, i, omp_threads);
    }

    for (auto& t : workers) t.join();

    return 0;
}

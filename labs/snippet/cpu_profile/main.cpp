#include <cstdlib>
#include <iostream>
#include <thread>
#include <type_traits>
#include <vector>
#include <mutex>
#include <chrono>
#include <atomic>
#include <fstream>
#include <queue>
#include <condition_variable>
#include <functional>
#include <future>
#include <unistd.h> // For sleep() function
#include <variant>

std::mutex mtx; // Mutex for locking
std::atomic<int> shared_counter(0); // Shared atomic counter for locks
std::ofstream fake_io_file; // Fake IO file for simulation
std::atomic_int64_t finished_producers(0); // Atomic counter for finished producers

void simulate_io(int id) {
    std::this_thread::sleep_for(std::chrono::milliseconds(500)); // 模拟延时
    std::lock_guard<std::mutex> lock(mtx);
    fake_io_file << "Thread " << id << " performed I/O operation\n";
}

void serial_mode(int iterations) {
    for (int i = 0; i < iterations; ++i) {
        // 执行一些计算操作
        double result = (i * 3.14) / 2.71;
    }
}

void parallel_mode(std::chrono::seconds duration, int thread_count) {
    std::vector<std::thread> threads;
    std::atomic<bool> stop_flag(false);
    // std::rand 有性能问题，std::rand() 内部是需要加锁的
    
    for (int i = 0; i < thread_count; ++i) {
        threads.push_back(std::thread([&stop_flag]() {
            while (!stop_flag.load()) {
                auto rand_i32 = std::rand();
                double result = (rand_i32 * 3.14) / 2.71;
                finished_producers.fetch_add(1);
            }
        }));
    }

    std::this_thread::sleep_for(duration);
    stop_flag.store(true);

    for (auto& t : threads) {
        t.join();
    }

    std::cout << "Finished " << finished_producers.load()
                << " producers, qps is " << finished_producers.load() / duration.count() << "\n";
}

void lock_dependency_mode(int iterations, int thread_count) {
    std::vector<std::thread> threads;
    for (int i = 0; i < thread_count; ++i) {
        threads.push_back(std::thread([iterations, i]() {
            for (int j = 0; j < iterations; ++j) {
                std::lock_guard<std::mutex> lock(mtx);
                double result = (j * 3.14) / 2.71; // 模拟计算
                shared_counter.fetch_add(1, std::memory_order_relaxed);
                simulate_io(i); // 模拟IO操作
            }
        }));
    }
    for (auto& t : threads) {
        t.join();
    }
}

void lock_serial_mode(int iterations, int thread_count) {
    std::vector<std::thread> threads;
    for (int i = 0; i < thread_count; ++i) {
        threads.push_back(std::thread([iterations, i]() {
            for (int j = 0; j < iterations; ++j) {
                std::lock_guard<std::mutex> lock(mtx);
                double result = (j * 3.14) / 2.71;
                // 这里模拟锁的影响
                shared_counter.fetch_add(1, std::memory_order_relaxed);
                std::this_thread::sleep_for(std::chrono::milliseconds(10)); // 睡眠模拟实际串行执行
            }
        }));
    }
    for (auto& t : threads) {
        t.join();
    }
}

void io_in_parallel_mode(int iterations, int thread_count) {
    std::vector<std::thread> threads;
    for (int i = 0; i < thread_count; ++i) {
        threads.push_back(std::thread([iterations, i]() {
            for (int j = 0; j < iterations; ++j) {
                double result = (j * 3.14) / 2.71;
                simulate_io(i); // 模拟IO操作
            }
        }));
    }
    for (auto& t : threads) {
        t.join();
    }
}

class ThreadPool {
public:
    ThreadPool(size_t pool_size);
    ~ThreadPool();

    using EnqueueSucceed = bool;

    template<class F, class... Args>
    using EnqueueResult = std::variant<EnqueueSucceed, std::future<typename std::invoke_result<F, Args...>::type>>;

    template<class F, class... Args>
    EnqueueResult<F, Args...> enqueue(F&& f, Args&&... args);
    
    void stop();

private:
    std::vector<std::thread> workers;
    std::queue<std::function<void()>> tasks;

    std::mutex queue_mutex;
    std::condition_variable condition;
    bool stop_flag;
};

ThreadPool::ThreadPool(size_t pool_size) : stop_flag(false) {
    for (size_t i = 0; i < pool_size; ++i) {
        workers.emplace_back([this] {
            for (;;) {
                std::function<void()> task;

                {
                    std::unique_lock<std::mutex> lock(this->queue_mutex);
                    this->condition.wait(lock, [this] { return this->stop_flag || !this->tasks.empty(); });
                    

                    // Finish all tasks before stopping
                    if (!this->tasks.empty()) {
                        task = std::move(this->tasks.front());
                        this->tasks.pop();
                    } else {
                        if (stop_flag) {
                            return;
                        }               
                    }
                }

                task();
            }
        });
    }
}

ThreadPool::~ThreadPool() {
    stop();
}

template<class F, class... Args>
auto ThreadPool::enqueue(F&& f, Args&&... args) -> std::variant<bool, std::future<typename std::invoke_result<F, Args...>::type>> {
    using return_type = typename std::invoke_result<F, Args...>::type;

    auto task = std::make_shared<std::packaged_task<return_type()>>(std::bind(std::forward<F>(f), std::forward<Args>(args)...));

    std::future<return_type> res = task->get_future();
    {
        std::unique_lock<std::mutex> lock(queue_mutex);

        if (stop_flag)
            return std::variant<bool, std::future<return_type>>(false);

        tasks.emplace([task]() { (*task)(); });
    }
    condition.notify_one();
    return std::variant<bool, std::future<return_type>>(std::move(res));
}

void ThreadPool::stop() {
    {
        std::unique_lock<std::mutex> lock(queue_mutex);
        if (stop_flag) {
            return;
        }
        std::cout << "ThreadPool is set stopped...\n";
        stop_flag = true;
    }
    condition.notify_all();
    std::cout << "Waiting for "<< workers.size() << " workers to join, existing tasks " << tasks.size() << "...\n";
    for (std::thread &worker : workers) {
        worker.join();
    }
}

class TaskProducer {
public:
    TaskProducer(ThreadPool& pool, int id, bool io_flag = true)
        : pool(pool), id(id), io_flag(io_flag), rand_i32(std::rand()){}

    void produce_tasks() {
        auto task = [this] {
            double result = (rand_i32 * 3.14) / 2.71;
            if (io_flag) {
                simulate_io(id);
            }
            return result;
        };

        while (true) {
            auto res = pool.enqueue(task);

            if (std::holds_alternative<bool>(res) && !std::get<bool>(res)) {
                break; // Stop if enqueue failed
            } else {
                // Get result from task.
                std::future<double> future = std::move(std::get<std::future<double>>(res));
                future.wait();
                double task_res = future.get();
                finished_producers.fetch_add(1, std::memory_order_relaxed);
            }
        }
    }

private:
    ThreadPool& pool;
    int id;
    bool io_flag;
    // std::rand 有性能问题，std::rand() 内部是需要加锁的
    int rand_i32;
};

void thread_pool_with_timed_task_producer_mode(std::chrono::seconds duration, int thread_count, int producer_count, bool io_flag) {
    std::cerr << "Starting ThreadPool with " << thread_count << " threads and " << producer_count << " producers...\n";
    ThreadPool pool(thread_count);

    std::vector<std::thread> producers;
    for (int i = 0; i < producer_count; ++i) {
        producers.emplace_back([&pool, i, io_flag] {
            TaskProducer producer(pool, i, io_flag);
            producer.produce_tasks();
        });
    }

    std::this_thread::sleep_for(duration);
    std::cerr << "Stopping ThreadPool...\n";
    pool.stop(); // Signal all producers to stop
    for (auto& producer : producers) {
        producer.join();
    }
    std::cerr << "ThreadPool stopped\n";
    std::cout << "Finished " << finished_producers.load() << " producers, qps is " << finished_producers.load() / duration.count() << "\n";
}

/**
 * @brief Entry point of the program.
 *
 * This function parses command-line arguments and executes different modes based on the provided mode.
 * 
 * Usage: <program_name> <mode> <iterations> <threads> [producers] [duration] [io_flag]
 * 
 * Modes:
 * 1 - Serial
 * 2 - Parallel
 * 3 - Lock Dependency
 * 4 - Lock Serial
 * 5 - IO in Parallel
 * 6 - Thread Pool with Timed Task Producer
 * 
 * @param argc Number of command-line arguments.
 * @param argv Array of command-line arguments.
 * 
 * Command-line arguments:
 * - mode: The mode of operation (integer).
 * - iterations: Number of iterations (integer, not used in mode 6).
 * - threads: Number of threads (integer).
 * - producers: Number of producers (integer, optional, default is 1).
 * - duration: Duration in seconds (integer, optional, default is 10).
 * - io_flag: Flag to indicate whether IO operations should be performed (boolean, optional, default is true).
 * 
 * @return int Exit status of the program.
 */
int main(int argc, char** argv) {
    if (argc < 4) {
        std::cout << "Usage: " << argv[0] << " <mode> <iterations> <threads> [producers] [duration] [io_flag]\n";
        std::cout << "Modes: 1 - Serial, 2 - Parallel, 3 - Lock Dependency, 4 - Lock Serial, 5 - IO in Parallel, 6 - Thread Pool with Timed Task Producer\n";
        std::cout << "io_flag: 0 for no IO operations, 1 for IO operations (only applicable for mode 6)\n";
        return 1;
    }

    int mode = std::stoi(argv[1]);
    int iterations = (mode == 2 || mode == 6) ? 0 : std::stoi(argv[2]);
    int thread_count = std::stoi(argv[3]);
    int producer_count = (argc > 4) ? std::stoi(argv[4]) : 1;
    int duration_seconds = (argc > 5) ? std::stoi(argv[5]) : 10;
    bool io_flag = (argc >= 7) ? std::stoi(argv[6]) : true;

    auto start_time = std::chrono::steady_clock::now();

    switch (mode) {
        case 1:
            std::cout << "Running in Serial mode...\n";
            serial_mode(iterations);
            break;
        case 2:
            std::cout << "Running in Parallel mode...\n";
            parallel_mode(std::chrono::seconds(duration_seconds), thread_count);
            break;
        case 3:
            std::cout << "Running in Lock Dependency mode...\n";
            lock_dependency_mode(iterations, thread_count);
            break;
        case 4:
            std::cout << "Running in Lock Serial mode...\n";
            lock_serial_mode(iterations, thread_count);
            break;
        case 5:
            std::cout << "Running IO in Parallel mode...\n";
            io_in_parallel_mode(iterations, thread_count);
            break;
        case 6:
            std::cout << "Running Thread Pool with Timed Task Producer mode, io_flag is " << io_flag << "...\n";
            thread_pool_with_timed_task_producer_mode(std::chrono::seconds(duration_seconds), thread_count, producer_count, io_flag);
            break;
        default:
            std::cout << "Unknown mode selected!\n";
            return 1;
    }

    auto end_time = std::chrono::steady_clock::now();
    std::chrono::duration<double> elapsed_seconds = end_time - start_time;
    std::cout << "Elapsed time: " << elapsed_seconds.count() << " seconds\n";
    fake_io_file.close();
    return 0;
}

#include <iostream>
#include <mutex>

class Singleton {
    private:
        Singleton() {}
    public:
        static Singleton instance;
        static Singleton& getInstance() {
            return instance;
        }
};

Singleton Singleton::instance;

class Singleton1 {
    private:
        Singleton1() {}
    public:
        static Singleton1& getInstance() {
            std::lock_guard<std::mutex> lock(mtx);
            if (instance == nullptr) {
                instance = new Singleton1();
            }
            return *instance;
        }
    private:
        static Singleton1* instance;
        static std::mutex mtx;
};

Singleton1* Singleton1::instance = nullptr;
std::mutex Singleton1::mtx;

class Singleton2 {
    private:
        Singleton2() {}
    public:
        static Singleton2& getInstance() {
            if (instance == nullptr) {
                std::lock_guard<std::mutex> lock(mtx);
                if (instance == nullptr) {
                    instance = new Singleton2();
                }
            }
            return *instance;
        }
    private:
        static Singleton2* instance;
        static std::mutex mtx;
};

Singleton2* Singleton2::instance = nullptr;
std::mutex Singleton2::mtx;

class Singleton3 {
    
};

int main () {
    Singleton& s1 = Singleton::getInstance();
    Singleton& s2 = Singleton::getInstance();
    if (&s1 == &s2) {
        std::cout << "Both are same instance." << std::endl;
    } else {
        std::cout << "Different instances." << std::endl;
    }

    Singleton1& s3 = Singleton1::getInstance();
    Singleton1& s4 = Singleton1::getInstance();
    if (&s3 == &s4) {
        std::cout << "Both are same instance." << std::endl;
    } else {
        std::cout << "Different instances." << std::endl;
    }
    return 0;
}
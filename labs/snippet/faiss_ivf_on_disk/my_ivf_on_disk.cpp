// 一个“仿照 Faiss”的最小 IVF + OnDisk demo（纯 C++，不依赖 Faiss）

#include <algorithm>
#include <cmath>
#include <cstring>
#include <cstdint>
#include <filesystem>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <limits>
#include <queue>
#include <random>
#include <stdexcept>
#include <string>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <utility>
#include <vector>

namespace {

float l2sqr(const float *a, const float *b, int d) {
  float s = 0.0f;
  for (int i = 0; i < d; ++i) {
    float diff = a[i] - b[i];
    s += diff * diff;
  }
  return s;
}

void fill_random(std::vector<float> &x, uint32_t seed) {
  std::mt19937 rng(seed);
  std::uniform_real_distribution<float> dis(0.0f, 1.0f);
  for (auto &v : x) {
    v = dis(rng);
  }
}

struct Posting {
  int64_t id = -1;
  std::vector<float> vec;
};

struct ListMeta {
  uint64_t offset_bytes = 0; // 在 data 文件中的起始偏移
  uint64_t size = 0;         // 该 list 的 posting 数量
};

class ReadOnlyMMap {
public:
  ReadOnlyMMap() = default;

  ~ReadOnlyMMap() { close(); }

  ReadOnlyMMap(const ReadOnlyMMap &) = delete;
  ReadOnlyMMap &operator=(const ReadOnlyMMap &) = delete;

  ReadOnlyMMap(ReadOnlyMMap &&other) noexcept { move_from(std::move(other)); }

  ReadOnlyMMap &operator=(ReadOnlyMMap &&other) noexcept {
    if (this != &other) {
      close();
      move_from(std::move(other));
    }
    return *this;
  }

  void open(const std::string &path) {
    close();

    fd_ = ::open(path.c_str(), O_RDONLY);
    if (fd_ < 0) {
      throw std::runtime_error("open mmap file failed: " + path);
    }

    struct stat st {};
    if (::fstat(fd_, &st) != 0) {
      ::close(fd_);
      fd_ = -1;
      throw std::runtime_error("fstat mmap file failed: " + path);
    }

    if (st.st_size == 0) {
      throw std::runtime_error("mmap file is empty: " + path);
    }

    size_ = static_cast<size_t>(st.st_size);
    void *p = ::mmap(nullptr, size_, PROT_READ, MAP_SHARED, fd_, 0);
    if (p == MAP_FAILED) {
      ::close(fd_);
      fd_ = -1;
      size_ = 0;
      throw std::runtime_error("mmap failed: " + path);
    }

    data_ = static_cast<const uint8_t *>(p);
  }

  void close() {
    if (data_) {
      ::munmap(const_cast<uint8_t *>(data_), size_);
      data_ = nullptr;
      size_ = 0;
    }
    if (fd_ >= 0) {
      ::close(fd_);
      fd_ = -1;
    }
  }

  const uint8_t *data() const { return data_; }

  size_t size() const { return size_; }

  bool valid() const { return data_ != nullptr && size_ > 0; }

  void advise_willneed(size_t offset, size_t bytes) const {
    if (!valid() || bytes == 0) {
      return;
    }

    long page = ::sysconf(_SC_PAGESIZE);
    if (page <= 0) {
      return;
    }
    const size_t page_size = static_cast<size_t>(page);
    const size_t begin = (offset / page_size) * page_size;
    const size_t end = std::min(size_, offset + bytes);
    if (end <= begin) {
      return;
    }

    const size_t len = end - begin;
    (void)::madvise(
        const_cast<uint8_t *>(data_) + begin, len, MADV_WILLNEED);
  }

private:
  void move_from(ReadOnlyMMap &&other) {
    data_ = other.data_;
    size_ = other.size_;
    fd_ = other.fd_;

    other.data_ = nullptr;
    other.size_ = 0;
    other.fd_ = -1;
  }

  const uint8_t *data_ = nullptr;
  size_t size_ = 0;
  int fd_ = -1;
};

class InvertedLists {
public:
  explicit InvertedLists(size_t nlist) : lists_(nlist) {}

  void add_entry(size_t list_no, int64_t id, const float *x, int d) {
    Posting p;
    p.id = id;
    p.vec.assign(x, x + d);
    lists_.at(list_no).push_back(std::move(p));
  }

  const std::vector<Posting> &list(size_t list_no) const {
    return lists_.at(list_no);
  }

  size_t nlist() const { return lists_.size(); }

  size_t list_size(size_t list_no) const { return lists_.at(list_no).size(); }

  std::vector<std::vector<Posting>> &mutable_lists() { return lists_; }

private:
    // centroids id to its postings list.
  std::vector<std::vector<Posting>> lists_;
};

class SimpleCoarseQuantizer {
public:
  SimpleCoarseQuantizer(int d, int nlist) : d_(d), nlist_(nlist) {}

  void train(const std::vector<float> &xb) {
    if (xb.size() % static_cast<size_t>(d_) != 0) {
      throw std::runtime_error("bad train data shape");
    }
    size_t nb = xb.size() / d_;
    if (nb < static_cast<size_t>(nlist_)) {
      throw std::runtime_error("nb < nlist, cannot train");
    }
    centers_.assign(nlist_ * d_, 0.0f);

    // 最简单版本：随机抽 nlist 个向量作为中心
    std::vector<size_t> idx(nb);
    for (size_t i = 0; i < nb; ++i) {
      idx[i] = i;
    }
    std::mt19937 rng(7);
    std::shuffle(idx.begin(), idx.end(), rng);

    for (int id = 0; id < nlist_; ++id) {
      const float *src = xb.data() + idx[id] * d_;
      std::copy(src, src + d_, centers_.data() + id * d_);
    }
  }

  int assign(const float *x) const {
    float best = std::numeric_limits<float>::max();
    int best_id = -1;
    for (int c = 0; c < nlist_; ++c) {
      float dis = l2sqr(x, centers_.data() + c * d_, d_);
      if (dis < best) {
        best = dis;
        best_id = c;
      }
    }
    return best_id;
  }

  std::vector<int> assign_nprobe(const float *x, int nprobe) const {
    std::vector<std::pair<float, int>> all;
    all.reserve(nlist_);
    for (int c = 0; c < nlist_; ++c) {
      all.emplace_back(l2sqr(x, centers_.data() + c * d_, d_), c);
    }
    std::partial_sort(
        all.begin(), all.begin() + std::min(nprobe, nlist_), all.end(),
        [](const auto &a, const auto &b) { return a.first < b.first; });

    std::vector<int> out;
    int p = std::min(nprobe, nlist_);
    out.reserve(p);
    for (int i = 0; i < p; ++i) {
      out.push_back(all[i].second);
    }
    return out;
  }

  const std::vector<float> &centers() const { return centers_; }

  void set_centers(std::vector<float> centers) {
    centers_ = std::move(centers);
  }

private:
  int d_;
  int nlist_;
  std::vector<float> centers_;
};

class SimpleIVFIndex {
public:
  SimpleIVFIndex(int d, int nlist)
      : d_(d), nlist_(nlist), nprobe_(std::min(8, nlist)), quantizer_(d, nlist),
        invlists_(nlist), list_meta_(nlist) {}

  void train(const std::vector<float> &xb) {
    quantizer_.train(xb);
    trained_ = true;
  }

  void set_nprobe(int nprobe) {
    nprobe_ = std::max(1, std::min(nprobe, nlist_));
  }

  void add(const std::vector<float> &xb) {
    if (!trained_) {
      throw std::runtime_error("index not trained");
    }
    if (xb.size() % static_cast<size_t>(d_) != 0) {
      throw std::runtime_error("bad add data shape");
    }
    size_t nb = xb.size() / d_;
    for (size_t i = 0; i < nb; ++i) {
      const float *x = xb.data() + i * d_;
      int list_no = quantizer_.assign(x);
      int64_t id = ntotal_ + static_cast<int64_t>(i);
      invlists_.add_entry(list_no, id, x, d_);
    }
    ntotal_ += static_cast<int64_t>(nb);
  }

  void search(const std::vector<float> &xq, int k, std::vector<float> &D,
              std::vector<int64_t> &I) const {
    if (xq.size() % static_cast<size_t>(d_) != 0) {
      throw std::runtime_error("bad query shape");
    }
    size_t nq = xq.size() / d_;
    D.assign(nq * k, std::numeric_limits<float>::infinity());
    I.assign(nq * k, -1);

    for (size_t qi = 0; qi < nq; ++qi) {
      const float *q = xq.data() + qi * d_;
      auto probes = quantizer_.assign_nprobe(q, nprobe_);

      if (on_disk_mode_) {
        prefetch_lists(probes);
      }

      // 大根堆存 top-k（堆顶是最差结果）
      using Pair = std::pair<float, int64_t>;
      auto cmp = [](const Pair &a, const Pair &b) { return a.first < b.first; };
      std::priority_queue<Pair, std::vector<Pair>, decltype(cmp)> heap(cmp);

      for (int list_no : probes) {
        if (on_disk_mode_) {
          scan_list_from_disk(list_no, q, k, heap);
        } else {
          const auto &posting = invlists_.list(list_no);
          for (const auto &p : posting) {
            float dis = l2sqr(q, p.vec.data(), d_);
            if (static_cast<int>(heap.size()) < k) {
              heap.emplace(dis, p.id);
            } else if (dis < heap.top().first) {
              heap.pop();
              heap.emplace(dis, p.id);
            }
          }
        }
      }

      int out = static_cast<int>(heap.size()) - 1;
      while (!heap.empty()) {
        D[qi * k + out] = heap.top().first;
        I[qi * k + out] = heap.top().second;
        heap.pop();
        --out;
      }
    }
  }

  // 简单 OnDisk：data 文件存所有 posting，index 文件存元信息
  void save(const std::string &index_file, const std::string &data_file) const {
    // data_file format:
    // [id (int64_t)][vec (float[d])]
    {
      std::ofstream df(data_file, std::ios::binary | std::ios::trunc);
      if (!df) {
        throw std::runtime_error("open data file failed");
      }

      uint64_t cur = 0;
      for (int l = 0; l < nlist_; ++l) {
        const auto &lst = invlists_.list(l);
        // 写入该 list 的元信息（offset,size）
        // 注意：这里是保存时临时计算，加载后将直接使用，不需要再扫 data 文件重建
        // 值会在下面写入 idx 文件
        const uint64_t this_offset = cur;
        const uint64_t this_size = static_cast<uint64_t>(lst.size());

        for (const auto &p : lst) {
          df.write(reinterpret_cast<const char *>(&p.id), sizeof(p.id));
          df.write(reinterpret_cast<const char *>(p.vec.data()),
                   sizeof(float) * d_);
          cur += sizeof(int64_t) + sizeof(float) * static_cast<uint64_t>(d_);
        }

        // 通过 const_cast 仅用于保存阶段写入缓存元信息，不影响对外行为
        const_cast<std::vector<ListMeta> &>(list_meta_)[l] =
            ListMeta{this_offset, this_size};
      }
    }

    std::ofstream mf(index_file, std::ios::binary | std::ios::trunc);
    if (!mf) {
      throw std::runtime_error("open index file failed");
    }

    // magic
    const uint32_t magic = 0x49564631; // IVF1
    mf.write(reinterpret_cast<const char *>(&magic), sizeof(magic));
    mf.write(reinterpret_cast<const char *>(&d_), sizeof(d_));
    mf.write(reinterpret_cast<const char *>(&nlist_), sizeof(nlist_));
    mf.write(reinterpret_cast<const char *>(&nprobe_), sizeof(nprobe_));
    mf.write(reinterpret_cast<const char *>(&ntotal_), sizeof(ntotal_));

    // centers
    const auto &centers = quantizer_.centers();
    size_t csz = centers.size();
    mf.write(reinterpret_cast<const char *>(&csz), sizeof(csz));
    mf.write(reinterpret_cast<const char *>(centers.data()),
             sizeof(float) * csz);

    // 每个 list 的 (offset, size)
    for (int l = 0; l < nlist_; ++l) {
      const auto &m = list_meta_[l];
      mf.write(reinterpret_cast<const char *>(&m.offset_bytes),
               sizeof(m.offset_bytes));
      mf.write(reinterpret_cast<const char *>(&m.size), sizeof(m.size));
    }
  }

  static SimpleIVFIndex load(const std::string &index_file,
                             const std::string &data_file) {
    std::ifstream mf(index_file, std::ios::binary);
    if (!mf) {
      throw std::runtime_error("open index file failed");
    }

    uint32_t magic = 0;
    mf.read(reinterpret_cast<char *>(&magic), sizeof(magic));
    if (magic != 0x49564631) {
      throw std::runtime_error("bad index magic");
    }

    int d = 0, nlist = 0, nprobe = 0;
    int64_t ntotal = 0;
    mf.read(reinterpret_cast<char *>(&d), sizeof(d));
    mf.read(reinterpret_cast<char *>(&nlist), sizeof(nlist));
    mf.read(reinterpret_cast<char *>(&nprobe), sizeof(nprobe));
    mf.read(reinterpret_cast<char *>(&ntotal), sizeof(ntotal));

    SimpleIVFIndex idx(d, nlist);
    idx.nprobe_ = nprobe;
    idx.ntotal_ = ntotal;
    idx.trained_ = true;

    size_t csz = 0;
    mf.read(reinterpret_cast<char *>(&csz), sizeof(csz));
    std::vector<float> centers(csz);
    mf.read(reinterpret_cast<char *>(centers.data()), sizeof(float) * csz);
    idx.quantizer_.set_centers(std::move(centers));

    std::vector<ListMeta> list_meta(nlist);
    for (int l = 0; l < nlist; ++l) {
      mf.read(reinterpret_cast<char *>(&list_meta[l].offset_bytes),
              sizeof(list_meta[l].offset_bytes));
      mf.read(reinterpret_cast<char *>(&list_meta[l].size),
              sizeof(list_meta[l].size));
    }

    // 关键改动：load 不再扫描 data 文件重建倒排表
    // 仅记录 data 文件路径和每个 list 的 offset/size，查询时按需读取。
    idx.list_meta_ = std::move(list_meta);
    idx.on_disk_mode_ = true;
    idx.on_disk_data_file_ = data_file;
    idx.open_mmap_data();

    return idx;
  }

private:
  size_t posting_bytes() const {
    return sizeof(int64_t) + sizeof(float) * static_cast<size_t>(d_);
  }

  void open_mmap_data() {
    if (!on_disk_mode_) {
      return;
    }
    mmap_data_ = std::make_unique<ReadOnlyMMap>();
    mmap_data_->open(on_disk_data_file_);
  }

  void prefetch_lists(const std::vector<int> &probes) const {
    if (!mmap_data_ || !mmap_data_->valid()) {
      return;
    }
    const size_t rec_bytes = posting_bytes();
    for (int list_no : probes) {
      const auto &meta = list_meta_.at(static_cast<size_t>(list_no));
      const size_t bytes =
          static_cast<size_t>(meta.size) * static_cast<size_t>(rec_bytes);
      mmap_data_->advise_willneed(static_cast<size_t>(meta.offset_bytes),
                                  bytes);
    }
  }

  template <typename Heap>
  void scan_list_from_disk(int list_no, const float *q, int k, Heap &heap) const {
    if (!mmap_data_ || !mmap_data_->valid()) {
      throw std::runtime_error("mmap data is not ready");
    }

    const auto &meta = list_meta_.at(static_cast<size_t>(list_no));
    if (meta.size == 0) {
      return;
    }

    const size_t rec_bytes = posting_bytes();
    const size_t offset = static_cast<size_t>(meta.offset_bytes);
    const size_t bytes = static_cast<size_t>(meta.size) * rec_bytes;

    if (offset + bytes > mmap_data_->size()) {
      throw std::runtime_error("list metadata out of mmap range");
    }

    const uint8_t *p = mmap_data_->data() + offset;

    std::vector<float> vec(d_);
    for (uint64_t i = 0; i < meta.size; ++i) {
      int64_t id = -1;
      std::memcpy(&id, p, sizeof(id));
      p += sizeof(id);
      std::memcpy(vec.data(), p, sizeof(float) * static_cast<size_t>(d_));
      p += sizeof(float) * static_cast<size_t>(d_);

      float dis = l2sqr(q, vec.data(), d_);
      if (static_cast<int>(heap.size()) < k) {
        heap.emplace(dis, id);
      } else if (dis < heap.top().first) {
        heap.pop();
        heap.emplace(dis, id);
      }
    }
  }

  int d_;
  int nlist_;
  int nprobe_;
  int64_t ntotal_ = 0;
  bool trained_ = false;

  SimpleCoarseQuantizer quantizer_;
  InvertedLists invlists_;
  std::vector<ListMeta> list_meta_;

  bool on_disk_mode_ = false;
  std::string on_disk_data_file_;
  std::unique_ptr<ReadOnlyMMap> mmap_data_;
};

void print_result(const std::vector<float> &D, const std::vector<int64_t> &I,
                  int nq, int k) {
  for (int qi = 0; qi < nq; ++qi) {
    std::cout << "query " << qi << ": ";
    for (int j = 0; j < k; ++j) {
      int p = qi * k + j;
      std::cout << "(" << I[p] << ", " << D[p] << ") ";
    }
    std::cout << '\n';
  }
}

} // namespace

int main() {
  try {
    constexpr int d = 32;
    constexpr int nb = 10000;
    constexpr int nq = 5;
    constexpr int nlist = 64;
    constexpr int k = 5;

    const std::string data_dir =
        "/mnt/disk4/hezhiqiang/workspace/ivf-ondisk-data";
    std::filesystem::create_directories(data_dir);
    const std::string idx_file = data_dir + "/my_ivf_demo.index";
    const std::string dat_file = data_dir + "/my_ivf_demo.ivfdata";

    std::vector<float> xb(nb * d), xq(nq * d);
    fill_random(xb, 42);
    fill_random(xq, 123);

    SimpleIVFIndex index(d, nlist);
    index.train(xb);
    index.set_nprobe(12);
    index.add(xb);

    std::vector<float> D1;
    std::vector<int64_t> I1;
    index.search(xq, k, D1, I1);

    std::cout << "before save:\n";
    print_result(D1, I1, nq, k);

    index.save(idx_file, dat_file);
    auto loaded = SimpleIVFIndex::load(idx_file, dat_file);

    std::vector<float> D2;
    std::vector<int64_t> I2;
    loaded.search(xq, k, D2, I2);

    std::cout << "\nafter load:\n";
    print_result(D2, I2, nq, k);

    size_t diff = 0;
    for (size_t i = 0; i < I1.size(); ++i) {
      if (I1[i] != I2[i] || std::fabs(D1[i] - D2[i]) > 1e-6f) {
        ++diff;
      }
    }
    std::cout << "\ndiff count: " << diff << '\n';
    std::cout << "index file: " << idx_file << '\n';
    std::cout << "data file : " << dat_file << '\n';
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "exception: " << e.what() << '\n';
    return 1;
  }
}
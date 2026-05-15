#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <limits>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

struct Options {
  std::string workdir = "ivf_mmap_proto/data_cpp";
  int n = 20000;
  int d = 32;
  int nq = 100;
  int nlist = 64;
  int nprobe = 8;
  int k = 10;
  int kmeans_iters = 6;
  uint32_t seed = 42;
};

// IVF 索引在内存中的最小元数据：
// 1) centroids: coarse quantizer，shape = [nlist, d]
// 2) offsets: 倒排表边界，offsets[i]~offsets[i+1] 是第 i 个 list 在磁盘文件中的范围
struct IndexMeta {
  int d = 0;
  int nlist = 0;
  std::vector<uint64_t> offsets;
  std::vector<float> centroids; // nlist * d
};

float l2_sq(const float* a, const float* b, int d) {
  float s = 0.0f;
  for (int i = 0; i < d; ++i) {
    float v = a[i] - b[i];
    s += v * v;
  }
  return s;
}

int argmin_centroid(const float* x, const std::vector<float>& centroids, int nlist, int d) {
  int best = 0;
  float best_d2 = std::numeric_limits<float>::infinity();
  for (int c = 0; c < nlist; ++c) {
    float d2 = l2_sq(x, &centroids[static_cast<size_t>(c) * d], d);
    if (d2 < best_d2) {
      best_d2 = d2;
      best = c;
    }
  }
  return best;
}

void train_kmeans(const std::vector<float>& xb, int n, int d, int nlist, int iters, uint32_t seed,
                  std::vector<float>* centroids_out) {
  std::mt19937 rng(seed);
  std::uniform_int_distribution<int> uni(0, n - 1);
  std::vector<float> centroids(static_cast<size_t>(nlist) * d);
  for (int c = 0; c < nlist; ++c) {
    int idx = uni(rng);
    std::memcpy(&centroids[static_cast<size_t>(c) * d], &xb[static_cast<size_t>(idx) * d], sizeof(float) * d);
  }

  std::vector<int> assign(n, 0);
  std::vector<float> sums(static_cast<size_t>(nlist) * d, 0.0f);
  std::vector<int> counts(nlist, 0);

  for (int it = 0; it < iters; ++it) {
    std::fill(sums.begin(), sums.end(), 0.0f);
    std::fill(counts.begin(), counts.end(), 0);
    for (int i = 0; i < n; ++i) {
      const float* x = &xb[static_cast<size_t>(i) * d];
      int cid = argmin_centroid(x, centroids, nlist, d);
      assign[i] = cid;
      counts[cid] += 1;
      float* s = &sums[static_cast<size_t>(cid) * d];
      for (int j = 0; j < d; ++j) s[j] += x[j];
    }
    for (int c = 0; c < nlist; ++c) {
      float* cen = &centroids[static_cast<size_t>(c) * d];
      if (counts[c] == 0) {
        int idx = uni(rng);
        std::memcpy(cen, &xb[static_cast<size_t>(idx) * d], sizeof(float) * d);
      } else {
        float inv = 1.0f / static_cast<float>(counts[c]);
        const float* s = &sums[static_cast<size_t>(c) * d];
        for (int j = 0; j < d; ++j) cen[j] = s[j] * inv;
      }
    }
  }

  *centroids_out = std::move(centroids);
}

void write_binary(const std::string& path, const void* data, size_t bytes) {
  std::ofstream os(path, std::ios::binary | std::ios::trunc);
  if (!os) throw std::runtime_error("failed to open " + path);
  os.write(reinterpret_cast<const char*>(data), static_cast<std::streamsize>(bytes));
  if (!os) throw std::runtime_error("failed to write " + path);
}

IndexMeta build_index(const std::vector<float>& xb, int n, int d, int nlist, int kmeans_iters, uint32_t seed,
                      const std::string& workdir) {
  // Build 流程总览：
  // A. 用 kmeans 训练 coarse centroids
  // B. 每个向量分配到最近 centroid，得到 list_id[i]
  // C. 按 list_id stable_sort 得到全局重排 order
  // D. 生成 offsets（每个 list 的连续区间）
  // E. 按 order 重排向量与原始 id，写入磁盘
  //
  // 关键数据结构转换发生在：
  // xb(原始顺序) -> list_id(每个向量属于哪个 list)
  // list_id -> order(同一 list 连续)
  // order -> xb_sorted/ids_sorted(真正落盘布局)
  std::vector<float> centroids;
  train_kmeans(xb, n, d, nlist, kmeans_iters, seed, &centroids);

  std::vector<int> list_id(n, 0);
  for (int i = 0; i < n; ++i) {
    list_id[i] = argmin_centroid(&xb[static_cast<size_t>(i) * d], centroids, nlist, d);
  }

  std::vector<int> order(n);
  std::iota(order.begin(), order.end(), 0);
  std::stable_sort(order.begin(), order.end(), [&](int a, int b) { return list_id[a] < list_id[b]; });

  std::vector<uint64_t> counts(nlist, 0);
  for (int idx : order) counts[list_id[idx]] += 1;

  // offsets 是 list 的前缀和边界：
  // list i 的磁盘区间是 [offsets[i], offsets[i+1])，后续查询只需访问 probe 到的区间。
  std::vector<uint64_t> offsets(static_cast<size_t>(nlist) + 1, 0);
  for (int i = 0; i < nlist; ++i) offsets[i + 1] = offsets[i] + counts[i];

  std::vector<float> xb_sorted(static_cast<size_t>(n) * d);
  std::vector<int32_t> ids_sorted(n);
  // 
  for (int pos = 0; pos < n; ++pos) {
    int src = order[pos];
    std::memcpy(&xb_sorted[static_cast<size_t>(pos) * d], &xb[static_cast<size_t>(src) * d], sizeof(float) * d);
    ids_sorted[pos] = src;
  }

  ::mkdir(workdir.c_str(), 0755);
  // 落盘格式是 SoA 风格的两个并行数组：
  // vectors.f32: 排序后的向量数据（被 mmap）
  // ids.i32:     每个排序后位置对应的原始向量 id（被 mmap）
  // offsets/centroids: 查询时需要的小元数据（普通读入内存即可）
  write_binary(workdir + "/vectors.f32", xb_sorted.data(), xb_sorted.size() * sizeof(float));
  write_binary(workdir + "/ids.i32", ids_sorted.data(), ids_sorted.size() * sizeof(int32_t));
  write_binary(workdir + "/offsets.u64", offsets.data(), offsets.size() * sizeof(uint64_t));
  write_binary(workdir + "/centroids.f32", centroids.data(), centroids.size() * sizeof(float));

  IndexMeta m;
  m.d = d;
  m.nlist = nlist;
  m.offsets = std::move(offsets);
  m.centroids = std::move(centroids);
  return m;
}

struct MMapFile {
  int fd = -1;
  size_t bytes = 0;
  void* ptr = nullptr;
  ~MMapFile() {
    if (ptr && ptr != MAP_FAILED) munmap(ptr, bytes);
    if (fd >= 0) close(fd);
  }
};

MMapFile mmap_ro(const std::string& path) {
  MMapFile f;
  f.fd = open(path.c_str(), O_RDONLY);
  if (f.fd < 0) throw std::runtime_error("open failed: " + path);
  struct stat st {};
  if (fstat(f.fd, &st) != 0) throw std::runtime_error("fstat failed: " + path);
  f.bytes = static_cast<size_t>(st.st_size);
  f.ptr = mmap(nullptr, f.bytes, PROT_READ, MAP_SHARED, f.fd, 0);
  if (f.ptr == MAP_FAILED) throw std::runtime_error("mmap failed: " + path);
  return f;
}

std::vector<int> brute_force_topk(const std::vector<float>& xb, const float* q, int n, int d, int k) {
  std::vector<std::pair<float, int>> dist;
  dist.reserve(n);
  for (int i = 0; i < n; ++i) {
    dist.emplace_back(l2_sq(&xb[static_cast<size_t>(i) * d], q, d), i);
  }
  std::nth_element(dist.begin(), dist.begin() + k, dist.end(),
                   [](const auto& a, const auto& b) { return a.first < b.first; });
  dist.resize(k);
  std::sort(dist.begin(), dist.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
  std::vector<int> out;
  out.reserve(k);
  for (const auto& p : dist) out.push_back(p.second);
  return out;
}

std::pair<std::vector<int>, size_t> ivf_search_topk(const float* q, const IndexMeta& meta, const float* xb_mm,
                                                    const int32_t* ids_mm, int nprobe, int k) {
  // Search 流程总览：
  // 1) coarse 阶段：q 对所有 centroids 算距离，选 nprobe 个 list
  // 2) fine 阶段：仅扫描这些 list 的 [offsets[lid], offsets[lid+1]) 区间
  // 3) 在候选集合上取 top-k
  //
  // 关键转换：
  // q -> coarse(list id 集合) -> cand(候选对: 距离, 原始id) -> topk id
  std::vector<std::pair<float, int>> coarse;
  coarse.reserve(meta.nlist);
  for (int c = 0; c < meta.nlist; ++c) {
    coarse.emplace_back(l2_sq(q, &meta.centroids[static_cast<size_t>(c) * meta.d], meta.d), c);
  }
  std::nth_element(coarse.begin(), coarse.begin() + nprobe, coarse.end(),
                   [](const auto& a, const auto& b) { return a.first < b.first; });
  coarse.resize(nprobe);

  std::vector<std::pair<float, int>> cand;
  size_t cand_cnt = 0;
  for (const auto& p : coarse) {
    int lid = p.second;
    // 这里通过 offsets 把“逻辑 list id”转成“磁盘连续位置区间”。
    uint64_t s = meta.offsets[static_cast<size_t>(lid)];
    uint64_t e = meta.offsets[static_cast<size_t>(lid) + 1];
    cand_cnt += static_cast<size_t>(e - s);
    for (uint64_t pos = s; pos < e; ++pos) {
      // xb_mm/ids_mm 来自 mmap；访问 pos 时由 OS 按页调入对应文件页。
      const float* x = &xb_mm[static_cast<size_t>(pos) * meta.d];
      cand.emplace_back(l2_sq(x, q, meta.d), ids_mm[pos]);
    }
  }
  if (cand.empty()) return {{}, 0};
  int topk = std::min(k, static_cast<int>(cand.size()));
  std::nth_element(cand.begin(), cand.begin() + topk, cand.end(),
                   [](const auto& a, const auto& b) { return a.first < b.first; });
  cand.resize(topk);
  std::sort(cand.begin(), cand.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
  std::vector<int> out;
  out.reserve(topk);
  for (const auto& c : cand) out.push_back(c.second);
  return {out, cand_cnt};
}

double recall_at_k(const std::vector<int>& gt, const std::vector<int>& pred) {
  int hit = 0;
  for (int g : gt) {
    if (std::find(pred.begin(), pred.end(), g) != pred.end()) hit++;
  }
  return gt.empty() ? 0.0 : static_cast<double>(hit) / static_cast<double>(gt.size());
}

Options parse_args(int argc, char** argv) {
  Options opt;
  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    auto need = [&](const char* name) {
      if (i + 1 >= argc) throw std::runtime_error(std::string("missing value for ") + name);
      return std::string(argv[++i]);
    };
    if (a == "--workdir") opt.workdir = need("--workdir");
    else if (a == "--n") opt.n = std::stoi(need("--n"));
    else if (a == "--d") opt.d = std::stoi(need("--d"));
    else if (a == "--nq") opt.nq = std::stoi(need("--nq"));
    else if (a == "--nlist") opt.nlist = std::stoi(need("--nlist"));
    else if (a == "--nprobe") opt.nprobe = std::stoi(need("--nprobe"));
    else if (a == "--k") opt.k = std::stoi(need("--k"));
    else if (a == "--kmeans-iters") opt.kmeans_iters = std::stoi(need("--kmeans-iters"));
    else if (a == "--seed") opt.seed = static_cast<uint32_t>(std::stoul(need("--seed")));
    else throw std::runtime_error("unknown arg: " + a);
  }
  if (opt.nprobe <= 0 || opt.nprobe > opt.nlist) throw std::runtime_error("nprobe must be in [1, nlist]");
  return opt;
}

int main(int argc, char** argv) {
  try {
    // Main 主流程：
    // 1) 解析参数并生成随机 base/query
    // 2) build_index：训练 coarse + 生成倒排布局并落盘
    // 3) mmap 打开 vectors/ids 文件，得到“像内存数组一样”的只读视图
    // 4) 对每个 query：跑 brute_force 得 GT，再跑 ivf_search 得预测并统计 recall/候选量
    // 5) 输出性能与 I/O 估算指标
    Options opt = parse_args(argc, argv);

    std::mt19937 rng(opt.seed);
    std::normal_distribution<float> normal(0.0f, 1.0f);
    std::vector<float> xb(static_cast<size_t>(opt.n) * opt.d);
    std::vector<float> xq(static_cast<size_t>(opt.nq) * opt.d);
    for (float& v : xb) v = normal(rng);
    for (float& v : xq) v = normal(rng);

    auto t0 = std::chrono::steady_clock::now();
    IndexMeta meta = build_index(xb, opt.n, opt.d, opt.nlist, opt.kmeans_iters, opt.seed, opt.workdir);
    auto t1 = std::chrono::steady_clock::now();
    MMapFile vec_f = mmap_ro(opt.workdir + "/vectors.f32");
    MMapFile ids_f = mmap_ro(opt.workdir + "/ids.i32");
    auto t2 = std::chrono::steady_clock::now();

    const float* xb_mm = reinterpret_cast<const float*>(vec_f.ptr);
    const int32_t* ids_mm = reinterpret_cast<const int32_t*>(ids_f.ptr);
    // 数据形态转换点：
    // 文件字节流 -> mmap 虚拟地址 -> 按类型 reinterpret_cast 成数组视图。
    // 之后代码按 xb_mm[pos*d + j] 的形式访问，底层由 OS 懒加载对应页。

    double recall_sum = 0.0;
    size_t cand_sum = 0;
    auto s0 = std::chrono::steady_clock::now();
    for (int i = 0; i < opt.nq; ++i) {
      const float* q = &xq[static_cast<size_t>(i) * opt.d];
      // gt: 全量暴力检索的 top-k（作为评测基准）
      std::vector<int> gt = brute_force_topk(xb, q, opt.n, opt.d, opt.k);
      // pred_and_cnt.first: IVF 预测 top-k id；pred_and_cnt.second: 本次扫描候选数
      auto pred_and_cnt = ivf_search_topk(q, meta, xb_mm, ids_mm, opt.nprobe, opt.k);
      recall_sum += recall_at_k(gt, pred_and_cnt.first);
      cand_sum += pred_and_cnt.second;
    }
    auto s1 = std::chrono::steady_clock::now();

    double build_s = std::chrono::duration<double>(t1 - t0).count();
    double mmap_s = std::chrono::duration<double>(t2 - t1).count();
    double search_s = std::chrono::duration<double>(s1 - s0).count();
    double avg_recall = recall_sum / static_cast<double>(opt.nq);
    double avg_cands = static_cast<double>(cand_sum) / static_cast<double>(opt.nq);
    double cand_ratio = avg_cands / static_cast<double>(opt.n);
    double bytes_per_query = avg_cands * static_cast<double>(opt.d) * sizeof(float);
    double bytes_full = static_cast<double>(opt.n) * opt.d * sizeof(float);

    std::cout << "=== IVF + mmap prototype (C++) ===\n";
    std::cout << "N=" << opt.n << ", D=" << opt.d << ", NQ=" << opt.nq << ", nlist=" << opt.nlist
              << ", nprobe=" << opt.nprobe << ", k=" << opt.k << "\n";
    std::cout << "build_index_time=" << build_s << "s, mmap_time=" << mmap_s << "s\n";
    std::cout << "search_time=" << search_s << "s, qps=" << (opt.nq / search_s) << "\n";
    std::cout << "avg_recall@" << opt.k << "=" << avg_recall << "\n";
    std::cout << "avg_candidates=" << avg_cands << "/" << opt.n << " (" << (cand_ratio * 100.0) << "% of full scan)\n";
    std::cout << "estimated_vec_bytes_read_per_query=" << (bytes_per_query / (1024.0 * 1024.0))
              << " MiB (full scan " << (bytes_full / (1024.0 * 1024.0)) << " MiB)\n";
    std::cout << "Interpretation: larger nprobe improves recall but reads/scans more data.\n";
    return 0;
  } catch (const std::exception& e) {
    std::cerr << "error: " << e.what() << "\n";
    return 1;
  }
}

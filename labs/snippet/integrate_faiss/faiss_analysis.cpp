#include "faiss/IndexPreTransform.h"
#include "faiss/VectorTransform.h"
#include "faiss/index_factory.h"
#include <algorithm>
#include <atomic>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <faiss/IndexFlat.h>
#include <faiss/IndexHNSW.h>
#include <faiss/IndexIVF.h>
#include <faiss/IndexIVFFlat.h>
#include <faiss/IndexIVFPQ.h>
#include <faiss/IndexIVFRaBitQ.h>
#include <faiss/IndexPQ.h>
#include <faiss/IndexRaBitQ.h>
#include <faiss/IndexRefine.h>
#include <faiss/IndexScalarQuantizer.h>
#include <faiss/MetricType.h>
#include <faiss/index_io.h>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <mutex>
#include <random>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <thread>
#include <unistd.h>
#include <unordered_set>
#include <utility>
#include <vector>
#ifdef HAVE_VECML
#include "vecml_shim/vecml_shim.h"
#endif
#include "cli_utils.h"
#include "util/results_utils.h"

// --- Lightweight step logger (default on; set FAISS_ANALYSIS_LOG=0 to disable)
// ---
static bool analysis_log_enabled() {
  const char *v = ::getenv("FAISS_ANALYSIS_LOG");
  if (!v)
    return true;
  std::string s(v);
  for (auto &c : s)
    c = (char)std::tolower((unsigned char)c);
  return !(s == "0" || s == "false" || s == "off");
}
static std::string now_ts_simple() {
  using namespace std::chrono;
  auto now = system_clock::now();
  auto t = system_clock::to_time_t(now);
  std::tm tm;
#if defined(_WIN32)
  localtime_s(&tm, &t);
#else
  localtime_r(&t, &tm);
#endif
  char buf[32];
  std::strftime(buf, sizeof(buf), "%H:%M:%S", &tm);
  auto ms = duration_cast<milliseconds>(now.time_since_epoch()) % 1000;
  char out[48];
  snprintf(out, sizeof(out), "%s.%03lld", buf, (long long)ms.count());
  return std::string(out);
}
static void log_step(const std::string &tag, const std::string &msg) {
  if (!analysis_log_enabled())
    return;
  std::cerr << "[" << now_ts_simple() << "] [STEP] " << tag << ": " << msg
            << "\n";
}

// 通过序列化来估算索引内存占用：写到临时文件，取文件大小（MB）
static double measureIndexSerializedSize(faiss::Index *index) {
  if (!index)
    return 0.0;
  char tmpl[] = "/tmp/faiss_index_memXXXXXX";
  int fd = mkstemp(tmpl);
  if (fd == -1) {
    return 0.0;
  }
  close(fd); // 只保留文件名
  try {
    faiss::write_index(index, tmpl);
    struct stat st;
    double mb = 0.0;
    if (::stat(tmpl, &st) == 0) {
      mb = (double)st.st_size / (1024.0 * 1024.0);
    }
    ::unlink(tmpl);
    return mb;
  } catch (...) {
    ::unlink(tmpl);
    return 0.0;
  }
}

// ---------------------------------------------------------------------------

static double computeDirectorySizeMB(const std::string &path) {
  if (path.empty()) {
    return -1.0;
  }
  std::error_code ec;
  std::filesystem::path dir(path);
  if (!std::filesystem::exists(dir, ec)) {
    return 0.0;
  }
  std::uintmax_t total_blocks = 0;
  for (auto it = std::filesystem::recursive_directory_iterator(
           dir, std::filesystem::directory_options::skip_permission_denied, ec);
       it != std::filesystem::recursive_directory_iterator();
       it.increment(ec)) {
    if (ec) {
      continue;
    }
    const auto &entry = *it;
    if (!entry.is_regular_file(ec)) {
      continue;
    }
    struct stat st;
    if (::stat(entry.path().c_str(), &st) == 0) {
      total_blocks += static_cast<std::uintmax_t>(st.st_blocks);
    }
  }
  double bytes = static_cast<double>(total_blocks) *
                 512.0; // POSIX reports blocks in 512-byte units
  return bytes / (1024.0 * 1024.0);
}

// ---- SIFT1M helpers (fvecs/ivecs readers) ----
static float *fvecs_read_all(const char *fname, size_t *d_out, size_t *n_out) {
  FILE *f = fopen(fname, "rb");
  if (!f) {
    std::perror("fopen");
    std::cerr << "could not open " << fname << std::endl;
    return nullptr;
  }
  int d = 0;
  size_t nr = fread(&d, 1, sizeof(int), f);
  if (nr != sizeof(int)) {
    fclose(f);
    return nullptr;
  }
  if (!(d > 0 && d < 1000000)) {
    fclose(f);
    return nullptr;
  }
  fseek(f, 0, SEEK_SET);
  struct stat st;
  fstat(fileno(f), &st);
  size_t sz = (size_t)st.st_size;
  if (sz % ((size_t)(d + 1) * 4) != 0) {
    fclose(f);
    return nullptr;
  }
  size_t n = sz / ((size_t)(d + 1) * 4);
  *d_out = (size_t)d;
  *n_out = n;
  float *x = new float[n * (size_t)(d + 1)];
  size_t want = n * (size_t)(d + 1);
  size_t nrf = fread(x, sizeof(float), want, f);
  fclose(f);
  if (nrf != want) {
    delete[] x;
    return nullptr;
  }
  // shift rows to remove header
  for (size_t i = 0; i < n; i++) {
    memmove(x + i * (size_t)d, x + 1 + i * (size_t)(d + 1),
            (size_t)d * sizeof(*x));
  }
  return x;
}

static int *ivecs_read_all(const char *fname, size_t *d_out, size_t *n_out) {
  return reinterpret_cast<int *>(fvecs_read_all(fname, d_out, n_out));
}

struct Options {
  int dim = 128;
  int nb = 20000;
  int nq = 500;
  int k = 10;

  // Support list variants (if non-empty, they override the single value)
  std::vector<int> dim_list;
  std::vector<int> nb_list;
  std::vector<int> nq_list;
  std::vector<int> k_list;

  // HNSW
  int hnsw_M = 32;
  int efC = 200;
  int efS = 64;
  std::vector<int> hnsw_M_list;
  std::vector<int> efC_list;
  std::vector<int> efS_list;

  // PQ (for HNSW-PQ)
  int pq_m = 16;
  int pq_nbits = 8;
  double pq_train_ratio = 1.0; // fraction of nb used for PQ training [0,1]
  std::vector<int> pq_m_list;
  std::vector<int> pq_nbits_list;
  std::vector<double> pq_train_ratio_list; // allow multiple training ratios

  // SQ (for HNSW-SQ) - removed, now specified in which parameter
  // int sq_qtype = (int)faiss::ScalarQuantizer::QuantizerType::QT_8bit;
  // std::vector<int> sq_qtype_list;

  // Which tests to run: all, hnsw_flat, hnsw_sq4, hnsw_sq8, hnsw_pq,
  // hnsw_rabitq, ivf_flat, ivf_sq4, ivf_sq8, ivf_pq, ivf_rbq, rabitq
  std::vector<std::string> which = {"all"};

  // SIFT1M dataset support
  // If sift1m_dir is non-empty, load SIFT1M from this directory
  // (expects sift_base.fvecs, sift_query.fvecs, sift_groundtruth.ivecs)
  // and override dim/nb/nq/k based on file contents and limits provided
  // by dim, nb, nq, k options (nb/nq/k act as upper bounds if set).
  bool use_sift1m = false;
  std::string sift1m_dir; // e.g., "sift1M"
  // Optional dataset limiting/override when using SIFT1M (defaults: off)
  int sift_nb_limit = -1;   // if >0, limit number of base vectors
  int sift_nq_limit = -1;   // if >0, limit number of queries
  int sift_k_override = -1; // if >0, override K per query (cap by GT)

  // IVF parameters (for IVF-Flat / IVF-PQ / IVF-SQ)
  int ivf_nlist = 256;
  int ivf_nprobe = 8;
  std::vector<int> ivf_nlist_list;
  std::vector<int> ivf_nprobe_list;

  // RaBitQ (for HNSW/IVF-RaBitQ)
  int rabitq_qb = 8;            // query quantization bits
  bool rabitq_centered = false; // whether to center queries
  std::vector<int> rabitq_qb_list;
  std::vector<int> rabitq_centered_list;

  // RaBitQ Refine (for IVF-RaBitQ refine two-stage)
  // refine type: flat|sq8|sq4|fp16|bf16 (bf16 falls back to fp16 if
  // unsupported)
  std::string rbq_refine_type = "flat";
  std::vector<std::string> rbq_refine_type_list;
  int rbq_refine_k = 2;
  std::vector<int> rbq_refine_k_list;

  // Output
  std::string out_csv = "hnsw_index_types_results.csv";
  std::string save_data_dir =
      ""; // if not empty, save test data to this directory
  std::string load_data_dir =
      ""; // if not empty, load test data from this directory

  // Multi-thread options
  int mt_threads = 0; // 0 for auto-detect

  // VecML options
  std::string vecml_base_path =
      ""; // path to vecml SDK dir (contains include/lib)
  std::string vecml_license_path = "license.txt";
  int vecml_threads = 16; // threads for vecml attach/add operations

  // Whether to build transposed centroids for PQ (optimization)
  bool transpose_centroid = false;
};

class PQBenchmark {
private:
  int dim;
  int nb;
  int nq;
  int k;
  bool
      transpose_centroid; // control whether to sync transposed centroids for PQ
  int mt_threads;
  std::vector<float> database;
  std::vector<float> queries;
  std::vector<faiss::idx_t> ground_truth;
  std::string save_data_dir;               // directory to save test data
  std::string dataset_name = "std-normal"; // data source name

public:
  PQBenchmark(int dim = 128, int nb = 20000, int nq = 500, int k = 10,
              bool transpose_centroid = false, const std::string &data_dir = "",
              const std::string &load_dir = "", int mt_threads_option = 0,
              bool skip_init = false)
      : dim(dim), nb(nb), nq(nq), k(k), transpose_centroid(transpose_centroid),
        mt_threads(mt_threads_option), save_data_dir(data_dir) {
    std::cout << "=== HNSW Index Types Benchmark (C++) ===" << std::endl;
    std::cout << "配置: dim=" << dim << ", nb=" << nb << ", nq=" << nq
              << ", k=" << k << std::endl;
    if (!skip_init) {
      if (!load_dir.empty()) {
        std::cout << "从 " << load_dir << " 加载测试数据..." << std::endl;
        if (loadTestData(load_dir)) {
          std::cout << "数据加载成功!" << std::endl;
        } else {
          std::cout << "数据加载失败，生成新数据..." << std::endl;
          generateData();
          computeGroundTruth();
        }
      } else {
        generateData();
        computeGroundTruth();
      }

      if (!save_data_dir.empty()) {
        saveTestData();
      }
    }
  }

  // Accessors for current dataset config
  int getDim() const { return dim; }
  int getNb() const { return nb; }
  int getNq() const { return nq; }
  int getK() const { return k; }
  const std::string &getDatasetName() const { return dataset_name; }

  void generateData() {
    std::cout << "生成测试数据..." << std::endl;

    std::mt19937 rng(42);
    std::normal_distribution<float> dist(0.0, 1.0);

    database.resize(nb * dim);
    queries.resize(nq * dim);

    // 生成数据库向量
    for (int i = 0; i < nb * dim; i++) {
      database[i] = dist(rng);
    }

    // 生成查询向量
    for (int i = 0; i < nq * dim; i++) {
      queries[i] = dist(rng);
    }

    // L2规范化
    normalizeVectors(database.data(), nb, dim);
    normalizeVectors(queries.data(), nq, dim);
  }

  void normalizeVectors(float *vectors, int n, int d) {
    for (int i = 0; i < n; i++) {
      float norm = 0.0;
      for (int j = 0; j < d; j++) {
        norm += vectors[i * d + j] * vectors[i * d + j];
      }
      norm = std::sqrt(norm);
      if (norm > 0) {
        for (int j = 0; j < d; j++) {
          vectors[i * d + j] /= norm;
        }
      }
    }
  }

  void computeGroundTruth() {
    std::cout << "计算真实最近邻..." << std::endl;

    faiss::IndexFlatL2 index(dim);
    index.add(nb, database.data());

    std::vector<float> distances(nq * k);
    ground_truth.resize(nq * k);

    index.search(nq, queries.data(), k, distances.data(), ground_truth.data());
  }

  void saveTestData() {
    if (save_data_dir.empty())
      return;

    // Create directory if it doesn't exist
    std::string mkdir_cmd = "mkdir -p " + save_data_dir;
    if (system(mkdir_cmd.c_str()) != 0) {
      std::cerr << "警告: 无法创建目录 " << save_data_dir << std::endl;
      return;
    }

    std::cout << "保存测试数据到 " << save_data_dir << "..." << std::endl;

    // Save database vectors
    std::string db_file = save_data_dir + "/database_" + std::to_string(dim) +
                          "d_" + std::to_string(nb) + "n.fvecs";
    saveFVecs(db_file, database, nb, dim);

    // Save query vectors
    std::string query_file = save_data_dir + "/queries_" + std::to_string(dim) +
                             "d_" + std::to_string(nq) + "n.fvecs";
    saveFVecs(query_file, queries, nq, dim);

    // Save ground truth
    std::string gt_file = save_data_dir + "/groundtruth_" + std::to_string(nq) +
                          "q_" + std::to_string(k) + "k.ivecs";
    saveIVecs(gt_file, ground_truth, nq, k);

    std::cout << "数据已保存: " << db_file << ", " << query_file << ", "
              << gt_file << std::endl;
  }

  void saveFVecs(const std::string &filename, const std::vector<float> &data,
                 int n, int d) {
    std::ofstream file(filename, std::ios::binary);
    if (!file.is_open()) {
      std::cerr << "错误: 无法创建文件 " << filename << std::endl;
      return;
    }

    for (int i = 0; i < n; i++) {
      file.write(reinterpret_cast<const char *>(&d), sizeof(int));
      file.write(reinterpret_cast<const char *>(data.data() + i * d),
                 d * sizeof(float));
    }
    file.close();
  }

  void saveIVecs(const std::string &filename,
                 const std::vector<faiss::idx_t> &data, int n, int d) {
    std::ofstream file(filename, std::ios::binary);
    if (!file.is_open()) {
      std::cerr << "错误: 无法创建文件 " << filename << std::endl;
      return;
    }

    for (int i = 0; i < n; i++) {
      file.write(reinterpret_cast<const char *>(&d), sizeof(int));
      for (int j = 0; j < d; j++) {
        int val = static_cast<int>(data[i * d + j]);
        file.write(reinterpret_cast<const char *>(&val), sizeof(int));
      }
    }
    file.close();
  }

  bool loadTestData(const std::string &load_dir) {
    try {
      // 构建文件路径
      std::string db_file = load_dir + "/database_" + std::to_string(dim) +
                            "d_" + std::to_string(nb) + "n.fvecs";
      std::string query_file = load_dir + "/queries_" + std::to_string(dim) +
                               "d_" + std::to_string(nq) + "n.fvecs";
      std::string gt_file = load_dir + "/groundtruth_" + std::to_string(nq) +
                            "q_" + std::to_string(k) + "k.ivecs";

      // 检查文件是否存在
      if (!fileExists(db_file) || !fileExists(query_file) ||
          !fileExists(gt_file)) {
        std::cout << "部分文件不存在，需要的文件:" << std::endl;
        std::cout << "  " << db_file << std::endl;
        std::cout << "  " << query_file << std::endl;
        std::cout << "  " << gt_file << std::endl;
        return false;
      }

      // 加载数据
      if (!loadFVecs(db_file, database, nb, dim)) {
        std::cerr << "加载数据库向量失败: " << db_file << std::endl;
        return false;
      }

      if (!loadFVecs(query_file, queries, nq, dim)) {
        std::cerr << "加载查询向量失败: " << query_file << std::endl;
        return false;
      }

      if (!loadIVecs(gt_file, ground_truth, nq, k)) {
        std::cerr << "加载ground truth失败: " << gt_file << std::endl;
        return false;
      }

      std::cout << "成功加载: " << nb << " 个数据库向量, " << nq
                << " 个查询向量, ground truth" << std::endl;
      return true;
    } catch (const std::exception &e) {
      std::cerr << "加载数据时发生异常: " << e.what() << std::endl;
      return false;
    }
  }

  bool fileExists(const std::string &filename) {
    std::ifstream file(filename);
    return file.good();
  }

  bool loadFVecs(const std::string &filename, std::vector<float> &data,
                 int expected_n, int expected_d) {
    std::ifstream file(filename, std::ios::binary);
    if (!file.is_open()) {
      return false;
    }

    data.resize(expected_n * expected_d);

    for (int i = 0; i < expected_n; i++) {
      int d;
      file.read(reinterpret_cast<char *>(&d), sizeof(int));
      if (file.fail() || d != expected_d) {
        std::cerr << "维度不匹配: 期望 " << expected_d << ", 实际 " << d
                  << " (在向量 " << i << ")" << std::endl;
        return false;
      }

      file.read(reinterpret_cast<char *>(data.data() + i * expected_d),
                expected_d * sizeof(float));
      if (file.fail()) {
        std::cerr << "读取向量数据失败: 向量 " << i << std::endl;
        return false;
      }
    }

    file.close();
    return true;
  }

  bool loadIVecs(const std::string &filename, std::vector<faiss::idx_t> &data,
                 int expected_n, int expected_d) {
    std::ifstream file(filename, std::ios::binary);
    if (!file.is_open()) {
      return false;
    }

    data.resize(expected_n * expected_d);

    for (int i = 0; i < expected_n; i++) {
      int d;
      file.read(reinterpret_cast<char *>(&d), sizeof(int));
      if (file.fail() || d != expected_d) {
        std::cerr << "k值不匹配: 期望 " << expected_d << ", 实际 " << d
                  << " (在查询 " << i << ")" << std::endl;
        return false;
      }

      for (int j = 0; j < expected_d; j++) {
        int val;
        file.read(reinterpret_cast<char *>(&val), sizeof(int));
        if (file.fail()) {
          std::cerr << "读取ground truth失败: 查询 " << i << ", 位置 " << j
                    << std::endl;
          return false;
        }
        data[i * expected_d + j] = static_cast<faiss::idx_t>(val);
      }
    }

    file.close();
    return true;
  }

  // Load SIFT1M dataset from directory
  bool loadSift1M(const std::string &dir, int nb_limit = -1, int nq_limit = -1,
                  int k_override = -1) {
    try {
      std::string base_file = dir + "/sift_base.fvecs";
      std::string query_file = dir + "/sift_query.fvecs";
      std::string gt_file = dir + "/sift_groundtruth.ivecs";

      size_t d_b = 0, n_b = 0;
      float *xb = fvecs_read_all(base_file.c_str(), &d_b, &n_b);
      if (!xb) {
        std::cerr << "SIFT1M: failed to read " << base_file << std::endl;
        return false;
      }
      size_t d_q = 0, n_q = 0;
      float *xq = fvecs_read_all(query_file.c_str(), &d_q, &n_q);
      if (!xq) {
        delete[] xb;
        std::cerr << "SIFT1M: failed to read " << query_file << std::endl;
        return false;
      }
      if (d_b == 0 || d_b != d_q) {
        delete[] xb;
        delete[] xq;
        std::cerr << "SIFT1M: dim mismatch or zero" << std::endl;
        return false;
      }
      size_t k_gt = 0, n_gt = 0;
      int *gt = ivecs_read_all(gt_file.c_str(), &k_gt, &n_gt);
      if (!gt) {
        delete[] xb;
        delete[] xq;
        std::cerr << "SIFT1M: failed to read " << gt_file << std::endl;
        return false;
      }
      if (n_gt != n_q) {
        delete[] xb;
        delete[] xq;
        delete[] gt;
        std::cerr << "SIFT1M: ground truth nq mismatch" << std::endl;
        return false;
      }

      size_t use_nb = (nb_limit > 0) ? std::min((size_t)nb_limit, n_b) : n_b;
      size_t use_nq = (nq_limit > 0) ? std::min((size_t)nq_limit, n_q) : n_q;
      size_t use_k = (k_override > 0) ? std::min((size_t)k_override, k_gt)
                                      : std::min((size_t)k, k_gt);
      if (use_nq == 0 || use_nb == 0 || use_k == 0) {
        delete[] xb;
        delete[] xq;
        delete[] gt;
        std::cerr << "SIFT1M: invalid limits after applying nb/nq/k"
                  << std::endl;
        return false;
      }

      dim = (int)d_b;
      nb = (int)use_nb;
      nq = (int)use_nq;
      k = (int)use_k;
      database.assign(nb * dim, 0.0f);
      queries.assign(nq * dim, 0.0f);
      for (size_t i = 0; i < use_nb; ++i) {
        std::memcpy(database.data() + i * (size_t)dim, xb + i * (size_t)dim,
                    (size_t)dim * sizeof(float));
      }
      for (size_t i = 0; i < use_nq; ++i) {
        std::memcpy(queries.data() + i * (size_t)dim, xq + i * (size_t)dim,
                    (size_t)dim * sizeof(float));
      }
      ground_truth.assign(nq * k, -1);
      for (size_t qi = 0; qi < use_nq; ++qi) {
        for (size_t j = 0; j < use_k; ++j) {
          ground_truth[qi * (size_t)k + j] =
              (faiss::idx_t)gt[qi * (size_t)k_gt + j];
        }
      }

      delete[] xb;
      delete[] xq;
      delete[] gt;
      // Set dataset name from directory leaf if present (e.g., "sift1M")
      try {
        std::filesystem::path p(dir);
        if (!p.filename().empty()) {
          dataset_name = p.filename().string();
        } else {
          dataset_name = "sift1M";
        }
      } catch (...) {
        dataset_name = "sift1M";
      }

      std::cout << "加载 SIFT1M 成功: dim=" << dim << ", nb=" << nb
                << ", nq=" << nq << ", k=" << k << std::endl;
      return true;
    } catch (const std::exception &e) {
      std::cerr << "SIFT1M: exception: " << e.what() << std::endl;
      return false;
    }
  }

  struct TestResult {
    std::string method;  // HNSW-Flat / HNSW-SQ / HNSW-PQ
    std::string dataset; // "std-normal" or dataset name (e.g., sift1M)
    // Dataset level
    int dim = 0;
    int nb = 0;
    int nq = 0;
    int k = 0;
    int hnsw_M = 0;
    int efC = 0;
    int efS = 0;
    int ivf_nlist = 0; // IVF params
    int ivf_nprobe = 0;
    int pq_m = 0;
    int pq_nbits = 0;
    double pq_train_ratio = 1.0; // valid for PQ rows
    int qtype = -1;              // for SQ
    int rabitq_qb = 0;           // for RaBitQ
    int rabitq_centered = 0;     // 0/1 for printing
    std::string refine_type;     // rbq_refine only
    int refine_k = 0;            // rbq_refine only

    double train_time = 0.0;     // seconds
    double add_time = 0.0;       // seconds
    double build_time = 0.0;     // train + add seconds
    double search_time_ms = 0.0; // per query
    double recall_1 = 0.0;
    double recall_5 = 0.0;
    double recall_k = 0.0;
    double mbs_on_disk = 0.0; // serialized index size in MB
    double compression_ratio = 0.0;

    // Multi-thread smoke metrics (optional)
    bool has_mt = false;
    int mt_threads = 0;
    double mt_search_time_ms = 0.0;
    double mt_recall_k = 0.0;
    double mt_recall_1 = 0.0;
    double mt_recall_5 = 0.0;
  };

  double computeRecall(const std::vector<faiss::idx_t> &pred_labels,
                       const std::vector<faiss::idx_t> &true_labels,
                       int top_k) {
    double recall_sum = 0.0;

    for (int i = 0; i < nq; i++) {
      std::unordered_set<faiss::idx_t> true_set;
      true_set.reserve(top_k * 2);
      for (int j = 0; j < top_k; j++) {
        true_set.insert(true_labels[i * k + j]);
      }
      int hit = 0;
      for (int j = 0; j < top_k; j++) {
        if (true_set.find(pred_labels[i * k + j]) != true_set.end())
          ++hit;
      }
      if (top_k > 0) {
        recall_sum += static_cast<double>(hit) / top_k;
      }
    }

    return recall_sum / nq;
  }

  // Standard 1-NN recall@K: fraction of queries where the true nearest
  // neighbor (ground_truth's first entry per query) appears in the top-K
  // predicted labels. Monotonically non-decreasing with K and within [0,1].
  double computeRecall1NN(const std::vector<faiss::idx_t> &pred_labels,
                          int top_k) {
    if (nq <= 0 || k <= 0 || top_k <= 0)
      return 0.0;
    int K = std::min(top_k, k);
    int hit_count = 0;
    for (int i = 0; i < nq; ++i) {
      faiss::idx_t true_nn = ground_truth[i * k + 0];
      bool hit = false;
      for (int j = 0; j < K; ++j) {
        if (pred_labels[i * k + j] == true_nn) {
          hit = true;
          break;
        }
      }
      if (hit)
        ++hit_count;
    }
    return nq > 0 ? (double)hit_count / (double)nq : 0.0;
  }

  struct MultiThreadResult {
    int threads = 0;
    double ms_per_query = 0.0;
    std::vector<faiss::idx_t> labels;
  };

  template <typename SearchShardFn>
  bool runMultiThreadSearch(const std::string &method_name,
                            SearchShardFn &&search_shard,
                            MultiThreadResult &result) {
    // Require explicit --mt-threads to run multi-thread smoke tests. Do not
    // auto-enable based on hardware_concurrency(): the user must opt-in.
    int threads = mt_threads;
    if (threads <= 1 || nq <= 0 || k <= 0) {
      return false;
    }

    result.threads = threads;
    result.labels.assign(
        static_cast<std::size_t>(nq) * static_cast<std::size_t>(k), -1);
    std::vector<float> distances(static_cast<std::size_t>(nq) *
                                 static_cast<std::size_t>(k));
    std::vector<std::thread> workers;
    workers.reserve(static_cast<std::size_t>(threads));
    std::atomic<bool> failed{false};
    std::string failure_message;
    std::mutex failure_mutex;

    auto shard_wrapper = [&](std::size_t start, std::size_t count) {
      if (count == 0 || failed.load(std::memory_order_relaxed)) {
        return;
      }
      try {
        search_shard(start, count,
                     distances.data() + start * static_cast<std::size_t>(k),
                     result.labels.data() +
                         start * static_cast<std::size_t>(k));
      } catch (const std::exception &e) {
        failed.store(true, std::memory_order_relaxed);
        std::lock_guard<std::mutex> lock(failure_mutex);
        if (failure_message.empty()) {
          failure_message = e.what();
        }
      } catch (...) {
        failed.store(true, std::memory_order_relaxed);
        std::lock_guard<std::mutex> lock(failure_mutex);
        if (failure_message.empty()) {
          failure_message = "unknown error";
        }
      }
    };

    std::size_t total_queries = static_cast<std::size_t>(nq);
    std::size_t base_chunk =
        threads > 0 ? total_queries / static_cast<std::size_t>(threads) : 0;
    std::size_t remainder =
        threads > 0 ? total_queries % static_cast<std::size_t>(threads) : 0;
    std::size_t cursor = 0;
    auto mt_t0 = std::chrono::high_resolution_clock::now();
    for (int t = 0; t < threads; ++t) {
      std::size_t count =
          base_chunk + ((static_cast<std::size_t>(t) < remainder) ? 1 : 0);
      std::size_t start = cursor;
      cursor += count;
      if (count == 0) {
        continue;
      }
      workers.emplace_back(
          [&, start, count]() { shard_wrapper(start, count); });
    }
    for (auto &worker : workers) {
      worker.join();
    }
    auto mt_t1 = std::chrono::high_resolution_clock::now();

    if (failed.load(std::memory_order_relaxed)) {
      std::cout << "    [MT] " << method_name
                << " multi-thread search failed: " << failure_message
                << std::endl;
      return false;
    }

    double total_ms =
        std::chrono::duration<double, std::milli>(mt_t1 - mt_t0).count();
    result.ms_per_query = nq > 0 ? total_ms / static_cast<double>(nq) : 0.0;
    return true;
  }

  void applyMultiThreadMetrics(const std::string &method_name, TestResult &r,
                               const std::vector<faiss::idx_t> *baseline_labels,
                               const MultiThreadResult &mt,
                               bool adopt_as_primary_if_no_baseline) {
    r.has_mt = true;
    r.mt_threads = mt.threads;
    r.mt_search_time_ms = mt.ms_per_query;
    r.mt_recall_k = computeRecall(mt.labels, ground_truth, k);
    r.mt_recall_1 = (k > 0) ? computeRecall(mt.labels, ground_truth, 1) : 0.0;
    int recall_at_5 = std::min(5, k);
    r.mt_recall_5 = (recall_at_5 > 0)
                        ? computeRecall(mt.labels, ground_truth, recall_at_5)
                        : 0.0;
    bool has_baseline = (baseline_labels && !baseline_labels->empty());
    bool match = false;
    if (has_baseline) {
      match = (mt.labels == *baseline_labels);
    }
    std::cout << std::fixed << std::setprecision(3)
              << "    [MT] threads=" << r.mt_threads
              << ", search=" << r.mt_search_time_ms << " ms/query, recall@" << k
              << "=" << r.mt_recall_k << std::endl;
    if (has_baseline && !match) {
      std::cout << "    [WARN] " << method_name
                << " multi-thread results differ from single-thread baseline"
                << std::endl;
    }
    if (!has_baseline && adopt_as_primary_if_no_baseline) {
      // 没有基线时，将多线程结果作为主结果，避免重复单线程search
      r.search_time_ms = r.mt_search_time_ms;
      r.recall_k = r.mt_recall_k;
      r.recall_1 = r.mt_recall_1;
      r.recall_5 = r.mt_recall_5;
    }
  }

  // 小工具：qtype 名称
  static const char *qtypeName(int qtype) {
    using QT = faiss::ScalarQuantizer::QuantizerType;
    switch (qtype) {
    case QT::QT_8bit:
      return "QT_8bit";
    case QT::QT_4bit:
      return "QT_4bit";
    case QT::QT_8bit_uniform:
      return "QT_8bit_uniform";
    case QT::QT_fp16:
      return "QT_fp16";
#ifdef FAISS_HAVE_QT_8BIT_DIRECT
    case QT::QT_8bit_direct:
      return "QT_8bit_direct";
#endif
    default:
      return "unknown";
    }
  }

  // 小工具：获取qtype对应的bit数
  static int getQTypeBits(int qtype) {
    using QT = faiss::ScalarQuantizer::QuantizerType;
    switch (qtype) {
    case QT::QT_8bit:
    case QT::QT_8bit_uniform:
#ifdef FAISS_HAVE_QT_8BIT_DIRECT
    case QT::QT_8bit_direct:
#endif
      return 8;
    case QT::QT_4bit:
      return 4;
    case QT::QT_fp16:
      return 16;
    default:
      return 8;
    }
  }

  // HNSW-Flat
  TestResult testHNSWFlat(int hnsw_m, int efC, int efS) {
    std::cout << "  测试 IndexHNSWFlat (M=" << hnsw_m << ", efC=" << efC
              << ", efS=" << efS << ")..." << std::endl;
    TestResult r{};
    r.method = "HNSW-Flat";
    std::string tag = r.method;
    r.hnsw_M = hnsw_m;
    r.efC = efC;
    r.efS = efS;
    try {
      log_step(tag, "start");
      faiss::IndexHNSWFlat index(dim, hnsw_m);
      index.hnsw.efConstruction = efC;
      // no train for HNSW-Flat
      r.train_time = 0.0;
      log_step(tag, std::string("add start nb=") + std::to_string(nb) +
                        ", dim=" + std::to_string(dim));
      auto t_add0 = std::chrono::high_resolution_clock::now();
      index.add(nb, database.data());
      auto t_add1 = std::chrono::high_resolution_clock::now();
      r.add_time = std::chrono::duration<double>(t_add1 - t_add0).count();
      r.build_time = r.train_time + r.add_time;
      log_step(tag, std::string("add done, time=") +
                        std::to_string(r.add_time) + " s");
      std::cout << std::fixed << std::setprecision(3)
                << "    训练(train)= " << r.train_time
                << " s, 建索引(add)= " << r.add_time
                << " s, 总构建= " << r.build_time << " s" << std::endl;

      index.hnsw.efSearch = efS;
      std::vector<float> distances;
      std::vector<faiss::idx_t> labels;
      // Always run single-thread baseline to populate serial metrics
      distances.resize((size_t)nq * k);
      labels.resize((size_t)nq * k);
      log_step(tag, std::string("search start nq=") + std::to_string(nq) +
                        ", k=" + std::to_string(k));
      auto t0 = std::chrono::high_resolution_clock::now();
      index.search(nq, queries.data(), k, distances.data(), labels.data());
      auto t1 = std::chrono::high_resolution_clock::now();
      r.search_time_ms =
          std::chrono::duration<double, std::milli>(t1 - t0).count() / nq;
      log_step(tag, std::string("search done, time=") +
                        std::to_string(r.search_time_ms) + " ms/query");
      r.recall_1 = computeRecall1NN(labels, 1);
      r.recall_5 = computeRecall1NN(labels, 5);
      r.recall_k = computeRecall1NN(labels, k);

      // Serialize index to a temporary file to measure real memory footprint
      // (including graph + codes)
      r.mbs_on_disk = measureIndexSerializedSize(&index);
      log_step(tag, std::string("serialized size=") +
                        std::to_string(r.mbs_on_disk) + " MB");
      // For flat, compression ratio = original (dim*4) /
      // (serialized_size_per_vector)
      if (nb > 0) {
        double per_vec = (r.mbs_on_disk * 1024.0 * 1024.0) / nb;
        r.compression_ratio = ((double)dim * 4.0) / per_vec;
      } else {
        r.compression_ratio = 1.0;
      }

      MultiThreadResult mt_result;
      bool mt_ok = runMultiThreadSearch(
          r.method,
          [&](std::size_t start, std::size_t count, float *dist_out,
              faiss::idx_t *label_out) {
            index.search(static_cast<faiss::idx_t>(count),
                         queries.data() + start * static_cast<std::size_t>(dim),
                         k, dist_out, label_out);
          },
          mt_result);
      if (mt_ok) {
        applyMultiThreadMetrics(r.method, r, &labels, mt_result,
                                /*adopt_as_primary_if_no_baseline=*/false);
      }
    } catch (const std::exception &e) {
      std::cerr << "    错误: " << e.what() << std::endl;
      r.build_time = -1;
    }
    return r;
  }

  // HNSW-SQ
  TestResult testHNSWSQ(int qtype, int hnsw_m, int efC, int efS) {
    std::string qtype_name = qtypeName(qtype);
    std::cout << "  测试 IndexHNSWSQ (" << qtype_name << ", M=" << hnsw_m
              << ", efC=" << efC << ", efS=" << efS << ")..." << std::endl;
    TestResult r{};
    r.method = "HNSW-SQ" + std::to_string(getQTypeBits(qtype));
    std::string tag = r.method;
    r.hnsw_M = hnsw_m;
    r.efC = efC;
    r.efS = efS;
    r.qtype = qtype;
    try {
      log_step(tag, "start");
      faiss::IndexHNSWSQ index(dim,
                               (faiss::ScalarQuantizer::QuantizerType)qtype,
                               hnsw_m, faiss::METRIC_L2);
      index.hnsw.efConstruction = efC;
      log_step(tag, std::string("train start nb=") + std::to_string(nb));
      auto t0 = std::chrono::high_resolution_clock::now();
      index.train(nb, database.data());
      auto t1 = std::chrono::high_resolution_clock::now();
      r.train_time = std::chrono::duration<double>(t1 - t0).count();
      log_step(tag, std::string("train done, time=") +
                        std::to_string(r.train_time) + " s");
      log_step(tag, std::string("add start nb=") + std::to_string(nb));
      auto t2 = std::chrono::high_resolution_clock::now();
      index.add(nb, database.data());
      auto t3 = std::chrono::high_resolution_clock::now();
      r.add_time = std::chrono::duration<double>(t3 - t2).count();
      r.build_time = r.train_time + r.add_time;
      std::cout << std::fixed << std::setprecision(3)
                << "    训练(train)= " << r.train_time
                << " s, 建索引(add)= " << r.add_time
                << " s, 总构建= " << r.build_time << " s" << std::endl;

      index.hnsw.efSearch = efS;
      std::vector<float> distances;
      std::vector<faiss::idx_t> labels;
      // Always run baseline
      distances.resize((size_t)nq * k);
      labels.resize((size_t)nq * k);
      log_step(tag, std::string("search start nq=") + std::to_string(nq) +
                        ", k=" + std::to_string(k));
      t0 = std::chrono::high_resolution_clock::now();
      index.search(nq, queries.data(), k, distances.data(), labels.data());
      t1 = std::chrono::high_resolution_clock::now();
      r.search_time_ms =
          std::chrono::duration<double, std::milli>(t1 - t0).count() / nq;
      log_step(tag, std::string("search done, time=") +
                        std::to_string(r.search_time_ms) + " ms/query");

      r.recall_1 = computeRecall1NN(labels, 1);
      r.recall_5 = computeRecall1NN(labels, 5);
      r.recall_k = computeRecall1NN(labels, k);

      int bits = 8;
      using QT = faiss::ScalarQuantizer::QuantizerType;
      switch ((QT)qtype) {
      case QT::QT_8bit:
      case QT::QT_8bit_uniform:
        bits = 8;
        break;
      case QT::QT_4bit:
        bits = 4;
        break;
      case QT::QT_fp16:
        bits = 16;
        break;
      default:
        bits = 8;
        break;
      }
      r.mbs_on_disk = measureIndexSerializedSize(&index);
      if (nb > 0) {
        double per_vec = (r.mbs_on_disk * 1024.0 * 1024.0) / nb;
        r.compression_ratio = ((double)dim * 4.0) / per_vec;
      } else {
        r.compression_ratio = 0.0;
      }

      MultiThreadResult mt_result;
      bool mt_ok = runMultiThreadSearch(
          r.method,
          [&](std::size_t start, std::size_t count, float *dist_out,
              faiss::idx_t *label_out) {
            index.search(static_cast<faiss::idx_t>(count),
                         queries.data() + start * static_cast<std::size_t>(dim),
                         k, dist_out, label_out);
          },
          mt_result);
      if (mt_ok) {
        applyMultiThreadMetrics(r.method, r, &labels, mt_result,
                                /*adopt_as_primary_if_no_baseline=*/false);
      }
    } catch (const std::exception &e) {
      std::cerr << "    错误: " << e.what() << std::endl;
      r.build_time = -1;
    }
    return r;
  }

  // HNSW-PQ
  TestResult testHNSWPQ(int pq_m, int pq_nbits, int hnsw_m, int efC, int efS,
                        double train_ratio) {
    std::cout << "  测试 IndexHNSWPQ (M=" << hnsw_m << ", PQ(m=" << pq_m
              << ", nbits=" << pq_nbits << "), efC=" << efC << ", efS=" << efS
              << ", tr=" << train_ratio << ")..." << std::endl;
    TestResult r{};
    r.method = "HNSW-PQ";
    std::string tag = r.method;
    r.hnsw_M = hnsw_m;
    r.efC = efC;
    r.efS = efS;
    r.pq_m = pq_m;
    r.pq_nbits = pq_nbits;
    r.pq_train_ratio = train_ratio;
    try {
      log_step(tag, "start");
      if (dim % pq_m != 0) {
        std::cout << "    跳过：dim=" << dim << " 不能被 m=" << pq_m << " 整除"
                  << std::endl;
        r.build_time = -1;
        return r;
      }
      faiss::IndexHNSWPQ index(dim, pq_m, hnsw_m, pq_nbits);
      index.hnsw.efConstruction = efC;
      // Decide training subset size based on ratio
      int train_n = (int)std::llround((double)nb * train_ratio);
      if (train_n < 1)
        train_n = 1;
      if (train_n > nb)
        train_n = nb;
      if (train_n < nb) {
        std::ostringstream oss;
        oss << std::fixed << std::setprecision(3)
            << (double)train_n / (double)nb;
        std::cout << "    使用训练样本: " << train_n << "/" << nb
                  << " (ratio=" << oss.str() << ")" << std::endl;
      }
      log_step(tag, std::string("train start n=") + std::to_string(train_n));
      auto t0 = std::chrono::high_resolution_clock::now();
      index.train(train_n, database.data());
      if (transpose_centroid) {
        faiss::IndexPQ *index_pq = static_cast<faiss::IndexPQ *>(index.storage);
        if (index_pq) {
          index_pq->pq.sync_transposed_centroids();
        }
      }
      auto t1 = std::chrono::high_resolution_clock::now();
      r.train_time = std::chrono::duration<double>(t1 - t0).count();
      log_step(tag, std::string("train done, time=") +
                        std::to_string(r.train_time) + " s");
      log_step(tag, std::string("add start nb=") + std::to_string(nb));
      auto t2 = std::chrono::high_resolution_clock::now();
      index.add(nb, database.data());
      auto t3 = std::chrono::high_resolution_clock::now();
      r.add_time = std::chrono::duration<double>(t3 - t2).count();
      r.build_time = r.train_time + r.add_time;
      log_step(tag, std::string("add done, time=") +
                        std::to_string(r.add_time) + " s");
      std::cout << std::fixed << std::setprecision(3)
                << "    训练(train)= " << r.train_time
                << " s, 建索引(add)= " << r.add_time
                << " s, 总构建= " << r.build_time << " s" << std::endl;

      index.hnsw.efSearch = efS;
      std::vector<float> distances;
      std::vector<faiss::idx_t> labels;
      // Always run baseline
      distances.resize((size_t)nq * k);
      labels.resize((size_t)nq * k);
      log_step(tag, std::string("search start nq=") + std::to_string(nq) +
                        ", k=" + std::to_string(k));
      t0 = std::chrono::high_resolution_clock::now();
      index.search(nq, queries.data(), k, distances.data(), labels.data());
      t1 = std::chrono::high_resolution_clock::now();
      r.search_time_ms =
          std::chrono::duration<double, std::milli>(t1 - t0).count() / nq;
      log_step(tag, std::string("search done, time=") +
                        std::to_string(r.search_time_ms) + " ms/query");

      r.recall_1 = computeRecall1NN(labels, 1);
      r.recall_5 = computeRecall1NN(labels, 5);
      r.recall_k = computeRecall1NN(labels, k);

      r.mbs_on_disk = measureIndexSerializedSize(&index);
      log_step(tag, std::string("serialized size=") +
                        std::to_string(r.mbs_on_disk) + " MB");
      if (nb > 0) {
        double per_vec = (r.mbs_on_disk * 1024.0 * 1024.0) / nb;
        r.compression_ratio = ((double)dim * 4.0) / per_vec;
      } else {
        r.compression_ratio = 0.0;
      }

      MultiThreadResult mt_result;
      bool mt_ok = runMultiThreadSearch(
          r.method,
          [&](std::size_t start, std::size_t count, float *dist_out,
              faiss::idx_t *label_out) {
            index.search(static_cast<faiss::idx_t>(count),
                         queries.data() + start * static_cast<std::size_t>(dim),
                         k, dist_out, label_out);
          },
          mt_result);
      if (mt_ok) {
        applyMultiThreadMetrics(r.method, r, &labels, mt_result,
                                /*adopt_as_primary_if_no_baseline=*/false);
      }
    } catch (const std::exception &e) {
      std::cerr << "    错误: " << e.what() << std::endl;
      r.build_time = -1;
    }
    return r;
  }

  // IVF-Flat
  TestResult testIVFFlat(int nlist, int nprobe) {
    std::cout << "  测试 IndexIVFFlat (nlist=" << nlist << ", nprobe=" << nprobe
              << ")..." << std::endl;
    TestResult r{};
    r.method = "IVF-Flat";
    std::string tag = r.method;
    r.ivf_nlist = nlist;
    r.ivf_nprobe = nprobe;
    try {
      log_step(tag, "start");
      faiss::IndexFlatL2 coarse(dim);
      faiss::IndexIVFFlat index(&coarse, dim, nlist, faiss::METRIC_L2);
      // need train
      log_step(tag, std::string("train start nb=") + std::to_string(nb));
      auto t0 = std::chrono::high_resolution_clock::now();
      index.train(nb, database.data());
      auto t1 = std::chrono::high_resolution_clock::now();
      r.train_time = std::chrono::duration<double>(t1 - t0).count();
      log_step(tag, std::string("train done, time=") +
                        std::to_string(r.train_time) + " s");
      log_step(tag, std::string("add start nb=") + std::to_string(nb));
      auto t2 = std::chrono::high_resolution_clock::now();
      index.add(nb, database.data());
      auto t3 = std::chrono::high_resolution_clock::now();
      r.add_time = std::chrono::duration<double>(t3 - t2).count();
      r.build_time = r.train_time + r.add_time;
      log_step(tag, std::string("add done, time=") +
                        std::to_string(r.add_time) + " s");
      std::cout << std::fixed << std::setprecision(3)
                << "    训练(train)= " << r.train_time
                << " s, 建索引(add)= " << r.add_time
                << " s, 总构建= " << r.build_time << " s" << std::endl;

      index.nprobe = nprobe;
      std::vector<float> distances;
      std::vector<faiss::idx_t> labels;
      // Always run baseline
      distances.resize((size_t)nq * k);
      labels.resize((size_t)nq * k);
      log_step(tag, std::string("search start nq=") + std::to_string(nq) +
                        ", k=" + std::to_string(k));
      t0 = std::chrono::high_resolution_clock::now();
      index.search(nq, queries.data(), k, distances.data(), labels.data());
      t1 = std::chrono::high_resolution_clock::now();
      r.search_time_ms =
          std::chrono::duration<double, std::milli>(t1 - t0).count() / nq;
      log_step(tag, std::string("search done, time=") +
                        std::to_string(r.search_time_ms) + " ms/query");

      r.recall_1 = computeRecall1NN(labels, 1);
      r.recall_5 = computeRecall1NN(labels, 5);
      r.recall_k = computeRecall1NN(labels, k);

      r.mbs_on_disk = measureIndexSerializedSize(&index);
      log_step(tag, std::string("serialized size=") +
                        std::to_string(r.mbs_on_disk) + " MB");
      // For IVF-Flat, vectors stored in float -> no compression
      r.compression_ratio = 1.0; // mark as 1.0; will be printed as NA below

      MultiThreadResult mt_result;
      bool mt_ok = runMultiThreadSearch(
          r.method,
          [&](std::size_t start, std::size_t count, float *dist_out,
              faiss::idx_t *label_out) {
            index.search(static_cast<faiss::idx_t>(count),
                         queries.data() + start * static_cast<std::size_t>(dim),
                         k, dist_out, label_out);
          },
          mt_result);
      if (mt_ok) {
        applyMultiThreadMetrics(r.method, r, &labels, mt_result,
                                /*adopt_as_primary_if_no_baseline=*/false);
      }
    } catch (const std::exception &e) {
      std::cerr << "    错误: " << e.what() << std::endl;
      r.build_time = -1;
    }
    return r;
  }

  // IVF-PQ
  TestResult testIVFPQ(int nlist, int nprobe, int m, int nbits,
                       double train_ratio) {
    std::cout << "  测试 IndexIVFPQ (nlist=" << nlist << ", nprobe=" << nprobe
              << ", PQ(m=" << m << ", nbits=" << nbits << ")"
              << ", tr=" << train_ratio << ")..." << std::endl;
    TestResult r{};
    r.method = "IVF-PQ";
    std::string tag = r.method;
    r.ivf_nlist = nlist;
    r.ivf_nprobe = nprobe;
    r.pq_m = m;
    r.pq_nbits = nbits;
    r.pq_train_ratio = train_ratio;
    try {
      log_step(tag, "start");
      if (dim % m != 0) {
        std::cout << "    跳过：dim=" << dim << " 不能被 m=" << m << " 整除"
                  << std::endl;
        r.build_time = -1;
        return r;
      }
      faiss::IndexFlatL2 coarse(dim);
      faiss::IndexIVFPQ index(&coarse, dim, nlist, m, nbits, faiss::METRIC_L2);
      // train subset
      int train_n = (int)std::llround((double)nb * train_ratio);
      if (train_n < 1)
        train_n = 1;
      if (train_n > nb)
        train_n = nb;
      log_step(tag, std::string("train start n=") + std::to_string(train_n));
      auto t0 = std::chrono::high_resolution_clock::now();
      index.train(train_n, database.data());
      auto t1 = std::chrono::high_resolution_clock::now();
      r.train_time = std::chrono::duration<double>(t1 - t0).count();
      log_step(tag, std::string("train done, time=") +
                        std::to_string(r.train_time) + " s");
      log_step(tag, std::string("add start nb=") + std::to_string(nb));
      auto t2 = std::chrono::high_resolution_clock::now();
      index.add(nb, database.data());
      auto t3 = std::chrono::high_resolution_clock::now();
      r.add_time = std::chrono::duration<double>(t3 - t2).count();
      r.build_time = r.train_time + r.add_time;
      log_step(tag, std::string("add done, time=") +
                        std::to_string(r.add_time) + " s");
      std::cout << std::fixed << std::setprecision(3)
                << "    训练(train)= " << r.train_time
                << " s, 建索引(add)= " << r.add_time
                << " s, 总构建= " << r.build_time << " s" << std::endl;

      index.nprobe = nprobe;
      std::vector<float> distances;
      std::vector<faiss::idx_t> labels;
      // Always run baseline
      distances.resize((size_t)nq * k);
      labels.resize((size_t)nq * k);
      log_step(tag, std::string("search start nq=") + std::to_string(nq) +
                        ", k=" + std::to_string(k));
      t0 = std::chrono::high_resolution_clock::now();
      index.search(nq, queries.data(), k, distances.data(), labels.data());
      t1 = std::chrono::high_resolution_clock::now();
      r.search_time_ms =
          std::chrono::duration<double, std::milli>(t1 - t0).count() / nq;
      log_step(tag, std::string("search done, time=") +
                        std::to_string(r.search_time_ms) + " ms/query");

      r.recall_1 = computeRecall1NN(labels, 1);
      r.recall_5 = computeRecall1NN(labels, 5);
      r.recall_k = computeRecall1NN(labels, k);

      r.mbs_on_disk = measureIndexSerializedSize(&index);
      log_step(tag, std::string("serialized size=") +
                        std::to_string(r.mbs_on_disk) + " MB");
      if (nb > 0) {
        double per_vec = (r.mbs_on_disk * 1024.0 * 1024.0) / nb;
        r.compression_ratio = ((double)dim * 4.0) / per_vec;
      } else {
        r.compression_ratio = 0.0;
      }

      MultiThreadResult mt_result;
      bool mt_ok = runMultiThreadSearch(
          r.method,
          [&](std::size_t start, std::size_t count, float *dist_out,
              faiss::idx_t *label_out) {
            index.search(static_cast<faiss::idx_t>(count),
                         queries.data() + start * static_cast<std::size_t>(dim),
                         k, dist_out, label_out);
          },
          mt_result);
      if (mt_ok) {
        applyMultiThreadMetrics(r.method, r, &labels, mt_result,
                                /*adopt_as_primary_if_no_baseline=*/false);
      }
    } catch (const std::exception &e) {
      std::cerr << "    错误: " << e.what() << std::endl;
      r.build_time = -1;
    }
    return r;
  }

  // IVF-SQ
  TestResult testIVFSQ(int nlist, int nprobe, int qtype) {
    std::string qtype_name = qtypeName(qtype);
    std::cout << "  测试 IndexIVFScalarQuantizer (" << qtype_name
              << ", nlist=" << nlist << ", nprobe=" << nprobe << ")..."
              << std::endl;
    TestResult r{};
    r.method = "IVF-SQ" + std::to_string(getQTypeBits(qtype));
    std::string tag = r.method;
    r.ivf_nlist = nlist;
    r.ivf_nprobe = nprobe;
    r.qtype = qtype;
    try {
      log_step(tag, "start");
      faiss::IndexFlatL2 coarse(dim);
      faiss::IndexIVFScalarQuantizer index(
          &coarse, dim, nlist, (faiss::ScalarQuantizer::QuantizerType)qtype,
          faiss::METRIC_L2);
      log_step(tag, std::string("train start nb=") + std::to_string(nb));
      auto t0 = std::chrono::high_resolution_clock::now();
      index.train(nb, database.data());
      auto t1 = std::chrono::high_resolution_clock::now();
      r.train_time = std::chrono::duration<double>(t1 - t0).count();
      log_step(tag, std::string("train done, time=") +
                        std::to_string(r.train_time) + " s");
      log_step(tag, std::string("add start nb=") + std::to_string(nb));
      auto t2 = std::chrono::high_resolution_clock::now();
      index.add(nb, database.data());
      auto t3 = std::chrono::high_resolution_clock::now();
      r.add_time = std::chrono::duration<double>(t3 - t2).count();
      r.build_time = r.train_time + r.add_time;
      std::cout << std::fixed << std::setprecision(3)
                << "    训练(train)= " << r.train_time
                << " s, 建索引(add)= " << r.add_time
                << " s, 总构建= " << r.build_time << " s" << std::endl;

      index.nprobe = nprobe;
      std::vector<float> distances;
      std::vector<faiss::idx_t> labels;
      // Always run baseline
      distances.resize((size_t)nq * k);
      labels.resize((size_t)nq * k);
      log_step(tag, std::string("search start nq=") + std::to_string(nq) +
                        ", k=" + std::to_string(k));
      t0 = std::chrono::high_resolution_clock::now();
      index.search(nq, queries.data(), k, distances.data(), labels.data());
      t1 = std::chrono::high_resolution_clock::now();
      r.search_time_ms =
          std::chrono::duration<double, std::milli>(t1 - t0).count() / nq;
      log_step(tag, std::string("search done, time=") +
                        std::to_string(r.search_time_ms) + " ms/query");

      r.recall_1 = computeRecall1NN(labels, 1);
      r.recall_5 = computeRecall1NN(labels, 5);
      r.recall_k = computeRecall1NN(labels, k);

      r.mbs_on_disk = measureIndexSerializedSize(&index);
      log_step(tag, std::string("serialized size=") +
                        std::to_string(r.mbs_on_disk) + " MB");
      if (nb > 0) {
        double per_vec = (r.mbs_on_disk * 1024.0 * 1024.0) / nb;
        r.compression_ratio = ((double)dim * 4.0) / per_vec;
      } else {
        r.compression_ratio = 0.0;
      }

      MultiThreadResult mt_result;
      bool mt_ok = runMultiThreadSearch(
          r.method,
          [&](std::size_t start, std::size_t count, float *dist_out,
              faiss::idx_t *label_out) {
            index.search(static_cast<faiss::idx_t>(count),
                         queries.data() + start * static_cast<std::size_t>(dim),
                         k, dist_out, label_out);
          },
          mt_result);
      if (mt_ok) {
        applyMultiThreadMetrics(r.method, r, &labels, mt_result,
                                /*adopt_as_primary_if_no_baseline=*/false);
      }
    } catch (const std::exception &e) {
      std::cerr << "    错误: " << e.what() << std::endl;
      r.build_time = -1;
    }
    return r;
  }

  // IVF-RaBitQ
  TestResult testIVFRaBitQ(int nlist, int nprobe, int qb, bool centered) {
    std::cout << "  测试 IndexIVFRaBitQ (nlist=" << nlist
              << ", nprobe=" << nprobe << ", qb=" << qb
              << ", centered=" << (centered ? "true" : "false") << ")..."
              << std::endl;
    TestResult r{};
    r.method = "IVF-RaBitQ";
    std::string tag = r.method;
    r.ivf_nlist = nlist;
    r.ivf_nprobe = nprobe;
    r.rabitq_qb = qb;
    r.rabitq_centered = centered ? 1 : 0;
    try {
      log_step(tag, "start");
      std::unique_ptr<faiss::IndexFlat> coarse =
          std::make_unique<faiss::IndexFlat>(dim, faiss::METRIC_L2);
      std::unique_ptr<faiss::IndexIVFRaBitQ> index =
          std::make_unique<faiss::IndexIVFRaBitQ>(coarse.release(), dim, nlist,
                                                  faiss::METRIC_L2);
      index->own_fields = true;
      index->qb = (uint8_t)qb; // default query bits

      // Try both with and without rotation for better recall
      auto rr = std::make_unique<faiss::RandomRotationMatrix>(dim, dim);
      // Align with bench_rabitq.py: explicit init of random rotation
      rr->init(123);
      auto idx_rr = std::make_unique<faiss::IndexPreTransform>(rr.release(),
                                                               index.release());
      idx_rr->own_fields = true;

      log_step(tag, std::string("train start nb=") + std::to_string(nb));
      auto t0 = std::chrono::high_resolution_clock::now();
      // Use more training data if available for better quantization
      int train_size = std::min(nb, std::max(50000, nb / 2));
      idx_rr->train(train_size, database.data());
      auto t1 = std::chrono::high_resolution_clock::now();
      r.train_time = std::chrono::duration<double>(t1 - t0).count();
      log_step(tag, std::string("train done, time=") +
                        std::to_string(r.train_time) +
                        " s (n=" + std::to_string(train_size) + ")");
      log_step(tag, std::string("add start nb=") + std::to_string(nb));
      auto t2 = std::chrono::high_resolution_clock::now();
      idx_rr->add(nb, database.data());
      auto t3 = std::chrono::high_resolution_clock::now();
      r.add_time = std::chrono::duration<double>(t3 - t2).count();
      r.build_time = r.train_time + r.add_time;
      log_step(tag, std::string("add done, time=") +
                        std::to_string(r.add_time) + " s");
      std::cout << std::fixed << std::setprecision(3)
                << "    训练(train)= " << r.train_time
                << " s, 建索引(add)= " << r.add_time
                << " s, 总构建= " << r.build_time
                << " s, 训练样本=" << train_size << std::endl;

  std::vector<float> distances;
  std::vector<faiss::idx_t> labels;
  faiss::IVFRaBitQSearchParameters sp;
      sp.qb = (uint8_t)qb;
      // Important: when passing SearchParameters, nprobe from params is used.
      // Default is 1, so make sure to pass the desired nprobe here.
      sp.nprobe = nprobe;
      bool skip_baseline = (mt_threads > 1);
      if (!skip_baseline) {
        distances.resize((size_t)nq * k);
        labels.resize((size_t)nq * k);
        log_step(tag, std::string("search start nq=") + std::to_string(nq) +
                          ", k=" + std::to_string(k) +
                          ", nprobe=" + std::to_string(sp.nprobe));
        t0 = std::chrono::high_resolution_clock::now();
        idx_rr->search(nq, queries.data(), k, distances.data(), labels.data(),
                       &sp);
        t1 = std::chrono::high_resolution_clock::now();
        r.search_time_ms =
            std::chrono::duration<double, std::milli>(t1 - t0).count() / nq;
        log_step(tag, std::string("search done, time=") +
                          std::to_string(r.search_time_ms) + " ms/query");
      }

      std::cout << "    调试: nprobe=" << sp.nprobe << ", qb=" << (int)sp.qb
                << std::endl;

      if (!labels.empty()) {
        r.recall_1 = computeRecall1NN(labels, 1);
        r.recall_5 = computeRecall1NN(labels, 5);
        r.recall_k = computeRecall1NN(labels, k);
      }

      r.mbs_on_disk = measureIndexSerializedSize(idx_rr.get());
      log_step(tag, std::string("serialized size=") +
                        std::to_string(r.mbs_on_disk) + " MB");
      if (nb > 0) {
        double per_vec = (r.mbs_on_disk * 1024.0 * 1024.0) / nb;
        r.compression_ratio = ((double)dim * 4.0) / per_vec;
      } else {
        r.compression_ratio = 0.0;
      }

      faiss::IndexPreTransform *index_ptr = idx_rr.get();
      faiss::IVFRaBitQSearchParameters sp_proto = sp;
      MultiThreadResult mt_result;
      bool mt_ok = runMultiThreadSearch(
          r.method,
          [&, index_ptr, sp_proto](std::size_t start, std::size_t count,
                                   float *dist_out, faiss::idx_t *label_out) {
            faiss::IVFRaBitQSearchParameters params = sp_proto;
            index_ptr->search(static_cast<faiss::idx_t>(count),
                              queries.data() +
                                  start * static_cast<std::size_t>(dim),
                              k, dist_out, label_out, &params);
          },
          mt_result);
      if (mt_ok) {
        applyMultiThreadMetrics(r.method, r, &labels, mt_result,
                                /*adopt_as_primary_if_no_baseline=*/false);
      }
    } catch (const std::exception &e) {
      std::cerr << "    错误: " << e.what() << std::endl;
      r.build_time = -1;
    }
    return r;
  }

  // IVF-RaBitQ + Refine (two-stage)
  TestResult testIVFRaBitQRefine(int nlist, int nprobe, int qb, bool centered,
                                 const std::string &refine_type, int refine_k) {
    std::cout << "  测试 IVFRaBitQ+Refine (nlist=" << nlist
              << ", nprobe=" << nprobe << ", qb=" << qb
              << ", centered=" << (centered ? "true" : "false")
              << ", refine_type=" << refine_type << ", refine_k=" << refine_k
              << ")..." << std::endl;
    TestResult r{};
    r.method = "IVF-RaBitQ-Refine";
    std::string tag = r.method;
    r.ivf_nlist = nlist;
    r.ivf_nprobe = nprobe;
    r.rabitq_qb = qb;
    r.rabitq_centered = centered ? 1 : 0;
    r.refine_type = refine_type;
    r.refine_k = refine_k;
    try {
      log_step(tag, "start");
      // Base: RR -> IVFRaBitQ
      std::unique_ptr<faiss::IndexFlatL2> coarse =
          std::make_unique<faiss::IndexFlatL2>(dim);
      std::unique_ptr<faiss::IndexIVFRaBitQ> base_ivf =
          std::make_unique<faiss::IndexIVFRaBitQ>(coarse.release(), dim, nlist,
                                                  faiss::METRIC_L2);
      base_ivf->nprobe = nprobe;
      base_ivf->own_fields = true;
      base_ivf->qb = (uint8_t)qb; // default query bits

      auto rr = std::make_unique<faiss::RandomRotationMatrix>(dim, dim);
      rr->init(123);
      std::unique_ptr<faiss::IndexPreTransform> base =
          std::make_unique<faiss::IndexPreTransform>(rr.release(),
                                                     base_ivf.release());
      base->own_fields = true;

      // Refine index by type (operates on original vectors)
      std::unique_ptr<faiss::Index> refine;
      auto to_lower = [](std::string s) {
        std::transform(s.begin(), s.end(), s.begin(),
                       [](unsigned char c) { return std::tolower(c); });
        return s;
      };
      std::string rt = to_lower(refine_type);
      if (rt == "flat") {
        refine = std::make_unique<faiss::IndexFlatL2>(dim);
      } else if (rt == "sq8") {
        refine = std::make_unique<faiss::IndexScalarQuantizer>(
            dim, faiss::ScalarQuantizer::QuantizerType::QT_8bit,
            faiss::METRIC_L2);
      } else if (rt == "sq4") {
        refine = std::make_unique<faiss::IndexScalarQuantizer>(
            dim, faiss::ScalarQuantizer::QuantizerType::QT_4bit,
            faiss::METRIC_L2);
      } else if (rt == "fp16" || rt == "bf16") {
        // Use fp16 SQ as a proxy; if bf16 unsupported in this FAISS build, fall
        // back to fp16
        refine = std::make_unique<faiss::IndexScalarQuantizer>(
            dim, faiss::ScalarQuantizer::QuantizerType::QT_fp16,
            faiss::METRIC_L2);
      } else {
        std::cout << "    未知 refine_type='" << refine_type << "'，回退到 flat"
                  << std::endl;
        refine = std::make_unique<faiss::IndexFlatL2>(dim);
      }

      // Wrap with IndexRefine
      std::unique_ptr<faiss::IndexRefine> wrapper =
          std::make_unique<faiss::IndexRefine>(base.release(),
                                               refine.release());
      wrapper->own_fields = true;

      // Train both indices as needed
      log_step(tag, std::string("train+add start nb=") + std::to_string(nb));
      auto t0 = std::chrono::high_resolution_clock::now();
      wrapper->train(nb, database.data());
      auto t1 = std::chrono::high_resolution_clock::now();
      r.train_time = std::chrono::duration<double>(t1 - t0).count();
      log_step(tag, std::string("train done, time=") +
                        std::to_string(r.train_time) + " s");
      log_step(tag, std::string("add start nb=") + std::to_string(nb));
      auto t2 = std::chrono::high_resolution_clock::now();
      wrapper->add(nb, database.data());
      auto t3 = std::chrono::high_resolution_clock::now();
      r.add_time = std::chrono::duration<double>(t3 - t2).count();
      r.build_time = r.train_time + r.add_time;
      std::cout << std::fixed << std::setprecision(3)
                << "    训练(train)= " << r.train_time
                << " s, 建索引(add)= " << r.add_time
                << " s, 总构建= " << r.build_time << " s" << std::endl;

      // Search with two-stage params
      std::vector<float> distances;
      std::vector<faiss::idx_t> labels;
      faiss::IVFRaBitQSearchParameters ivf_sp;
      ivf_sp.qb = (uint8_t)qb;
      ivf_sp.nprobe = nprobe;
      // nprobe is already set on index; still pass via base params
      faiss::IndexRefineSearchParameters ref_sp;
      ref_sp.k_factor = refine_k;
      ref_sp.base_index_params = &ivf_sp;
      // Always run baseline
      distances.resize((size_t)nq * k);
      labels.resize((size_t)nq * k);
      log_step(tag, std::string("search start nq=") + std::to_string(nq) +
                        ", k=" + std::to_string(k) +
                        ", refine_k=" + std::to_string(refine_k));
      t0 = std::chrono::high_resolution_clock::now();
      wrapper->search(nq, queries.data(), k, distances.data(), labels.data(),
                      &ref_sp);
      t1 = std::chrono::high_resolution_clock::now();
      r.search_time_ms =
          std::chrono::duration<double, std::milli>(t1 - t0).count() / nq;
      log_step(tag, std::string("search done, time=") +
                        std::to_string(r.search_time_ms) + " ms/query");

      r.recall_1 = computeRecall(labels, ground_truth, 1);
      r.recall_5 = computeRecall(labels, ground_truth, 5);
      r.recall_k = computeRecall(labels, ground_truth, k);

      r.mbs_on_disk = measureIndexSerializedSize(wrapper.get());
      log_step(tag, std::string("serialized size=") +
                        std::to_string(r.mbs_on_disk) + " MB");
      if (nb > 0) {
        double per_vec = (r.mbs_on_disk * 1024.0 * 1024.0) / nb;
        r.compression_ratio = ((double)dim * 4.0) / per_vec;
      } else {
        r.compression_ratio = 0.0;
      }

      faiss::IndexRefine *wrapper_ptr = wrapper.get();
      faiss::IVFRaBitQSearchParameters ivf_sp_proto = ivf_sp;
      faiss::IndexRefineSearchParameters ref_sp_proto = ref_sp;
      MultiThreadResult mt_result;
      bool mt_ok = runMultiThreadSearch(
          r.method,
          [&, wrapper_ptr, ivf_sp_proto,
           ref_sp_proto](std::size_t start, std::size_t count, float *dist_out,
                         faiss::idx_t *label_out) {
            faiss::IVFRaBitQSearchParameters ivf_params = ivf_sp_proto;
            faiss::IndexRefineSearchParameters refine_params = ref_sp_proto;
            refine_params.base_index_params = &ivf_params;
            wrapper_ptr->search(static_cast<faiss::idx_t>(count),
                                queries.data() +
                                    start * static_cast<std::size_t>(dim),
                                k, dist_out, label_out, &refine_params);
          },
          mt_result);
      if (mt_ok) {
        applyMultiThreadMetrics(r.method, r, &labels, mt_result,
                                /*adopt_as_primary_if_no_baseline=*/false);
      }
    } catch (const std::exception &e) {
      std::cerr << "    错误: " << e.what() << std::endl;
      r.build_time = -1;
    }
    return r;
  }

  // RaBitQ (flat)
  TestResult testRaBitQ(int qb, bool centered) {
    std::cout << "  测试 IndexRaBitQ (qb=" << qb
              << ", centered=" << (centered ? "true" : "false") << ")..."
              << std::endl;
    TestResult r{};
    r.method = "RaBitQ";
    std::string tag = r.method;
    r.rabitq_qb = qb;
    r.rabitq_centered = centered ? 1 : 0;
    try {
      log_step(tag, "start");
      faiss::IndexRaBitQ index(dim, faiss::METRIC_L2);
      // train
      log_step(tag, std::string("train start nb=") + std::to_string(nb));
      auto t0 = std::chrono::high_resolution_clock::now();
      index.train(nb, database.data());
      auto t1 = std::chrono::high_resolution_clock::now();
      r.train_time = std::chrono::duration<double>(t1 - t0).count();
      log_step(tag, std::string("train done, time=") +
                        std::to_string(r.train_time) + " s");
      // add
      log_step(tag, std::string("add start nb=") + std::to_string(nb));
      auto t2 = std::chrono::high_resolution_clock::now();
      index.add(nb, database.data());
      auto t3 = std::chrono::high_resolution_clock::now();
      r.add_time = std::chrono::duration<double>(t3 - t2).count();
      r.build_time = r.train_time + r.add_time;
      log_step(tag, std::string("add done, time=") +
                        std::to_string(r.add_time) + " s");

      std::vector<float> distances;
      std::vector<faiss::idx_t> labels;
      faiss::RaBitQSearchParameters sp;
      sp.qb = (uint8_t)qb;
      // Always run baseline
      distances.resize((size_t)nq * k);
      labels.resize((size_t)nq * k);
      log_step(tag, std::string("search start nq=") + std::to_string(nq) +
                        ", k=" + std::to_string(k));
      t0 = std::chrono::high_resolution_clock::now();
      index.search(nq, queries.data(), k, distances.data(), labels.data(), &sp);
      t1 = std::chrono::high_resolution_clock::now();
      r.search_time_ms =
          std::chrono::duration<double, std::milli>(t1 - t0).count() / nq;
      log_step(tag, std::string("search done, time=") +
                        std::to_string(r.search_time_ms) + " ms/query");

      r.recall_1 = computeRecall(labels, ground_truth, 1);
      r.recall_5 = computeRecall(labels, ground_truth, 5);
      r.recall_k = computeRecall(labels, ground_truth, k);

      r.mbs_on_disk = measureIndexSerializedSize(&index);
      log_step(tag, std::string("serialized size=") +
                        std::to_string(r.mbs_on_disk) + " MB");
      if (nb > 0) {
        double per_vec = (r.mbs_on_disk * 1024.0 * 1024.0) / nb;
        r.compression_ratio = ((double)dim * 4.0) / per_vec;
      } else {
        r.compression_ratio = 0.0;
      }
      std::cout << std::fixed << std::setprecision(3)
                << "    训练(train)= " << r.train_time
                << " s, 建索引(add)= " << r.add_time
                << " s, 总构建= " << r.build_time << " s" << std::endl;

      faiss::RaBitQSearchParameters sp_proto = sp;
      MultiThreadResult mt_result;
      bool mt_ok = runMultiThreadSearch(
          r.method,
          [&, sp_proto](std::size_t start, std::size_t count, float *dist_out,
                        faiss::idx_t *label_out) {
            faiss::RaBitQSearchParameters params = sp_proto;
            index.search(static_cast<faiss::idx_t>(count),
                         queries.data() + start * static_cast<std::size_t>(dim),
                         k, dist_out, label_out, &params);
          },
          mt_result);
      if (mt_ok) {
        applyMultiThreadMetrics(r.method, r, &labels, mt_result,
                                /*adopt_as_primary_if_no_baseline=*/false);
      }
    } catch (const std::exception &e) {
      std::cerr << "    错误: " << e.what() << std::endl;
      r.build_time = -1;
    }
    return r;
  }

#ifdef HAVE_VECML
  // VecML test using the C shim (vecml_shim)
  TestResult testVecML(const std::string &base_path,
                       const std::string &license_path, int mt_threads_option,
                       int vec_threads_option) {
    TestResult r{};
    r.method = "VecML";
    r.dim = dim;
    r.nb = nb;
    r.nq = nq;
    r.k = k;
    // create ctx
    log_step("VecML", std::string("create context, base=") + base_path +
                          ", license=" + license_path + ", fast_index=false");
    vecml_ctx_t ctx = vecml_create(base_path.c_str(), license_path.c_str(),
                                   /*fast_index=*/false);
    if (!ctx) {
      std::cerr << "VecML: failed to create context" << std::endl;
      r.build_time = -1;
      return r;
    }
    // Configure threads for index attach and add operations
    vecml_set_threads(ctx, vec_threads_option);
    log_step("VecML",
             std::string("set_threads=") + std::to_string(vec_threads_option));
    // VecML does not have a separate train phase. Measure add_time and set
    // build_time = add_time to reflect that "build" is just adding data.
    try {
      log_step("VecML", std::string("add_data start nb=") + std::to_string(nb) +
                            ", dim=" + std::to_string(dim));
      auto t_add0 = std::chrono::high_resolution_clock::now();
      int add_ret = vecml_add_data(ctx, database.data(), nb, dim, nullptr);
      auto t_add1 = std::chrono::high_resolution_clock::now();
      if (add_ret != 0) {
        std::cerr << "VecML: add_data failed: " << add_ret << std::endl;
        vecml_destroy(ctx);
        r.build_time = -1;
        return r;
      }
      r.add_time = std::chrono::duration<double>(t_add1 - t_add0).count();
      log_step("VecML", std::string("add_data done, time=") +
                            std::to_string(r.add_time) + " s");
      r.train_time = 0.0; // no train step in VecML
      r.build_time = r.add_time;

      int threads = mt_threads_option;
      std::vector<faiss::idx_t> labels; // baseline labels
      // Always run baseline single-thread search to populate serial metrics
      log_step("VecML", std::string("search start nq=") + std::to_string(nq) +
                            ", k=" + std::to_string(k));
      std::vector<long> out_ids((size_t)nq * k, -1);
      auto t_s0 = std::chrono::high_resolution_clock::now();
      int sret = vecml_search(ctx, queries.data(), nq, dim, k, out_ids.data());
      auto t_s1 = std::chrono::high_resolution_clock::now();
      if (sret != 0) {
        std::cerr << "VecML: search failed: " << sret << std::endl;
        vecml_destroy(ctx);
        r.build_time = -1;
        return r;
      }
      double search_sec = std::chrono::duration<double>(t_s1 - t_s0).count();
      r.search_time_ms = nq > 0 ? (search_sec / (double)nq) * 1000.0 : 0.0;
      log_step("VecML", std::string("search done, time=") +
                            std::to_string(r.search_time_ms) + " ms/query");

      labels.assign((size_t)nq * k, -1);
      for (int i = 0; i < nq * k; ++i) {
        labels[i] =
            out_ids[i] >= 0 ? static_cast<faiss::idx_t>(out_ids[i]) : -1;
      }
      r.recall_1 = computeRecall(labels, ground_truth, 1);
      r.recall_5 = computeRecall(labels, ground_truth, 5);
      r.recall_k = computeRecall(labels, ground_truth, k);

      // Only run multi-thread smoke test if the user explicitly provided
      // --mt-threads (mt_threads_option > 0). Do not auto-detect.
      if (threads <= 1) {
        std::cout << "\n[VecML-MT] Skip multi-thread test: --mt-threads not "
                     "provided or <=1"
                  << std::endl;
      } else if (nq <= 0 || k <= 0) {
        std::cout << "\n[VecML-MT] Skip multi-thread test: invalid dataset "
                     "configuration"
                  << std::endl;
      } else {
        std::cout << "\n=== VecML Multi-thread Smoke Test (threads=" << threads
                  << ") ===" << std::endl;
        std::vector<long> mt_out((size_t)nq * k, -1);
        std::atomic<int> mt_err{0};
        auto run_chunk = [&](std::size_t start, std::size_t count) {
          if (count == 0 || mt_err.load(std::memory_order_relaxed) != 0) {
            return;
          }
          int ret = vecml_search(ctx, queries.data() + start * (std::size_t)dim,
                                 static_cast<int>(count), dim, k,
                                 mt_out.data() + start * (std::size_t)k);
          if (ret != 0) {
            mt_err.store(ret, std::memory_order_relaxed);
          }
        };

        std::vector<std::thread> workers;
        workers.reserve((size_t)threads);
        std::size_t total_queries = (std::size_t)nq;
        std::size_t base_chunk = total_queries / (std::size_t)threads;
        std::size_t remainder = total_queries % (std::size_t)threads;
        std::size_t cursor = 0;
        auto mt_t0 = std::chrono::high_resolution_clock::now();
        for (int t = 0; t < threads; ++t) {
          std::size_t count = base_chunk + ((std::size_t)t < remainder ? 1 : 0);
          if (count == 0) {
            continue;
          }
          std::size_t start = cursor;
          workers.emplace_back(
              [&, start, count]() { run_chunk(start, count); });
          cursor += count;
        }
        for (auto &worker : workers) {
          worker.join();
        }
        auto mt_t1 = std::chrono::high_resolution_clock::now();

        int mt_code = mt_err.load(std::memory_order_relaxed);
        if (mt_code != 0) {
          std::cout << "[VecML-MT] vecml_search returned error code " << mt_code
                    << "; skipping multi-thread metrics" << std::endl;
        } else {
          double mt_total_ms =
              std::chrono::duration<double, std::milli>(mt_t1 - mt_t0).count();
          double mt_ms_per_query = nq > 0 ? mt_total_ms / (double)nq : 0.0;

          std::vector<faiss::idx_t> mt_labels((size_t)nq * k);
          for (int i = 0; i < nq * k; ++i) {
            mt_labels[i] =
                mt_out[i] >= 0 ? static_cast<faiss::idx_t>(mt_out[i]) : -1;
          }
          double mt_recall_1 = computeRecall1NN(mt_labels, 1);
          double mt_recall_5 = computeRecall1NN(mt_labels, std::min(5, k));
          double mt_recall_k = computeRecall1NN(mt_labels, k);

          r.has_mt = true;
          r.mt_threads = threads;
          r.mt_search_time_ms = mt_ms_per_query;
          r.mt_recall_k = mt_recall_k;
          r.mt_recall_1 = mt_recall_1;
          r.mt_recall_5 = mt_recall_5;
          // Print MT summary line for reference (serial metrics remain in r.*)
          std::cout << std::fixed << std::setprecision(3)
                    << "Multi-thread: " << mt_ms_per_query
                    << " ms/query, recall@" << k << "=" << mt_recall_k
                    << std::endl;
        }
      }

      log_step("VecML", "destroy context");
      vecml_destroy(ctx);

      double final_disk_mb = computeDirectorySizeMB(base_path);
      if (final_disk_mb >= 0.0) {
        r.mbs_on_disk = final_disk_mb;
        double raw_mb =
            (double)nb * (double)dim * sizeof(float) / (1024.0 * 1024.0);
        if (final_disk_mb > 0.0) {
          r.compression_ratio = raw_mb / final_disk_mb;
        }
        log_step("VecML", std::string("persisted disk usage=") +
                              std::to_string(final_disk_mb) + " MB");
      }

      return r;
    } catch (const std::exception &e) {
      std::cerr << "VecML: exception during add/search: " << e.what()
                << std::endl;
      vecml_destroy(ctx);
      r.build_time = -1;
      return r;
    }
  }
#endif

#ifdef HAVE_VECML
  // VecML Fast Index test (attach_soil_index) using the C shim
  TestResult testVecMLFastIdx(const std::string &base_path,
                              const std::string &license_path,
                              int mt_threads_option, int vec_threads_option) {
    TestResult r{};
    r.method = "VecML-Fast-Idx";
    r.dim = dim;
    r.nb = nb;
    r.nq = nq;
    r.k = k;
    log_step("VecML-Fast-Idx", std::string("create context, base=") +
                                   base_path + ", license=" + license_path +
                                   ", fast_index=true");
    vecml_ctx_t ctx = vecml_create(base_path.c_str(), license_path.c_str(),
                                   /*fast_index=*/true);
    if (!ctx) {
      std::cerr << "VecML-Fast-Idx: failed to create context" << std::endl;
      r.build_time = -1;
      return r;
    }
    // Configure threads and enable fast index before adding data
    vecml_set_threads(ctx, vec_threads_option);
    log_step("VecML-Fast-Idx",
             std::string("set_threads=") + std::to_string(vec_threads_option));
    if (vecml_enable_fast_index(
            ctx, /*shrink_rate=*/0.4f,
            /*max_num_samples=*/std::max(nb, 100000),
            (vec_threads_option > 0 ? vec_threads_option : 8)) != 0) {
      std::cerr << "VecML-Fast-Idx: enable_fast_index failed" << std::endl;
      vecml_destroy(ctx);
      r.build_time = -1;
      return r;
    }
    log_step(
        "VecML-Fast-Idx",
        std::string("enable_fast_index shrink=0.4 max_samples=") +
            std::to_string(std::max(nb, 100000)) + ", threads=" +
            std::to_string(vec_threads_option > 0 ? vec_threads_option : 8));

    try {
      log_step("VecML-Fast-Idx", std::string("add_data start nb=") +
                                     std::to_string(nb) +
                                     ", dim=" + std::to_string(dim));
      auto t_add0 = std::chrono::high_resolution_clock::now();
      int add_ret = vecml_add_data(ctx, database.data(), nb, dim, nullptr);
      auto t_add1 = std::chrono::high_resolution_clock::now();
      if (add_ret != 0) {
        std::cerr << "VecML-Fast-Idx: add_data failed: " << add_ret
                  << std::endl;
        vecml_destroy(ctx);
        r.build_time = -1;
        return r;
      }
      r.add_time = std::chrono::duration<double>(t_add1 - t_add0).count();
      log_step("VecML-Fast-Idx", std::string("add_data done, time=") +
                                     std::to_string(r.add_time) + " s");
      r.train_time = 0.0;
      r.build_time = r.add_time;

      // Always run single-thread baseline first
      int threads = mt_threads_option;
      std::vector<faiss::idx_t> labels; // baseline labels
      std::vector<long> out_ids((size_t)nq * k, -1);
      log_step("VecML-Fast-Idx", std::string("search start nq=") +
                                     std::to_string(nq) +
                                     ", k=" + std::to_string(k));
      auto t_s0 = std::chrono::high_resolution_clock::now();
      int sret = vecml_search(ctx, queries.data(), nq, dim, k, out_ids.data());
      auto t_s1 = std::chrono::high_resolution_clock::now();
      if (sret != 0) {
        std::cerr << "VecML-Fast-Idx: search failed: " << sret << std::endl;
        vecml_destroy(ctx);
        r.build_time = -1;
        return r;
      }
      double search_sec = std::chrono::duration<double>(t_s1 - t_s0).count();
      r.search_time_ms = nq > 0 ? (search_sec / (double)nq) * 1000.0 : 0.0;
      log_step("VecML-Fast-Idx", std::string("search done, time=") +
                                     std::to_string(r.search_time_ms) +
                                     " ms/query");

      labels.assign((size_t)nq * k, -1);
      for (int i = 0; i < nq * k; ++i) {
        labels[i] = out_ids[i] >= 0 ? static_cast<faiss::idx_t>(out_ids[i]) : -1;
      }
      r.recall_1 = computeRecall1NN(labels, 1);
      r.recall_5 = computeRecall1NN(labels, 5);
      r.recall_k = computeRecall1NN(labels, k);

      // Optional: MT smoke test mirrors testVecML
      if (threads > 1 && nq > 0 && k > 0) {
        std::cout << "\n=== VecML Fast-Idx Multi-thread Smoke Test (threads="
                  << threads << ") ===" << std::endl;
        std::vector<long> mt_out((size_t)nq * k, -1);
        std::atomic<int> mt_err{0};
        auto run_chunk = [&](std::size_t start, std::size_t count) {
          if (count == 0 || mt_err.load(std::memory_order_relaxed) != 0)
            return;
          int ret = vecml_search(ctx, queries.data() + start * (std::size_t)dim,
                                 static_cast<int>(count), dim, k,
                                 mt_out.data() + start * (std::size_t)k);
          if (ret != 0)
            mt_err.store(ret, std::memory_order_relaxed);
        };
        std::vector<std::thread> workers;
        workers.reserve((size_t)threads);
        std::size_t total_queries = (std::size_t)nq;
        std::size_t base_chunk = total_queries / (std::size_t)threads;
        std::size_t remainder = total_queries % (std::size_t)threads;
        std::size_t cursor = 0;
        auto mt_t0 = std::chrono::high_resolution_clock::now();
        for (int t = 0; t < threads; ++t) {
          std::size_t count = base_chunk + ((std::size_t)t < remainder ? 1 : 0);
          if (count == 0)
            continue;
          std::size_t start = cursor;
          workers.emplace_back(
              [&, start, count]() { run_chunk(start, count); });
          cursor += count;
        }
        for (auto &w : workers)
          w.join();
        auto mt_t1 = std::chrono::high_resolution_clock::now();
        int mt_code = mt_err.load(std::memory_order_relaxed);
        if (mt_code == 0) {
          double mt_total_ms =
              std::chrono::duration<double, std::milli>(mt_t1 - mt_t0).count();
          double mt_ms_per_query = nq > 0 ? mt_total_ms / (double)nq : 0.0;
          std::vector<faiss::idx_t> mt_labels((size_t)nq * k);
          for (int i = 0; i < nq * k; ++i) {
            mt_labels[i] = mt_out[i] >= 0 ? (faiss::idx_t)mt_out[i] : -1;
          }
          r.has_mt = true;
          r.mt_threads = threads;
          r.mt_search_time_ms = mt_ms_per_query;
          r.mt_recall_1 = computeRecall(mt_labels, ground_truth, 1);
          r.mt_recall_5 =
              computeRecall(mt_labels, ground_truth, std::min(5, k));
          r.mt_recall_k = computeRecall(mt_labels, ground_truth, k);
        }
      } else if (threads <= 1) {
        std::cout << "\n[VecML-Fast-Idx-MT] Skip multi-thread test: "
                     "--mt-threads not provided or <=1"
                  << std::endl;
      }

      log_step("VecML-Fast-Idx", "destroy context");
      vecml_destroy(ctx);
      double final_disk_mb = computeDirectorySizeMB(base_path);
      if (final_disk_mb >= 0.0) {
        r.mbs_on_disk = final_disk_mb;
        double raw_mb =
            (double)nb * (double)dim * sizeof(float) / (1024.0 * 1024.0);
        if (final_disk_mb > 0.0) {
          r.compression_ratio = raw_mb / final_disk_mb;
        }
        log_step("VecML-Fast-Idx", std::string("persisted disk usage=") +
                                       std::to_string(final_disk_mb) + " MB");
      }
      return r;
    } catch (const std::exception &e) {
      std::cerr << "VecML-Fast-Idx: exception during add/search: " << e.what()
                << std::endl;
      vecml_destroy(ctx);
      r.build_time = -1;
      return r;
    }
  }
#endif

  std::vector<TestResult> runIndexTypeBenchmarks(const Options &opt) {
    std::vector<TestResult> results;
    auto contains = [&](const std::string &what) {
      if (opt.which.size() == 1 && opt.which[0] == "all")
        return true;
      return std::find(opt.which.begin(), opt.which.end(), what) !=
             opt.which.end();
    };

    // Helper to check for SQ variants
    auto containsSQ = [&](const std::string &base, int bits) {
      std::string target = base + std::to_string(bits);
      return contains(target);
    };

    // Parse SQ types from which parameter
    auto getSQTypes = [&](const std::string &base) {
      std::vector<int> types;
      if (contains("all") || containsSQ(base, 4)) {
        types.push_back((int)faiss::ScalarQuantizer::QuantizerType::QT_4bit);
      }
      if (contains("all") || containsSQ(base, 8)) {
        types.push_back((int)faiss::ScalarQuantizer::QuantizerType::QT_8bit);
      }
      return types;
    };

    // Prepare lists (fallback to single value if list empty)
    auto prepareIntList = [](const std::vector<int> &lst, int single) {
      return lst.empty() ? std::vector<int>{single} : lst;
    };
    auto prepareDoubleList = [](const std::vector<double> &lst, double single) {
      return lst.empty() ? std::vector<double>{single} : lst;
    };

    auto dim_list = prepareIntList(opt.dim_list, opt.dim);
    auto nb_list = prepareIntList(opt.nb_list, opt.nb);
    auto nq_list = prepareIntList(opt.nq_list, opt.nq);
    auto k_list = prepareIntList(opt.k_list, opt.k);
    auto hnsw_M_list = prepareIntList(opt.hnsw_M_list, opt.hnsw_M);
    auto efC_list = prepareIntList(opt.efC_list, opt.efC);
    auto efS_list = prepareIntList(opt.efS_list, opt.efS);
    auto pq_m_list = prepareIntList(opt.pq_m_list, opt.pq_m);
    auto pq_nbits_list = prepareIntList(opt.pq_nbits_list, opt.pq_nbits);
    auto pq_train_ratio_list =
        prepareDoubleList(opt.pq_train_ratio_list, opt.pq_train_ratio);
    // auto sq_qtype_list = prepareIntList(opt.sq_qtype_list, opt.sq_qtype); //
    // removed
    auto ivf_nlist_list = prepareIntList(opt.ivf_nlist_list, opt.ivf_nlist);
    auto ivf_nprobe_list = prepareIntList(opt.ivf_nprobe_list, opt.ivf_nprobe);
    auto rabitq_qb_list = prepareIntList(opt.rabitq_qb_list, opt.rabitq_qb);
    auto rabitq_centered_list =
        prepareIntList(opt.rabitq_centered_list, opt.rabitq_centered ? 1 : 0);
    auto rbq_refine_type_list =
        (opt.rbq_refine_type_list.empty()
             ? std::vector<std::string>{opt.rbq_refine_type}
             : opt.rbq_refine_type_list);
    auto rbq_refine_k_list =
        prepareIntList(opt.rbq_refine_k_list, opt.rbq_refine_k);

    bool use_sift1m = opt.use_sift1m && !opt.sift1m_dir.empty();
    if (use_sift1m) {
      // dim is determined by dataset; avoid redundant dim sweeps
      dim_list = {opt.dim};
      // Ignore nb/nq/k CLI under SIFT1M; dataset decides sizes.
      nb_list = {opt.nb};
      nq_list = {opt.nq};
      k_list = {opt.k};
    }

    // Iterate over dataset-level combinations first: dim, nb, nq, k
    for (int dim_v : dim_list) {
      for (int nb_v : nb_list) {
        for (int nq_v : nq_list) {
          for (int k_v : k_list) {
            // Rebuild benchmark data for each dataset combo
            PQBenchmark bench_local(dim_v, nb_v, nq_v, k_v,
                                    opt.transpose_centroid, opt.save_data_dir,
                                    opt.load_data_dir, opt.mt_threads,
                                    /*skip_init=*/use_sift1m);
            if (use_sift1m) {
              // Load dataset, optionally applying user-provided limits.
              if (!bench_local.loadSift1M(opt.sift1m_dir, opt.sift_nb_limit,
                                          opt.sift_nq_limit,
                                          opt.sift_k_override)) {
                std::cerr << "SIFT1M 加载失败，跳过该组合" << std::endl;
                continue;
              }
            }
            // HNSW param combos
            for (int hM : hnsw_M_list) {
              for (int efC_v : efC_list) {
                for (int efS_v : efS_list) {
                  if (contains("hnsw_flat")) {
                    auto r = bench_local.testHNSWFlat(hM, efC_v, efS_v);
                    if (r.build_time >= 0) {
                      r.dim = bench_local.getDim();
                      r.nb = bench_local.getNb();
                      r.nq = bench_local.getNq();
                      r.k = bench_local.getK();
                      r.dataset = bench_local.getDatasetName();
                      results.push_back(r);
                    }
                  }
                  // HNSW-SQ with specific bit types
                  auto hnsw_sq_types = getSQTypes("hnsw_sq");
                  for (int qtype_v : hnsw_sq_types) {
                    auto r = bench_local.testHNSWSQ(qtype_v, hM, efC_v, efS_v);
                    if (r.build_time >= 0) {
                      r.dim = bench_local.getDim();
                      r.nb = bench_local.getNb();
                      r.nq = bench_local.getNq();
                      r.k = bench_local.getK();
                      r.dataset = bench_local.getDatasetName();
                      results.push_back(r);
                    }
                  }
                  if (contains("hnsw_pq")) {
                    for (int m_v : pq_m_list) {
                      for (int nbits_v : pq_nbits_list) {
                        for (double tr_v : pq_train_ratio_list) {
                          auto r = bench_local.testHNSWPQ(m_v, nbits_v, hM,
                                                          efC_v, efS_v, tr_v);
                          if (r.build_time >= 0) {
                            r.dim = bench_local.getDim();
                            r.nb = bench_local.getNb();
                            r.nq = bench_local.getNq();
                            r.k = bench_local.getK();
                            r.pq_train_ratio = tr_v;
                            r.dataset = bench_local.getDatasetName();
                            results.push_back(r);
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
            // IVF param combos
            for (int nl_v : ivf_nlist_list) {
              for (int np_v : ivf_nprobe_list) {
                if (contains("ivf_flat")) {
                  auto r = bench_local.testIVFFlat(nl_v, np_v);
                  if (r.build_time >= 0) {
                    r.dim = bench_local.getDim();
                    r.nb = bench_local.getNb();
                    r.nq = bench_local.getNq();
                    r.k = bench_local.getK();
                    r.dataset = bench_local.getDatasetName();
                    results.push_back(r);
                  }
                }
                // IVF-SQ with specific bit types
                auto ivf_sq_types = getSQTypes("ivf_sq");
                for (int qtype_v : ivf_sq_types) {
                  auto r = bench_local.testIVFSQ(nl_v, np_v, qtype_v);
                  if (r.build_time >= 0) {
                    r.dim = bench_local.getDim();
                    r.nb = bench_local.getNb();
                    r.nq = bench_local.getNq();
                    r.k = bench_local.getK();
                    r.dataset = bench_local.getDatasetName();
                    results.push_back(r);
                  }
                }
                if (contains("ivf_pq")) {
                  for (int m_v : pq_m_list) {
                    for (int nbits_v : pq_nbits_list) {
                      for (double tr_v : pq_train_ratio_list) {
                        auto r = bench_local.testIVFPQ(nl_v, np_v, m_v, nbits_v,
                                                       tr_v);
                        if (r.build_time >= 0) {
                          r.dim = bench_local.getDim();
                          r.nb = bench_local.getNb();
                          r.nq = bench_local.getNq();
                          r.k = bench_local.getK();
                          r.pq_train_ratio = tr_v;
                          r.dataset = bench_local.getDatasetName();
                          results.push_back(r);
                        }
                      }
                    }
                  }
                }
                if (contains("ivf_rbq")) {
                  for (int qb_v : rabitq_qb_list) {
                    for (int centered_flag : rabitq_centered_list) {
                      bool centered = centered_flag != 0;
                      auto r =
                          bench_local.testIVFRaBitQ(nl_v, np_v, qb_v, centered);
                      if (r.build_time >= 0) {
                        r.dim = bench_local.getDim();
                        r.nb = bench_local.getNb();
                        r.nq = bench_local.getNq();
                        r.k = bench_local.getK();
                        r.dataset = bench_local.getDatasetName();
                        results.push_back(r);
                      }
                    }
                  }
                }
                // IVFRaBitQ + Refine
                if (contains("rbq_refine") || contains("ivf_rbq_refine")) {
                  for (int qb_v : rabitq_qb_list) {
                    for (int centered_flag : rabitq_centered_list) {
                      bool centered = centered_flag != 0;
                      for (const auto &rt : rbq_refine_type_list) {
                        for (int rk : rbq_refine_k_list) {
                          if (rk < 1)
                            continue;
                          auto r = bench_local.testIVFRaBitQRefine(
                              nl_v, np_v, qb_v, centered, rt, rk);
                          if (r.build_time >= 0) {
                            r.dim = bench_local.getDim();
                            r.nb = bench_local.getNb();
                            r.nq = bench_local.getNq();
                            r.k = bench_local.getK();
                            r.dataset = bench_local.getDatasetName();
                            results.push_back(r);
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
            // Direct RaBitQ (flat) combos (independent of IVF/HNSW params)
            if (contains("rabitq")) {
              for (int qb_v : rabitq_qb_list) {
                for (int centered_flag : rabitq_centered_list) {
                  bool centered = centered_flag != 0;
                  auto r = bench_local.testRaBitQ(qb_v, centered);
                  if (r.build_time >= 0) {
                    r.dim = bench_local.getDim();
                    r.nb = bench_local.getNb();
                    r.nq = bench_local.getNq();
                    r.k = bench_local.getK();
                    r.dataset = bench_local.getDatasetName();
                    results.push_back(r);
                  }
                }
              }
            }
#// VecML: dataset-level test (VecML has no HNSW/IVF params, but
#// should still be exercised for different dim/nb/nq/k combos)
#// Only run VecML when explicitly requested via --which=vecml.
            if (contains("vecml")) {
#ifdef HAVE_VECML
              auto vr = bench_local.testVecML(
                  opt.vecml_base_path, opt.vecml_license_path, opt.mt_threads,
                  opt.vecml_threads);
              if (vr.build_time >= 0) {
                vr.dim = bench_local.getDim();
                vr.nb = bench_local.getNb();
                vr.nq = bench_local.getNq();
                vr.k = bench_local.getK();
                vr.dataset = bench_local.getDatasetName();
                results.push_back(vr);
              }
#else
              // VecML requested but not compiled in; inform the user once.
              static bool warned_vecml = false;
              if (!warned_vecml) {
                std::cerr << "VecML requested but not available in this build "
                             "(HAVE_VECML not defined)."
                          << std::endl;
                warned_vecml = true;
              }
#endif
            }
            // VecML Fast Index test
            if (contains("vecml-fast-idx")) {
#ifdef HAVE_VECML
              // Use a separate subdirectory for fast-idx to avoid reusing
              // files from the standard VecML run when both are requested.
              auto fr = bench_local.testVecMLFastIdx(
                  opt.vecml_base_path.empty()
                      ? std::string("")
                      : (opt.vecml_base_path + "/fast_idx"),
                  opt.vecml_license_path, opt.mt_threads, opt.vecml_threads);
              if (fr.build_time >= 0) {
                fr.dim = bench_local.getDim();
                fr.nb = bench_local.getNb();
                fr.nq = bench_local.getNq();
                fr.k = bench_local.getK();
                fr.dataset = bench_local.getDatasetName();
                results.push_back(fr);
              }
#else
              static bool warned_vecml_fast = false;
              if (!warned_vecml_fast) {
                std::cerr << "VecML fast index requested but not available in "
                             "this build (HAVE_VECML not defined)."
                          << std::endl;
                warned_vecml_fast = true;
              }
#endif
            }
          }
        }
      }
    }
    return results;
  }

  void printAnalysis(const std::vector<TestResult> &results) {
    std::cout << "\n" << std::string(80, '=') << std::endl;
    std::cout << "📈 HNSW Index Types 指标总结" << std::endl;
    std::cout << std::string(80, '=') << std::endl;
    if (results.empty()) {
      std::cout << "❌ 没有成功的测试结果" << std::endl;
      return;
    }
    // Best by recall and fastest
    auto best_recall =
        *std::max_element(results.begin(), results.end(),
                          [](const TestResult &a, const TestResult &b) {
                            return a.recall_k < b.recall_k;
                          });
    auto fastest =
        *std::min_element(results.begin(), results.end(),
                          [](const TestResult &a, const TestResult &b) {
                            return a.search_time_ms < b.search_time_ms;
                          });
    auto fmtParams = [](const TestResult &r) {
      std::ostringstream oss;
      oss << "M=" << r.hnsw_M;
      if (r.method == "HNSW-SQ") {
        oss << "," << PQBenchmark::qtypeName(r.qtype);
      } else if (r.method == "HNSW-PQ") {
        oss << ",PQ(m=" << r.pq_m << ",nbits=" << r.pq_nbits << ")";
      } else if (r.method == "HNSW-RaBitQ") {
        oss << ",qb=" << r.rabitq_qb;
        if (r.rabitq_centered) {
          oss << ",centered";
        }
      }
      oss << ",efC=" << r.efC << ",efS=" << r.efS;
      return oss.str();
    };
    std::cout << "🎯 最高召回: " << best_recall.method << "("
              << fmtParams(best_recall) << ") R@" << best_recall.k << "="
              << std::fixed << std::setprecision(3) << best_recall.recall_k
              << std::endl;
    std::cout << "⚡ 最快搜索: " << fastest.method << "(" << fmtParams(fastest)
              << ") " << std::setprecision(2) << fastest.search_time_ms
              << " ms/query" << std::endl;

    // Detailed table
    std::cout << "\n📊 详细结果:" << std::endl;

    bool show_mt_columns = false;
    for (const auto &r : results) {
      if (r.has_mt) {
        show_mt_columns = true;
        break;
      }
    }

    std::ostringstream header;
    header << std::left << std::setw(18) << "method" << ' ' << std::setw(10)
           << "dataset" << ' ' << std::setw(6) << "dim" << ' ' << std::setw(8)
           << "nb" << ' ' << std::setw(6) << "nq" << ' ' << std::setw(4) << "k"
           << ' ' << std::setw(8) << "hnsw_M" << ' ' << std::setw(6) << "efC"
           << ' ' << std::setw(6) << "efS" << ' ' << std::setw(10)
           << "ivf_nlist" << ' ' << std::setw(10) << "ivf_nprobe" << ' '
           << std::setw(6) << "pq_m" << ' ' << std::setw(10) << "pq_nbits"
           << ' ' << std::setw(10) << "rbq_qb" << ' ' << std::setw(12)
           << "rbq_centered" << ' ' << std::setw(10) << "refine_k" << ' '
           << std::setw(12) << "refine_type" << ' ' << std::setw(10) << "qtype"
           << ' ' << std::setw(12) << "train_tm" << ' ' << std::setw(10)
           << "add_tm" << ' ' << std::setw(12) << "build_tm" << ' '
           << std::setw(14) << "search_tm_ms" << ' ' << std::setw(10) << "r@1"
           << ' ' << std::setw(10) << "r@5" << ' ' << std::setw(10) << "r@k"
           << ' ' << std::setw(14) << "mbs_on_disk" << ' ' << std::setw(13)
           << "compression";
    if (show_mt_columns) {
      header << ' ' << std::setw(11) << "mt_threads" << ' ' << std::setw(12)
             << "mt_recall@k";
    }
    std::string header_line = header.str();
    std::cout << header_line << std::endl;
    std::cout << std::string(header_line.size(), '-') << std::endl;

    for (const auto &r : results) {
      std::ostringstream row;
      row << std::left << std::setw(18) << r.method << ' ' << std::setw(10)
          << (r.dataset.empty() ? std::string("std-normal") : r.dataset) << ' '
          << std::setw(6) << r.dim << ' ' << std::setw(8) << r.nb << ' '
          << std::setw(6) << r.nq << ' ' << std::setw(4) << r.k << ' '
          << std::setw(8) << r.hnsw_M << ' ' << std::setw(6) << r.efC << ' '
          << std::setw(6) << r.efS << ' ' << std::setw(10) << r.ivf_nlist << ' '
          << std::setw(10) << r.ivf_nprobe << ' ' << std::setw(6) << r.pq_m
          << ' ' << std::setw(10) << r.pq_nbits << ' ' << std::setw(10)
          << r.rabitq_qb << ' ' << std::setw(12) << r.rabitq_centered << ' '
          << std::setw(10) << r.refine_k << ' ' << std::setw(12)
          << (r.refine_type.empty() ? "NA" : r.refine_type) << ' '
          << std::setw(10)
          << ((r.method == std::string("HNSW-SQ") ||
               r.method == std::string("IVF-SQ"))
                  ? PQBenchmark::qtypeName(r.qtype)
                  : "NA")
          << ' ' << std::setw(12) << std::fixed << std::setprecision(2)
          << r.train_time << ' ' << std::setw(10) << std::fixed
          << std::setprecision(2) << r.add_time << ' ' << std::setw(12)
          << std::fixed << std::setprecision(2) << r.build_time << ' '
          << std::setw(14) << std::fixed << std::setprecision(2)
          << r.search_time_ms << ' ' << std::setw(10) << std::fixed
          << std::setprecision(3) << r.recall_1 << ' ' << std::setw(10)
          << std::fixed << std::setprecision(3) << r.recall_5 << ' '
          << std::setw(10) << std::fixed << std::setprecision(3) << r.recall_k
          << ' ' << std::setw(14) << std::fixed << std::setprecision(1)
          << r.mbs_on_disk;

      std::ostringstream cr;
      if (r.method.find("HNSW-Flat") != std::string::npos ||
          r.method.find("IVF-Flat") != std::string::npos) {
        cr << "NA";
      } else {
        cr << std::fixed << std::setprecision(1) << r.compression_ratio;
      }
      row << ' ' << std::setw(13) << cr.str();

      if (show_mt_columns) {
        row << ' ' << std::setw(11)
            << (r.has_mt ? std::to_string(r.mt_threads) : std::string("NA"));
        if (r.has_mt) {
          row << ' ' << std::setw(12) << std::fixed << std::setprecision(3)
              << r.mt_recall_k;
        } else {
          row << ' ' << std::setw(12) << "NA";
        }
      }

      std::cout << row.str() << std::endl;
    }

    if (show_mt_columns) {
      std::cout << "\n🚀 多线程速览:" << std::endl;
      const std::string mt_suffix = "-mt";
      std::unordered_set<std::string> printed_methods;
      for (const auto &r : results) {
        if (!r.has_mt) {
          continue;
        }
        std::string base_method = r.method;
        if (base_method.size() > mt_suffix.size() &&
            base_method.compare(base_method.size() - mt_suffix.size(),
                                mt_suffix.size(), mt_suffix) == 0) {
          base_method =
              base_method.substr(0, base_method.size() - mt_suffix.size());
          if (printed_methods.count(base_method)) {
            continue;
          }
        } else {
          if (printed_methods.count(base_method)) {
            continue;
          }
        }
        printed_methods.insert(base_method);

        std::cout << "  - " << r.method << " (" << r.mt_threads
                  << " threads): " << std::fixed << std::setprecision(3)
                  << r.mt_search_time_ms << " ms/q";
        if (r.search_time_ms > 0.0 &&
            std::fabs(r.search_time_ms - r.mt_search_time_ms) > 1e-6) {
          std::cout << " (single " << std::setprecision(3) << r.search_time_ms
                    << " ms/q)";
        }
        std::cout << ", recall@" << r.k << "=" << std::setprecision(3)
                  << r.mt_recall_k << std::endl;
      }
    }
  }

  void saveResults(const std::vector<TestResult> &results,
                   const std::string &path) {
    bool existed = false;
    auto csv_file = results_utils::openCsvAppend(path, existed);
    if (csv_file.is_open()) {
      if (!existed) {
        csv_file
            << "method,dataset,dim,nb,nq,k,hnsw_M,efC,efS,ivf_nlist,ivf_nprobe,"
               "pq_m,"
               "pq_nbits,rabitq_qb,rabitq_centered,refine_k,refine_type,"
               "qtype,train_time,add_time,build_time,search_time_ms,recall_at_"
               "1,"
               "recall_at_5,recall_at_k,mbs_on_disk,compression_ratio,"
               "mt_threads,mt_search_time_ms,mt_recall_at_k,run_time\n";
      }

      std::string run_time = results_utils::currentRunTimeString();

      for (const auto &r : results) {
        csv_file << r.method << ","
                 << (r.dataset.empty() ? std::string("std-normal") : r.dataset)
                 << "," << r.dim << "," << r.nb << "," << r.nq << "," << r.k
                 << "," << r.hnsw_M << "," << r.efC << "," << r.efS << ","
                 << r.ivf_nlist << "," << r.ivf_nprobe << "," << r.pq_m << ","
                 << r.pq_nbits << "," << r.rabitq_qb << "," << r.rabitq_centered
                 << "," << r.refine_k << ","
                 << (r.refine_type.empty() ? std::string("NA") : r.refine_type)
                 << ","
                 << ((r.method == std::string("HNSW-SQ") ||
                      r.method == std::string("IVF-SQ"))
                         ? qtypeName(r.qtype)
                         : std::string("NA"))
                 << "," << r.train_time << "," << r.add_time << ","
                 << r.build_time << "," << r.search_time_ms << "," << r.recall_1
                 << "," << r.recall_5 << "," << r.recall_k << ","
                 << r.mbs_on_disk << ",";
        if (r.method.find("HNSW-Flat") != std::string::npos ||
            r.method.find("IVF-Flat") != std::string::npos)
          csv_file << "NA";
        else
          csv_file << r.compression_ratio;
        csv_file << ',';
        if (r.has_mt)
          csv_file << r.mt_threads;
        else
          csv_file << "NA";
        csv_file << ',';
        if (r.has_mt)
          csv_file << r.mt_search_time_ms;
        else
          csv_file << "NA";
        csv_file << ',';
        if (r.has_mt)
          csv_file << r.mt_recall_k;
        else
          csv_file << "NA";
        csv_file << ',' << run_time << "\n";
      }
      csv_file.close();
      if (existed)
        std::cout << "\n💾 结果已追加到: " << path << std::endl;
      else
        std::cout << "\n💾 结果已保存到: " << path << std::endl;
    } else {
      std::cerr << "❌ 无法创建CSV文件" << std::endl;
    }
  }
};

// ---------------------------------------------------------------------------
// Lightweight OO test wrapper framework (moved here so PQBenchmark and
// PQBenchmark::TestResult are already defined). Each algorithm is
// represented as an IndexTest object that can be invoked with a
// PQBenchmark instance. This is a small, incremental refactor: concrete
// tests delegate to the existing bench_local.test* helpers while
// providing a unified spot for future per-step overrides.

struct IndexTest {
  virtual ~IndexTest() = default;
  // Execute the full test using provided PQBenchmark which owns data.
  virtual PQBenchmark::TestResult execute(PQBenchmark &bench) = 0;
};

struct HNSWFlatTest : public IndexTest {
  int m, efC, efS;
  HNSWFlatTest(int m_, int efC_, int efS_) : m(m_), efC(efC_), efS(efS_) {}
  PQBenchmark::TestResult execute(PQBenchmark &bench) override {
    return bench.testHNSWFlat(m, efC, efS);
  }
};

struct HNSWSQTest : public IndexTest {
  int qtype, m, efC, efS;
  HNSWSQTest(int qtype_, int m_, int efC_, int efS_)
      : qtype(qtype_), m(m_), efC(efC_), efS(efS_) {}
  PQBenchmark::TestResult execute(PQBenchmark &bench) override {
    return bench.testHNSWSQ(qtype, m, efC, efS);
  }
};

struct HNSWPQTest : public IndexTest {
  int pq_m, pq_nbits, m, efC, efS;
  double tr;
  HNSWPQTest(int pq_m_, int pq_nbits_, int m_, int efC_, int efS_, double tr_)
      : pq_m(pq_m_), pq_nbits(pq_nbits_), m(m_), efC(efC_), efS(efS_), tr(tr_) {
  }
  PQBenchmark::TestResult execute(PQBenchmark &bench) override {
    return bench.testHNSWPQ(pq_m, pq_nbits, m, efC, efS, tr);
  }
};

struct IVFFlatTest : public IndexTest {
  int nlist, nprobe;
  IVFFlatTest(int nlist_, int nprobe_) : nlist(nlist_), nprobe(nprobe_) {}
  PQBenchmark::TestResult execute(PQBenchmark &bench) override {
    return bench.testIVFFlat(nlist, nprobe);
  }
};

struct IVFSQTest : public IndexTest {
  int nlist, nprobe, qtype;
  IVFSQTest(int nlist_, int nprobe_, int qtype_)
      : nlist(nlist_), nprobe(nprobe_), qtype(qtype_) {}
  PQBenchmark::TestResult execute(PQBenchmark &bench) override {
    return bench.testIVFSQ(nlist, nprobe, qtype);
  }
};

struct IVFPQTest : public IndexTest {
  int nlist, nprobe, m, nbits;
  double tr;
  IVFPQTest(int nlist_, int nprobe_, int m_, int nbits_, double tr_)
      : nlist(nlist_), nprobe(nprobe_), m(m_), nbits(nbits_), tr(tr_) {}
  PQBenchmark::TestResult execute(PQBenchmark &bench) override {
    return bench.testIVFPQ(nlist, nprobe, m, nbits, tr);
  }
};

struct RaBitQTest : public IndexTest {
  int qb;
  bool centered;
  RaBitQTest(int qb_, bool centered_) : qb(qb_), centered(centered_) {}
  PQBenchmark::TestResult execute(PQBenchmark &bench) override {
    return bench.testRaBitQ(qb, centered);
  }
};

struct IVFRaBitQTest : public IndexTest {
  int nlist, nprobe, qb;
  bool centered;
  IVFRaBitQTest(int nlist_, int nprobe_, int qb_, bool centered_)
      : nlist(nlist_), nprobe(nprobe_), qb(qb_), centered(centered_) {}
  PQBenchmark::TestResult execute(PQBenchmark &bench) override {
    return bench.testIVFRaBitQ(nlist, nprobe, qb, centered);
  }
};

struct IVFRaBitQRefineTest : public IndexTest {
  int nlist, nprobe, qb;
  bool centered;
  std::string refine_type;
  int refine_k;
  IVFRaBitQRefineTest(int nlist_, int nprobe_, int qb_, bool centered_,
                      const std::string &rt, int rk)
      : nlist(nlist_), nprobe(nprobe_), qb(qb_), centered(centered_),
        refine_type(rt), refine_k(rk) {}
  PQBenchmark::TestResult execute(PQBenchmark &bench) override {
    return bench.testIVFRaBitQRefine(nlist, nprobe, qb, centered, refine_type,
                                     refine_k);
  }
};

#ifdef HAVE_VECML
struct VecMLTestWrap : public IndexTest {
  std::string base_path, license_path;
  int mt_threads;
  int vec_threads;
  VecMLTestWrap(const std::string &b, const std::string &l, int mt, int vt)
      : base_path(b), license_path(l), mt_threads(mt), vec_threads(vt) {}
  PQBenchmark::TestResult execute(PQBenchmark &bench) override {
    return bench.testVecML(base_path, license_path, mt_threads, vec_threads);
  }
};
#endif

// CLI parsing helpers moved to integrate_faiss/cli_utils.{h,cpp}

static std::vector<PQBenchmark::TestResult> expandResultsWithMtVariants(
    const std::vector<PQBenchmark::TestResult> &results) {
  std::vector<PQBenchmark::TestResult> expanded;
  expanded.reserve(results.size() * 2);
  constexpr const char *kMtSuffix = "-mt";
  for (const auto &r : results) {
    expanded.push_back(r);
    if (!(r.has_mt && r.mt_threads > 0)) {
      continue;
    }
    if (r.method.find(kMtSuffix) != std::string::npos) {
      continue;
    }
    PQBenchmark::TestResult mt = r;
    mt.method = r.method + kMtSuffix;
    mt.search_time_ms = r.mt_search_time_ms;
    mt.dataset = r.dataset;
    if (r.mt_recall_1 > 0.0) {
      mt.recall_1 = r.mt_recall_1;
    }
    if (r.mt_recall_5 > 0.0) {
      mt.recall_5 = r.mt_recall_5;
    }
    mt.recall_k = r.mt_recall_k;
    mt.mt_search_time_ms = r.mt_search_time_ms;
    mt.mt_recall_k = r.mt_recall_k;
    mt.mt_recall_1 = r.mt_recall_1;
    mt.mt_recall_5 = r.mt_recall_5;
    expanded.push_back(std::move(mt));
  }
  return expanded;
}

int main(int argc, char **argv) {
  Options opt;
  // Naive CLI parsing
  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    auto next = [&](int &dst) {
      if (i + 1 < argc)
        dst = std::stoi(argv[++i]);
    };
    auto nexts = [&](std::string &dst) {
      if (i + 1 < argc)
        dst = argv[++i];
    };
    auto handleListOrSingleString = [&](std::vector<std::string> &lst,
                                        std::string &single) {
      std::string s;
      nexts(s);
      if (s.find(',') != std::string::npos)
        lst = splitCSV(s);
      else if (!s.empty())
        single = s;
    };
    auto handleListOrSingleInt = [&](std::vector<int> &lst, int &single) {
      std::string s;
      nexts(s);
      if (s.find(',') != std::string::npos)
        lst = toIntList(s);
      else {
        try {
          single = std::stoi(s);
        } catch (...) {
        }
      }
    };
    if (a == "--dim") {
      handleListOrSingleInt(opt.dim_list, opt.dim);
    } else if (a == "--nb") {
      handleListOrSingleInt(opt.nb_list, opt.nb);
    } else if (a == "--nq") {
      handleListOrSingleInt(opt.nq_list, opt.nq);
    } else if (a == "--k") {
      handleListOrSingleInt(opt.k_list, opt.k);
    } else if (a == "--hnsw-M") {
      handleListOrSingleInt(opt.hnsw_M_list, opt.hnsw_M);
    } else if (a == "--efC") {
      handleListOrSingleInt(opt.efC_list, opt.efC);
    } else if (a == "--efS") {
      handleListOrSingleInt(opt.efS_list, opt.efS);
    } else if (a == "--pq-m") {
      handleListOrSingleInt(opt.pq_m_list, opt.pq_m);
    } else if (a == "--pq-nbits") {
      handleListOrSingleInt(opt.pq_nbits_list, opt.pq_nbits);
    } else if (a == "--pq-train-ratio") {
      std::string s;
      nexts(s);
      if (s.find(',') != std::string::npos) {
        opt.pq_train_ratio_list = toDoubleList(s);
      } else {
        try {
          opt.pq_train_ratio = std::stod(s);
        } catch (...) {
        }
        if (opt.pq_train_ratio < 0.0)
          opt.pq_train_ratio = 0.0;
        if (opt.pq_train_ratio > 1.0)
          opt.pq_train_ratio = 1.0;
      }
      // } else if (a == "--sq-qtype") {  // removed - now specified in --which
      //   std::string s;
      //   nexts(s);
      //   if (s.find(',') != std::string::npos) {
      //     auto parts = splitCSV(s);
      //     for (auto &p : parts)
      //       opt.sq_qtype_list.push_back(parseQType(p));
      //   } else {
      //     opt.sq_qtype = parseQType(s);
      //   }
    } else if (a == "--ivf-nlist") {
      handleListOrSingleInt(opt.ivf_nlist_list, opt.ivf_nlist);
    } else if (a == "--ivf-nprobe") {
      handleListOrSingleInt(opt.ivf_nprobe_list, opt.ivf_nprobe);
    } else if (a == "--rabitq-qb") {
      handleListOrSingleInt(opt.rabitq_qb_list, opt.rabitq_qb);
    } else if (a == "--rabitq-centered") {
      std::string s;
      nexts(s);
      if (s.find(',') != std::string::npos) {
        opt.rabitq_centered_list = toIntList(s);
        for (int &v : opt.rabitq_centered_list) {
          v = v ? 1 : 0;
        }
      } else if (!s.empty()) {
        try {
          opt.rabitq_centered = (std::stoi(s) != 0);
        } catch (...) {
          std::string lowered = s;
          std::transform(lowered.begin(), lowered.end(), lowered.begin(),
                         [](unsigned char c) { return std::tolower(c); });
          if (lowered == "true" || lowered == "t" || lowered == "yes" ||
              lowered == "y") {
            opt.rabitq_centered = true;
          } else if (lowered == "false" || lowered == "f" || lowered == "no" ||
                     lowered == "n") {
            opt.rabitq_centered = false;
          }
        }
      } else {
        // flag form defaults to true when no explicit value provided
        opt.rabitq_centered = true;
      }
    } else if (a == "--rbq-refine-type") {
      handleListOrSingleString(opt.rbq_refine_type_list, opt.rbq_refine_type);
    } else if (a == "--rbq-refine-k") {
      handleListOrSingleInt(opt.rbq_refine_k_list, opt.rbq_refine_k);
    } else if (a == "--which") {
      std::string s;
      nexts(s);
      opt.which = splitCSV(s);
    } else if (a == "--out-csv")
      nexts(opt.out_csv);
    else if (a == "--save-data-dir")
      nexts(opt.save_data_dir);
    else if (a == "--load-data-dir")
      nexts(opt.load_data_dir);
    else if (a == "--transpose-centroid") {
      opt.transpose_centroid = true;
    } else if (a == "--no-transpose-centroid") {
      opt.transpose_centroid = false; // explicit disable
    } else if (a == "--vecml-base-path") {
      nexts(opt.vecml_base_path);
    } else if (a == "--vecml-license") {
      nexts(opt.vecml_license_path);
    } else if (a == "--vecml-threads") {
      int v = 16;
      auto next_int = [&](int &dst) {
        if (i + 1 < argc)
          dst = std::stoi(argv[++i]);
      };
      next_int(v);
      if (v <= 0)
        v = 16;
      opt.vecml_threads = v;
    } else if (a == "--sift1m-dir") {
      nexts(opt.sift1m_dir);
      if (!opt.sift1m_dir.empty())
        opt.use_sift1m = true;
    } else if (a == "--sift1m-nb-limit") {
      next(opt.sift_nb_limit);
      if (opt.sift_nb_limit < 0)
        opt.sift_nb_limit = -1;
    } else if (a == "--sift1m-nq-limit") {
      next(opt.sift_nq_limit);
      if (opt.sift_nq_limit < 0)
        opt.sift_nq_limit = -1;
    } else if (a == "--sift1m-k-override") {
      next(opt.sift_k_override);
      if (opt.sift_k_override < 0)
        opt.sift_k_override = -1;
    } else if (a == "--mt-threads") {
      std::string s;
      nexts(s);
      try {
        opt.mt_threads = std::stoi(s);
        if (opt.mt_threads < 0)
          opt.mt_threads = 0;
      } catch (...) {
        opt.mt_threads = 0;
      }
    } else if (a == "-h" || a == "--help") {
      std::cout
          << "Usage: ./bench [options]\n"
             "  --dim INT[,INT...]           vector dim list (default 128)\n"
             "  --nb INT[,INT...]            database size list (default "
             "20000)\n"
             "  --nq INT[,INT...]            queries count list (default 500)\n"
             "  --k INT[,INT...]             top-k list (default 10)\n"
             "  --hnsw-M INT[,INT...]        HNSW M list (default 32)\n"
             "  --efC INT[,INT...]           HNSW efConstruction list (default "
             "200)\n"
             "  --efS INT[,INT...]           HNSW efSearch list (default 64)\n"
             "  --pq-m INT[,INT...]          PQ m list for HNSW-PQ (default "
             "16)\n"
             "  --pq-nbits INT[,INT...]      PQ nbits list for HNSW-PQ "
             "(default 8)\n"
             "  --pq-train-ratio F[,F...]    PQ train ratio list in [0,1] "
             "(default 1.0)\n"
             "  --ivf-nlist INT[,INT...]     IVF nlist list (default 256)\n"
             "  --ivf-nprobe INT[,INT...]    IVF nprobe list (default 8)\n"
             "  --rabitq-qb INT[,INT...]     RaBitQ qb bits for query (default "
             "8)\n"
             "  --rabitq-centered 0|1[,0|1...] RaBitQ centered query flag "
             "(default 0)\n"
             "  --rbq-refine-type STR[,STR...]  refine type for IVFRaBitQ "
             "refine (flat|sq8|sq4|fp16|bf16) (default flat)\n"
             "  --rbq-refine-k INT[,INT...]     refine k-factor (>=1), "
             "multiplier of k for first-stage candidates (default 2)\n"
             "  --which STR                  comma list: "
             "all|hnsw_flat|hnsw_sq4|hnsw_sq8|hnsw_pq|hnsw_rabitq|ivf_flat|ivf_"
             "sq4|ivf_sq8|ivf_pq|"
             "ivf_rbq|rbq_refine|ivf_rbq_refine|rabitq|vecml|vecml-fast-idx "
             "(default all)\n"
             "  --out-csv PATH      output csv path (default "
             "hnsw_index_types_results.csv)\n"
             "  --save-data-dir PATH         save test data (database, "
             "queries, groundtruth) "
             "to specified directory\n"
             "  --load-data-dir PATH         load test data from specified "
             "directory "
             "(if files exist, skips generation)\n"
             "  --transpose-centroid         enable PQ transposed centroids "
             "(default off)\n"
             "  --no-transpose-centroid      disable PQ transposed centroids "
             "(override)\n"
             "  --vecml-base-path PATH         path to VecML SDK directory "
             "(contains lib and headers)\n"
             "  --vecml-license PATH           path to VecML license file "
             "(optional, default: license.txt)\n";
      std::cout << "  --vecml-threads INT         threads used by VecML for "
                   "index attach/add (default 16)\n";
      std::cout << "  --sift1m-dir PATH           load SIFT1M dataset from "
                   "PATH (expects sift_base.fvecs, sift_query.fvecs, "
                   "sift_groundtruth.ivecs)\n";
      std::cout << "  --sift1m-nb-limit INT       optional: limit number of "
                   "base vectors to first INT (default off)\n";
      std::cout << "  --sift1m-nq-limit INT       optional: limit number of "
                   "queries to first INT (default off)\n";
      std::cout << "  --sift1m-k-override INT     optional: override top-K per "
                   "query (capped by ground truth K)\n";
      std::cout << "  --mt-threads INT             threads for multi-thread "
                   "search across "
                   "all selected methods (default: hardware threads)\n";
      return 0;
    }
  }

  try {
    // Avoid generating synthetic data at top-level; per-combination
    // instances will handle data init (and SIFT1M load if requested).
    PQBenchmark bench(opt.dim, opt.nb, opt.nq, opt.k, opt.transpose_centroid,
                      opt.save_data_dir, opt.load_data_dir, opt.mt_threads,
                      /*skip_init=*/true);
    auto results = bench.runIndexTypeBenchmarks(opt);

    // Note: VecML tests are now executed per-dataset inside
    // runIndexTypeBenchmarks when requested via --which=vecml or when
    // --vecml-base-path is provided.
    auto final_results = expandResultsWithMtVariants(results);
    bench.printAnalysis(final_results);
    bench.saveResults(final_results, opt.out_csv);
    std::cout << "\n✅ 分析完成！" << std::endl;
  } catch (const std::exception &e) {
    std::cerr << "❌ 错误: " << e.what() << std::endl;
    return 1;
  }
  return 0;
}

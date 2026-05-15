#include <algorithm>
#include <array>
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

namespace demo {

constexpr uint32_t kMagic = 0x46564946; // "FIVF"
constexpr uint32_t kVersion = 1;

struct Options {
  std::string out = "ivf_mmap_proto/faiss_like_index.bin";
  int n = 20000;
  int d = 32;
  int nq = 100;
  int nlist = 64;
  int nprobe = 8;
  int k = 10;
  int kmeans_iters = 6;
  uint32_t seed = 42;
};

// On-disk header for a single-file index.
struct DiskHeader {
  uint32_t magic = kMagic;
  uint32_t version = kVersion;
  uint32_t d = 0;
  uint32_t nlist = 0;
  uint32_t code_size = 0;
  uint32_t reserved0 = 0;
  uint64_t ntotal = 0;
  uint64_t dir_offset = 0;
  uint64_t data_offset = 0;
  uint64_t reserved1 = 0;
};

// Equivalent to "inverted list directory": where each list starts and how many codes it has.
struct ListDirEntry {
  uint64_t offset = 0; // absolute file offset
  uint64_t size = 0;   // number of entries in this list
};

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

  std::vector<float> sums(static_cast<size_t>(nlist) * d, 0.0f);
  std::vector<int> counts(nlist, 0);
  for (int it = 0; it < iters; ++it) {
    std::fill(sums.begin(), sums.end(), 0.0f);
    std::fill(counts.begin(), counts.end(), 0);
    for (int i = 0; i < n; ++i) {
      const float* x = &xb[static_cast<size_t>(i) * d];
      int cid = argmin_centroid(x, centroids, nlist, d);
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

// Simple SQ8 codec (per-dimension min/max) to emulate compressed codes in IVF lists.
struct SQ8Codec {
  int d = 0;
  std::vector<float> vmin;   // [d]
  std::vector<float> invgap; // [d], inv(max-min)

  void train(const std::vector<float>& xb, int n, int dim) {
    d = dim;
    vmin.assign(static_cast<size_t>(d), std::numeric_limits<float>::infinity());
    std::vector<float> vmax(static_cast<size_t>(d), -std::numeric_limits<float>::infinity());
    for (int i = 0; i < n; ++i) {
      const float* x = &xb[static_cast<size_t>(i) * d];
      for (int j = 0; j < d; ++j) {
        vmin[j] = std::min(vmin[j], x[j]);
        vmax[j] = std::max(vmax[j], x[j]);
      }
    }
    invgap.resize(static_cast<size_t>(d));
    for (int j = 0; j < d; ++j) {
      float gap = std::max(1e-12f, vmax[j] - vmin[j]);
      invgap[j] = 1.0f / gap;
    }
  }

  // code_size == d bytes
  void encode(const float* x, uint8_t* code) const {
    for (int j = 0; j < d; ++j) {
      float q = (x[j] - vmin[j]) * invgap[j] * 255.0f;
      q = std::max(0.0f, std::min(255.0f, q));
      code[j] = static_cast<uint8_t>(std::lround(q));
    }
  }

  float decode_value(int j, uint8_t c) const {
    return vmin[j] + (static_cast<float>(c) / 255.0f) / invgap[j];
  }
};

// In-memory representation before writing single-file on-disk inverted lists.
struct InMemoryLists {
  int code_size = 0;
  std::vector<std::vector<int64_t>> ids;       // [nlist][list_size]
  std::vector<std::vector<uint8_t>> codes_raw; // [nlist][list_size * code_size]
};

void build_inverted_lists(const std::vector<float>& xb, int n, int d, const std::vector<float>& centroids, int nlist,
                          const SQ8Codec& codec, InMemoryLists* out) {
  out->code_size = d;
  out->ids.assign(static_cast<size_t>(nlist), {});
  out->codes_raw.assign(static_cast<size_t>(nlist), {});
  std::vector<uint8_t> tmp(static_cast<size_t>(d));
  for (int i = 0; i < n; ++i) {
    const float* x = &xb[static_cast<size_t>(i) * d];
    int lid = argmin_centroid(x, centroids, nlist, d);
    codec.encode(x, tmp.data());
    out->ids[static_cast<size_t>(lid)].push_back(i);
    auto& bucket = out->codes_raw[static_cast<size_t>(lid)];
    bucket.insert(bucket.end(), tmp.begin(), tmp.end());
  }
}

struct LoadedIndex {
  DiskHeader h;
  std::vector<float> centroids; // kept in RAM
  std::vector<float> vmin;      // codec params in RAM
  std::vector<float> invgap;
  const ListDirEntry* dir = nullptr; // mmap-backed directory
  const uint8_t* base = nullptr;     // mmap base ptr
};

void write_index_file(const std::string& path, int d, int nlist, const std::vector<float>& centroids,
                      const SQ8Codec& codec, const InMemoryLists& lists) {
  std::ofstream os(path, std::ios::binary | std::ios::trunc);
  if (!os) throw std::runtime_error("failed to open " + path);

  DiskHeader h;
  h.d = static_cast<uint32_t>(d);
  h.nlist = static_cast<uint32_t>(nlist);
  h.code_size = static_cast<uint32_t>(lists.code_size);
  uint64_t ntotal = 0;
  for (int i = 0; i < nlist; ++i) ntotal += lists.ids[static_cast<size_t>(i)].size();
  h.ntotal = ntotal;
  h.dir_offset = sizeof(DiskHeader);

  // Layout:
  // [DiskHeader]
  // [centroids: float(nlist*d)]
  // [codec params vmin: float(d)]
  // [codec params invgap: float(d)]
  // [ListDirEntry(nlist)]
  // [list payloads ...]
  uint64_t centroids_bytes = static_cast<uint64_t>(nlist) * d * sizeof(float);
  uint64_t codec_bytes = static_cast<uint64_t>(2 * d) * sizeof(float);
  uint64_t dir_bytes = static_cast<uint64_t>(nlist) * sizeof(ListDirEntry);
  h.data_offset = sizeof(DiskHeader) + centroids_bytes + codec_bytes + dir_bytes;

  std::vector<ListDirEntry> dir(static_cast<size_t>(nlist));
  uint64_t cursor = h.data_offset;
  uint64_t per_entry = sizeof(int64_t) + static_cast<uint64_t>(lists.code_size) * sizeof(uint8_t);
  for (int lid = 0; lid < nlist; ++lid) {
    uint64_t sz = lists.ids[static_cast<size_t>(lid)].size();
    dir[static_cast<size_t>(lid)] = ListDirEntry{cursor, sz};
    cursor += sz * per_entry;
  }

  os.write(reinterpret_cast<const char*>(&h), sizeof(h));
  os.write(reinterpret_cast<const char*>(centroids.data()), static_cast<std::streamsize>(centroids_bytes));
  os.write(reinterpret_cast<const char*>(codec.vmin.data()), static_cast<std::streamsize>(d * sizeof(float)));
  os.write(reinterpret_cast<const char*>(codec.invgap.data()), static_cast<std::streamsize>(d * sizeof(float)));
  os.write(reinterpret_cast<const char*>(dir.data()), static_cast<std::streamsize>(dir_bytes));

  for (int lid = 0; lid < nlist; ++lid) {
    const auto& ids = lists.ids[static_cast<size_t>(lid)];
    const auto& codes = lists.codes_raw[static_cast<size_t>(lid)];
    uint64_t sz = ids.size();
    for (uint64_t i = 0; i < sz; ++i) {
      int64_t id = ids[static_cast<size_t>(i)];
      os.write(reinterpret_cast<const char*>(&id), sizeof(id));
      const uint8_t* code = &codes[static_cast<size_t>(i) * lists.code_size];
      os.write(reinterpret_cast<const char*>(code), lists.code_size);
    }
  }
  if (!os) throw std::runtime_error("failed to write index payload");
}

LoadedIndex load_index_from_mmap(const MMapFile& mm) {
  LoadedIndex idx;
  idx.base = reinterpret_cast<const uint8_t*>(mm.ptr);
  std::memcpy(&idx.h, idx.base, sizeof(DiskHeader));
  if (idx.h.magic != kMagic || idx.h.version != kVersion) {
    throw std::runtime_error("bad index file magic/version");
  }
  int d = static_cast<int>(idx.h.d);
  int nlist = static_cast<int>(idx.h.nlist);
  size_t off = sizeof(DiskHeader);

  idx.centroids.resize(static_cast<size_t>(nlist) * d);
  std::memcpy(idx.centroids.data(), idx.base + off, idx.centroids.size() * sizeof(float));
  off += idx.centroids.size() * sizeof(float);

  idx.vmin.resize(static_cast<size_t>(d));
  idx.invgap.resize(static_cast<size_t>(d));
  std::memcpy(idx.vmin.data(), idx.base + off, idx.vmin.size() * sizeof(float));
  off += idx.vmin.size() * sizeof(float);
  std::memcpy(idx.invgap.data(), idx.base + off, idx.invgap.size() * sizeof(float));
  off += idx.invgap.size() * sizeof(float);

  idx.dir = reinterpret_cast<const ListDirEntry*>(idx.base + off);
  return idx;
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

float sq8_distance_to_query(const uint8_t* code, const float* q, const LoadedIndex& idx) {
  int d = static_cast<int>(idx.h.d);
  float s = 0.0f;
  for (int j = 0; j < d; ++j) {
    float x = idx.vmin[j] + (static_cast<float>(code[j]) / 255.0f) / idx.invgap[j];
    float diff = x - q[j];
    s += diff * diff;
  }
  return s;
}

std::pair<std::vector<int>, size_t> search_ivf_sq8(const LoadedIndex& idx, const float* q, int nprobe, int k) {
  int d = static_cast<int>(idx.h.d);
  int nlist = static_cast<int>(idx.h.nlist);
  int code_size = static_cast<int>(idx.h.code_size);
  uint64_t stride = sizeof(int64_t) + static_cast<uint64_t>(code_size);

  std::vector<std::pair<float, int>> coarse;
  coarse.reserve(nlist);
  for (int c = 0; c < nlist; ++c) {
    coarse.emplace_back(l2_sq(q, &idx.centroids[static_cast<size_t>(c) * d], d), c);
  }
  std::nth_element(coarse.begin(), coarse.begin() + nprobe, coarse.end(),
                   [](const auto& a, const auto& b) { return a.first < b.first; });
  coarse.resize(nprobe);

  std::vector<std::pair<float, int>> cand;
  size_t cand_cnt = 0;
  for (const auto& p : coarse) {
    int lid = p.second;
    ListDirEntry e = idx.dir[static_cast<size_t>(lid)];
    cand_cnt += static_cast<size_t>(e.size);
    const uint8_t* list_ptr = idx.base + e.offset;
    for (uint64_t i = 0; i < e.size; ++i) {
      const uint8_t* entry = list_ptr + i * stride;
      int64_t id64 = 0;
      std::memcpy(&id64, entry, sizeof(int64_t));
      const uint8_t* code = entry + sizeof(int64_t);
      float d2 = sq8_distance_to_query(code, q, idx);
      cand.emplace_back(d2, static_cast<int>(id64));
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
    if (a == "--out") opt.out = need("--out");
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

int run(int argc, char** argv) {
  Options opt = parse_args(argc, argv);

  // Main pipeline:
  // 1) Generate data
  // 2) Build coarse quantizer + train codec + build in-memory lists
  // 3) Persist one-file on-disk index
  // 4) mmap the index and run search on probed lists
  std::mt19937 rng(opt.seed);
  std::normal_distribution<float> normal(0.0f, 1.0f);
  std::vector<float> xb(static_cast<size_t>(opt.n) * opt.d);
  std::vector<float> xq(static_cast<size_t>(opt.nq) * opt.d);
  for (float& v : xb) v = normal(rng);
  for (float& v : xq) v = normal(rng);

  auto t0 = std::chrono::steady_clock::now();
  std::vector<float> centroids;
  train_kmeans(xb, opt.n, opt.d, opt.nlist, opt.kmeans_iters, opt.seed, &centroids);

  SQ8Codec codec;
  codec.train(xb, opt.n, opt.d);

  InMemoryLists lists;
  build_inverted_lists(xb, opt.n, opt.d, centroids, opt.nlist, codec, &lists);
  write_index_file(opt.out, opt.d, opt.nlist, centroids, codec, lists);
  auto t1 = std::chrono::steady_clock::now();

  MMapFile mm = mmap_ro(opt.out);
  LoadedIndex idx = load_index_from_mmap(mm);
  auto t2 = std::chrono::steady_clock::now();

  double recall_sum = 0.0;
  size_t cand_sum = 0;
  auto s0 = std::chrono::steady_clock::now();
  for (int i = 0; i < opt.nq; ++i) {
    const float* q = &xq[static_cast<size_t>(i) * opt.d];
    std::vector<int> gt = brute_force_topk(xb, q, opt.n, opt.d, opt.k);
    auto pred_and_cnt = search_ivf_sq8(idx, q, opt.nprobe, opt.k);
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
  double per_entry = sizeof(int64_t) + static_cast<double>(idx.h.code_size);
  double bytes_per_query = avg_cands * per_entry;
  double bytes_full = static_cast<double>(opt.n) * per_entry;

  std::cout << "=== Faiss-like OnDiskIVF prototype (IVF + SQ8 + mmap) ===\n";
  std::cout << "N=" << opt.n << ", D=" << opt.d << ", NQ=" << opt.nq << ", nlist=" << opt.nlist
            << ", nprobe=" << opt.nprobe << ", k=" << opt.k << "\n";
  std::cout << "build_index_time=" << build_s << "s, mmap_time=" << mmap_s << "s\n";
  std::cout << "search_time=" << search_s << "s, qps=" << (opt.nq / search_s) << "\n";
  std::cout << "avg_recall@" << opt.k << "=" << avg_recall << "\n";
  std::cout << "avg_candidates=" << avg_cands << "/" << opt.n << " (" << (cand_ratio * 100.0) << "% of full scan)\n";
  std::cout << "estimated_index_bytes_read_per_query=" << (bytes_per_query / (1024.0 * 1024.0))
            << " MiB (full scan " << (bytes_full / (1024.0 * 1024.0)) << " MiB)\n";
  std::cout << "file=" << opt.out << ", file_size=" << (mm.bytes / (1024.0 * 1024.0)) << " MiB\n";
  std::cout << "Interpretation: this mirrors Faiss flow (coarse + encoded lists + on-disk list scan).\n";
  return 0;
}

} // namespace demo

int main(int argc, char** argv) {
  try {
    return demo::run(argc, argv);
  } catch (const std::exception& e) {
    std::cerr << "error: " << e.what() << "\n";
    return 1;
  }
}

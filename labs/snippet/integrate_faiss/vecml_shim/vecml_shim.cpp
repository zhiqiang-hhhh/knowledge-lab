#include "vecml_shim/vecml_shim.h"
#include <chrono>
#include <ctime>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#ifdef __has_include
#if __has_include(<fluffy_interface.h>)
#include <fluffy_interface.h>
#include <query_results.h>
#else
#error "fluffy_interface.h not found in include path"
#endif
#endif

using namespace std;

struct VecMLHandle {
  std::shared_ptr<fluffy::FluffyInterface> api;
  std::string index_name; // name of the attached index to use for searches
  std::string
      base_path; // store base path provided at creation for disk-size queries
  // Fast index options
  bool use_fast_index = false;
  float fast_shrink_rate = 0.4f;
  int fast_max_samples = 100000;
  int index_threads = 16;
};

// 轻量日志工具（默认开启，可通过 VECML_LOG=0 关闭）
static bool vecml_log_enabled() {
  const char *v = ::getenv("VECML_LOG");
  if (!v)
    return true; // 默认开
  std::string s(v);
  for (auto &c : s)
    c = (char)std::tolower((unsigned char)c);
  if (s == "0" || s == "false" || s == "off")
    return false;
  return true;
}

static std::string now_ts() {
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
  std::ostringstream oss;
  oss << buf << "." << std::setw(3) << std::setfill('0') << ms.count();
  return oss.str();
}

static void vlog(const std::string &msg) {
  if (!vecml_log_enabled())
    return;
  std::ostringstream oss;
  oss << "[" << now_ts() << "] [VecML] [tid=" << std::this_thread::get_id()
      << "] " << msg << "\n";
  std::cerr << oss.str();
}

extern "C" {

vecml_ctx_t vecml_create(const char *base_path, const char *license_path,
                         bool fast_index) {
  try {
    // Always clean the base path on each construction to keep behavior simple
    try {
      if (base_path && !std::string(base_path).empty()) {
        std::error_code fec;
        std::filesystem::remove_all(base_path, fec);
        if (fec)
          vlog(std::string("create: remove ") + base_path +
               " failed: " + fec.message());
        else
          vlog(std::string("create: removed base path ") + base_path);
      } else {
        vlog("create: base_path is null or empty");
      }
    } catch (const std::exception &e) {
      vlog(std::string("create: exception while removing base path: ") +
           e.what());
    }

    VecMLHandle *h = new VecMLHandle();
    h->base_path = base_path ? std::string(base_path) : std::string();
    vlog(std::string("create: init FluffyInterface, base=") +
         (base_path ? base_path : "") +
         ", license=" + (license_path ? license_path : ""));
    h->api = std::make_shared<fluffy::FluffyInterface>(
        std::string(base_path), std::string(license_path));
    // Initialize the SDK per-instance
    fluffy::ErrorCode ec = h->api->init();
    if (ec != fluffy::ErrorCode::Success) {
      vlog(std::string("create: init failed ec=") + std::to_string((int)ec));
      delete h;
      return nullptr;
    }

    // Choose a default index name. Actual attach happens in add_data.
    h->index_name = "test_index";
    // Configure fast-index preference for this handle; effective at add_data
    h->use_fast_index = fast_index;
    vlog(std::string("create: success, use_fast_index=") +
         (fast_index ? "true" : "false"));
    return reinterpret_cast<vecml_ctx_t>(h);
  } catch (const std::exception &e) {
    vlog(std::string("create: exception: ") + e.what());
    return nullptr;
  }
}

int vecml_add_data(vecml_ctx_t ctx, const float *data, int n, int dim,
                   const long *ids) {
  if (!ctx)
    return -1;
  VecMLHandle *h = reinterpret_cast<VecMLHandle *>(ctx);
  try {
    vlog(std::string("add: start n=") + std::to_string(n) +
         ", dim=" + std::to_string(dim) +
         ", threads=" + std::to_string(h->index_threads) +
         (h->use_fast_index ? ", mode=fast-index" : ", mode=standard"));
    // Ensure an index exists with the correct dimension and distance type.
    // If no index was attached earlier (or vector dim is unknown), attach
    // one now using the provided `dim` and Euclidean distance so results
    // match Faiss's L2 baseline.
    if (h->api->get_vector_dim() == 0) {
      // cast to int to match the SDK overload - dim_t is an SDK typedef
      fluffy::ErrorCode attach_ec = fluffy::ErrorCode::Success;
      if (h->use_fast_index) {
        // Use fast index (soil index)
        h->index_name = "fast_index";
        attach_ec = h->api->attach_soil_index(
            (int)dim, "dense", fluffy::DistanceFunctionType::Euclidean,
            h->fast_shrink_rate, h->index_name, h->fast_max_samples,
            (h->index_threads > 0 ? h->index_threads : 1));
      } else {
        attach_ec = h->api->attach_index(
            (int)dim, "dense", fluffy::DistanceFunctionType::Euclidean,
            h->index_name,
            (h->index_threads > 0 ? h->index_threads : 1));
      }
      if (attach_ec != fluffy::ErrorCode::Success) {
        vlog(std::string("add: attach index failed ec=") +
             std::to_string((int)attach_ec));
        // continue: add_data_batch may create index implicitly, but we tried
        // to make behavior explicit for correct metric/dim.
      } else {
        vlog(std::string("add: attached index '") + h->index_name +
             "' with dim=" + std::to_string(dim));
      }
    }
    // Prepare batch of (string_id, unique_ptr<Vector>) as the SDK expects
    vlog("add: building vectors batch...");
    std::vector<std::pair<std::string, std::unique_ptr<fluffy::Vector>>> batch;
    batch.reserve(n);
    for (int i = 0; i < n; ++i) {
      std::vector<float> embedding;
      embedding.assign(data + (size_t)i * dim, data + (size_t)i * dim + dim);
      std::unique_ptr<fluffy::Vector> vec;
      fluffy::ErrorCode ec = h->api->build_vector_dense(embedding, vec);
      if (ec != fluffy::ErrorCode::Success || !vec) {
        vlog(std::string("add: build_vector_dense failed at ") +
             std::to_string(i));
        return -2;
      }
      long id = ids ? ids[i] : i;
      std::string sid = std::string("id_") + std::to_string(id);
      // Avoid setting extra attributes that may require external lifetime
      // management. The string_id already encodes the numeric id and is used
      // to reconstruct ids during search results mapping.
      batch.emplace_back(sid, std::move(vec));
    }
    vlog("add: build vectors batch done, calling add_data_batch...");
    std::vector<fluffy::ErrorCode> ecs = h->api->add_data_batch(
        batch,
        /*threads=*/(h->index_threads > 0 ? h->index_threads : 1));
    vlog(std::string("add: add_data_batch done, items=") +
         std::to_string((int)batch.size()));
    // check results
    for (const auto &ec : ecs) {
      if (ec != fluffy::ErrorCode::Success) {
        vlog(std::string("add: add_data_batch returned error ec=") +
             std::to_string((int)ec));
        // continue but report failure
      }
    }
    // Flush to ensure data is persisted/visible for subsequent searches
    fluffy::ErrorCode flush_ec = h->api->flush();
    if (flush_ec != fluffy::ErrorCode::Success) {
      vlog(std::string("add: flush failed ec=") +
           std::to_string((int)flush_ec));
    } else {
      vlog("add: flush successful");
    }
    vlog("add: end");

    return 0;
  } catch (const std::exception &e) {
    vlog(std::string("add: exception: ") + e.what());
    return -2;
  }
}

int vecml_search(vecml_ctx_t ctx, const float *queries, int nq, int dim, int k,
                 long *out_ids) {
  if (!ctx)
    return -1;
  VecMLHandle *h = reinterpret_cast<VecMLHandle *>(ctx);
  try {
    vlog(std::string("search: start nq=") + std::to_string(nq) +
         ", dim=" + std::to_string(dim) + ", k=" + std::to_string(k) +
         ", index='" + h->index_name + "'");
    // Build query vectors and Query objects
    std::vector<fluffy::Query> queries_vec;
    std::vector<std::unique_ptr<fluffy::Vector>>
        qvecs_hold; // keep ownership alive
    queries_vec.reserve(nq);
    qvecs_hold.reserve(nq);
    for (int i = 0; i < nq; ++i) {
      std::vector<float> embedding;
      embedding.assign(queries + (size_t)i * dim,
                       queries + (size_t)i * dim + dim);
      std::unique_ptr<fluffy::Vector> vec;
      fluffy::ErrorCode ec = h->api->build_vector_dense(embedding, vec);
      if (ec != fluffy::ErrorCode::Success || !vec) {
        vlog(std::string("search: build_vector_dense failed for query ") +
             std::to_string(i));
        return -2;
      }
      fluffy::Query q;
      q.top_k = k;
      q.vector = vec.get();
      // Explicitly request Euclidean (L2) similarity so results align with
      // the Faiss L2 baseline used by the benchmark.
      q.similarity_measure = fluffy::DistanceFunctionType::Euclidean;
      // default similarity_measure will be used
      queries_vec.push_back(q);
      qvecs_hold.push_back(std::move(vec));
    }

    // Use the same index name attached during init (fallback to "test_index")
    const std::string idx =
        h->index_name.empty() ? std::string("test_index") : h->index_name;

    // Perform single searches for each query and marshal results
    for (int qi = 0; qi < nq; ++qi) {
      fluffy::InterfaceQueryResults qr;
      fluffy::ErrorCode sec =
          h->api->search(queries_vec[qi], qr, idx, 0.3f, 1.0f);
      if (sec != fluffy::ErrorCode::Success) {
        vlog(std::string("search: search() failed for query ") +
             std::to_string(qi) + ", ec=" + std::to_string((int)sec));
        // mark no results for this query
        for (int t = 0; t < k; ++t)
          out_ids[(size_t)qi * k + t] = -1;
        continue;
      }
      size_t found = 0;
      for (size_t j = 0; j < qr.results.size() && found < (size_t)k; ++j) {
        const std::string &sid = qr.results[j].string_id;
        long id = -1;
        size_t p = sid.find_last_of('_');
        if (p != std::string::npos) {
          try {
            id = std::stol(sid.substr(p + 1));
          } catch (...) {
            id = -1;
          }
        }
        out_ids[(size_t)qi * k + found] = id;
        ++found;
      }
      for (size_t t = found; t < (size_t)k; ++t)
        out_ids[(size_t)qi * k + t] = -1;
    }
    vlog("search: end");
    return 0;
  } catch (const std::exception &e) {
    vlog(std::string("search: exception: ") + e.what());
    return -3;
  }
}

void vecml_destroy(vecml_ctx_t ctx) {
  if (!ctx)
    return;
  VecMLHandle *h = reinterpret_cast<VecMLHandle *>(ctx);
  // Intentionally avoid resetting/destroying the underlying SDK instance here
  // to minimize the risk of destructor-related crashes in some environments.
  // The process will clean up remaining instances on exit.
  delete h;
}

} // extern C

extern "C" {

void vecml_set_threads(vecml_ctx_t ctx, int threads) {
  if (!ctx)
    return;
  VecMLHandle *h = reinterpret_cast<VecMLHandle *>(ctx);
  if (threads <= 0)
    threads = 1;
  h->index_threads = threads;
  vlog(std::string("set_threads: ") + std::to_string(threads));
}

double vecml_get_disk_mb(vecml_ctx_t ctx) {
  if (!ctx)
    return -1.0;
  VecMLHandle *h = reinterpret_cast<VecMLHandle *>(ctx);
  try {
    if (h->base_path.empty())
      return -1.0;
    std::uintmax_t total = 0;
    std::error_code ec;
    for (auto it = std::filesystem::recursive_directory_iterator(
             h->base_path,
             std::filesystem::directory_options::skip_permission_denied, ec);
         it != std::filesystem::recursive_directory_iterator();
         it.increment(ec)) {
      if (ec)
        continue;
      const auto &entry = *it;
      if (entry.is_regular_file(ec)) {
        std::error_code fec;
        auto sz = std::filesystem::file_size(entry.path(), fec);
        if (!fec)
          total += sz;
      }
    }
    double mb = static_cast<double>(total) / (1024.0 * 1024.0);
    return mb;
  } catch (...) {
    return -1.0;
  }
}

} // extern C

extern "C" {

int vecml_enable_fast_index(vecml_ctx_t ctx, float shrink_rate,
                            int max_num_samples, int num_threads) {
  if (!ctx)
    return -1;
  VecMLHandle *h = reinterpret_cast<VecMLHandle *>(ctx);
  if (shrink_rate <= 0.0f || shrink_rate > 1.0f)
    shrink_rate = 0.4f;
  if (max_num_samples <= 0)
    max_num_samples = 100000;
  if (num_threads <= 0)
    num_threads = 1;

  h->use_fast_index = true;
  h->fast_shrink_rate = shrink_rate;
  h->fast_max_samples = max_num_samples;
  h->index_threads = num_threads;
  vlog(std::string("enable_fast_index: shrink=") + std::to_string(shrink_rate) +
       ", max_samples=" + std::to_string(max_num_samples) +
       ", threads=" + std::to_string(num_threads));
  return 0;
}

} // extern C

#include "../include/vector_bench/cli.h"

#include "../include/vector_bench/benchmark_config.h"

#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace vecbench {

namespace {

std::string valueOrThrow(int& i, int argc, char** argv, const std::string& flag) {
  if (i + 1 >= argc) {
    throw std::runtime_error("Missing value for " + flag);
  }
  return argv[++i];
}

AlgorithmSpec makeAlgorithmFromLegacy(const std::string& name) {
  AlgorithmSpec spec;
  spec.library = "faiss";
  spec.name = name;
  if (name == "hnsw_sq4") {
    spec.name = "hnsw_sq";
    spec.params["bits"] = "4";
  } else if (name == "hnsw_sq8") {
    spec.name = "hnsw_sq";
    spec.params["bits"] = "8";
  } else if (name == "ivf_sq4") {
    spec.name = "ivf_sq";
    spec.params["bits"] = "4";
  } else if (name == "ivf_sq8") {
    spec.name = "ivf_sq";
    spec.params["bits"] = "8";
  } else if (name == "rbq_refine" || name == "ivf_rbq_refine") {
    spec.name = "ivf_rbq_refine";
  }
  return spec;
}

} // namespace

BenchmarkConfig parseCommandLine(int argc, char** argv) {
  BenchmarkConfig config;

  std::vector<std::string> legacyWhich;
  AlgorithmSpec* current_algorithm = nullptr;

  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    if (arg == "--help" || arg == "-h") {
      printHelp(argv[0]);
      std::exit(0);
    } else if (arg == "--dim") {
      config.dataset.dim = std::stoi(valueOrThrow(i, argc, argv, arg));
    } else if (arg == "--nb") {
      config.dataset.nb = std::stoi(valueOrThrow(i, argc, argv, arg));
    } else if (arg == "--nq") {
      config.dataset.nq = std::stoi(valueOrThrow(i, argc, argv, arg));
    } else if (arg == "--k") {
      config.dataset.k = std::stoi(valueOrThrow(i, argc, argv, arg));
    } else if (arg == "--seed") {
      config.dataset.seed = static_cast<unsigned int>(std::stoul(valueOrThrow(i, argc, argv, arg)));
    } else if (arg == "--no-normalize") {
      config.dataset.normalize = false;
    } else if (arg == "--normalize") {
      config.dataset.normalize = true;
    } else if (arg == "--save-data-dir") {
      config.dataset.save_data_dir = valueOrThrow(i, argc, argv, arg);
    } else if (arg == "--load-data-dir") {
      config.dataset.load_data_dir = valueOrThrow(i, argc, argv, arg);
    } else if (arg == "--no-sequential") {
      config.search.run_sequential = false;
    } else if (arg == "--no-concurrent") {
      config.search.run_concurrent = false;
    } else if (arg == "--concurrency") {
      config.search.concurrency = static_cast<std::size_t>(std::stoul(valueOrThrow(i, argc, argv, arg)));
    } else if (arg == "--verify-concurrent") {
      config.search.verify_concurrent = true;
    } else if (arg == "--out-csv") {
      config.output.csv_path = valueOrThrow(i, argc, argv, arg);
    } else if (arg == "--no-header") {
      config.output.include_header = false;
    } else if (arg == "--no-pretty") {
      config.output.pretty_print = false;
    } else if (arg == "--algorithm") {
      std::string payload = valueOrThrow(i, argc, argv, arg);
      auto pos = payload.find(':');
      AlgorithmSpec spec;
      if (pos == std::string::npos) {
        spec.library = "faiss";
        spec.name = payload;
      } else {
        spec.library = payload.substr(0, pos);
        spec.name = payload.substr(pos + 1);
      }
      config.algorithms.push_back(spec);
      current_algorithm = &config.algorithms.back();
    } else if (arg == "--param") {
      if (!current_algorithm) {
        throw std::runtime_error("--param must follow an --algorithm declaration");
      }
      std::string payload = valueOrThrow(i, argc, argv, arg);
      auto pos = payload.find('=');
      if (pos == std::string::npos) {
        throw std::runtime_error("--param expects key=value format");
      }
      auto key = payload.substr(0, pos);
      auto value = payload.substr(pos + 1);
      current_algorithm->params[key] = value;
    } else if (arg == "--which") {
      std::string payload = valueOrThrow(i, argc, argv, arg);
      std::stringstream ss(payload);
      std::string item;
      while (std::getline(ss, item, ',')) {
        if (!item.empty()) {
          legacyWhich.push_back(item);
        }
      }
    } else {
      std::ostringstream oss;
      oss << "Unknown flag: " << arg;
      throw std::runtime_error(oss.str());
    }
  }

  if (!legacyWhich.empty() && config.algorithms.empty()) {
    for (const auto& name : legacyWhich) {
      auto spec = makeAlgorithmFromLegacy(name);
      if (spec.name == "all") {
        continue;
      }
      config.algorithms.push_back(std::move(spec));
    }
  }

  if (config.algorithms.empty()) {
    AlgorithmSpec spec;
    spec.library = "faiss";
    spec.name = "hnsw_flat";
    config.algorithms.push_back(spec);
  }

  if (config.search.concurrency == 0) {
    config.search.concurrency = std::max<std::size_t>(1, std::thread::hardware_concurrency());
  }

  return config;
}

void printHelp(const std::string& binary_name) {
  std::cout << "Usage: " << binary_name << " [options]\n\n"
            << "Dataset options:\n"
            << "  --dim INT              Vector dimension\n"
            << "  --nb INT               Database vector count\n"
            << "  --nq INT               Query vector count\n"
            << "  --k INT                Top-k for search & recall\n"
            << "  --seed UINT            Random seed for synthetic data\n"
            << "  --normalize/--no-normalize  Enable or disable L2 normalization (default on)\n"
            << "  --save-data-dir PATH   Save generated dataset to directory\n"
            << "  --load-data-dir PATH   Load dataset from directory if available\n\n"
            << "Search options:\n"
            << "  --no-sequential        Skip sequential search measurement\n"
            << "  --no-concurrent        Skip concurrent search measurement\n"
            << "  --concurrency INT      Number of worker threads for concurrent search (default: HW concurrency)\n"
            << "  --verify-concurrent    Compare concurrent results against sequential baseline\n\n"
            << "Output options:\n"
            << "  --out-csv PATH         Output CSV path (default vecbench_results.csv)\n"
            << "  --no-header            Omit CSV header\n"
            << "  --no-pretty            Skip console summary\n\n"
            << "Algorithm selection:\n"
            << "  --algorithm LIB:NAME   Register an algorithm (e.g. faiss:hnsw_flat)\n"
            << "  --param KEY=VALUE      Set parameter for the most recent algorithm\n"
            << "  --which LIST           Legacy alias (comma separated) for FAISS presets\n\n"
            << "Examples:\n"
            << "  " << binary_name << " --dim 256 --nb 100000 --nq 1000 --algorithm faiss:hnsw_flat --param hnsw_m=32 --param ef_search=80\n"
            << "  " << binary_name << " --algorithm faiss:ivf_pq --param nlist=1024 --param m=16 --param nbits=8\n";
}

} // namespace vecbench

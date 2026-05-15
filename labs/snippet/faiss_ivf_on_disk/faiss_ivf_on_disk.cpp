// Faiss IVF OnDisk demo:
// 1) train IVF index
// 2) move inverted lists to disk (OnDiskInvertedLists)
// 3) add vectors and search
// 4) persist and reload index

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <algorithm>
#include <filesystem>
#include <iostream>
#include <memory>
#include <numeric>
#include <random>
#include <string>
#include <vector>

#include <faiss/IndexFlat.h>
#include <faiss/IndexIVFFlat.h>
#include <faiss/index_io.h>
#include <faiss/invlists/OnDiskInvertedLists.h>

namespace {

void log_step(const std::string& title) {
	std::cout << "\n========== " << title << " ==========" << '\n';
}

void fill_random(std::vector<float>& x, uint32_t seed) {
	std::mt19937 rng(seed);
	std::uniform_real_distribution<float> dis(0.0f, 1.0f);
	for (auto& v : x) {
		v = dis(rng);
	}
}

void print_ivf_list_stats(const faiss::IndexIVF& index) {
	std::vector<size_t> sizes(index.nlist);
	for (size_t i = 0; i < index.nlist; ++i) {
		sizes[i] = index.invlists->list_size(i);
	}

	size_t min_size = *std::min_element(sizes.begin(), sizes.end());
	size_t max_size = *std::max_element(sizes.begin(), sizes.end());
	double avg = static_cast<double>(std::accumulate(sizes.begin(), sizes.end(), size_t(0))) /
				 static_cast<double>(sizes.size());

	std::cout << "[IVF stats] nlist=" << index.nlist
			  << ", nprobe=" << index.nprobe
			  << ", code_size=" << index.code_size
			  << ", ntotal=" << index.ntotal << '\n';
	std::cout << "[IVF stats] list_size min/avg/max = "
			  << min_size << " / " << avg << " / " << max_size << '\n';
}

void print_result(
		const std::vector<float>& D,
		const std::vector<faiss::idx_t>& I,
		int nq,
		int k) {
	for (int qi = 0; qi < nq; ++qi) {
		std::cout << "query " << qi << ": ";
		for (int j = 0; j < k; ++j) {
			int pos = qi * k + j;
			std::cout << "(" << I[pos] << ", " << D[pos] << ") ";
		}
		std::cout << '\n';
	}
}

} // namespace

int main() {
	try {
		constexpr int d = 64;      // 向量维度
		constexpr int nb = 20000;  // 数据库向量数量
		constexpr int nq = 5;      // 查询数量
		constexpr int nlist = 128; // IVF 倒排桶数量
		constexpr int k = 5;       // top-k

		log_step("0) 参数与路径");
		std::cout << "d=" << d << ", nb=" << nb << ", nq=" << nq
				  << ", nlist=" << nlist << ", k=" << k << '\n';

		const std::string data_dir = "/mnt/disk4/hezhiqiang/workspace/ivf-ondisk-data";
		std::filesystem::create_directories(data_dir);

		const std::string invlists_path = data_dir + "/faiss_ivf_ondisk_demo.ivfdata";
		const std::string index_path = data_dir + "/faiss_ivf_ondisk_demo.index";

		// 清理历史文件（忽略失败）
		std::remove(invlists_path.c_str());
		std::remove(index_path.c_str());
		std::cout << "data_dir=" << data_dir << '\n';
		std::cout << "invlists_path=" << invlists_path << '\n';
		std::cout << "index_path=" << index_path << '\n';

		log_step("1) 准备随机数据");
		std::vector<float> xb(nb * d);
		std::vector<float> xq(nq * d);
		fill_random(xb, 42);
		fill_random(xq, 123);
		std::cout << "generated xb/xq with fixed seeds (42/123), reproducible demo" << '\n';

		// IVF 量化器
		log_step("2) 构建 IVF 索引");
		auto quantizer = std::make_unique<faiss::IndexFlatL2>(d);
		auto index = std::make_unique<faiss::IndexIVFFlat>(
				quantizer.get(), d, nlist, faiss::METRIC_L2);
		std::cout << "quantizer=IndexFlatL2, index=IndexIVFFlat(metric=L2)" << '\n';

		// 训练 IVF（需要先 train 再 add）
		log_step("3) 训练粗量化器");
		index->train(nb, xb.data());
		if (!index->is_trained) {
			std::cerr << "index training failed\n";
			return 1;
		}
		std::cout << "train done, is_trained=true" << '\n';

		// 把倒排表放到磁盘文件中
		log_step("4) 切换倒排表到 OnDisk");
		auto* ondisk_invlists = new faiss::OnDiskInvertedLists(
				index->nlist, index->code_size, invlists_path.c_str());
		index->replace_invlists(ondisk_invlists, true);
		std::cout << "replace_invlists done, postings will be written to mmap file" << '\n';

		// 可选参数：查询时访问更多桶以提高召回
		index->nprobe = 16;
		std::cout << "nprobe set to " << index->nprobe << '\n';

		// 添加数据
		log_step("5) add 向量到倒排表");
		index->add(nb, xb.data());
		std::cout << "added vectors: " << index->ntotal << '\n';
		print_ivf_list_stats(*index);

		// 搜索
		log_step("6) 首次 search");
		std::vector<float> D(nq * k);
		std::vector<faiss::idx_t> I(nq * k);
		index->search(nq, xq.data(), k, D.data(), I.data());

		std::cout << "search result before save:\n";
		print_result(D, I, nq, k);

		// 保存并加载
		log_step("7) 保存并重载索引");
		faiss::write_index(index.get(), index_path.c_str());
		std::cout << "write_index done" << '\n';
		std::unique_ptr<faiss::Index> loaded(faiss::read_index(index_path.c_str()));
		std::cout << "read_index done" << '\n';

		auto* loaded_ivf = dynamic_cast<faiss::IndexIVF*>(loaded.get());
		if (!loaded_ivf) {
			std::cerr << "loaded index is not IVF\n";
			return 1;
		}
		loaded_ivf->nprobe = 16;
		print_ivf_list_stats(*loaded_ivf);

		std::vector<float> D2(nq * k);
		std::vector<faiss::idx_t> I2(nq * k);
		log_step("8) 重载后 search");
		loaded->search(nq, xq.data(), k, D2.data(), I2.data());

		std::cout << "\nsearch result after reload:\n";
		print_result(D2, I2, nq, k);

		// 简单一致性检查
		log_step("9) 一致性检查");
		size_t diff = 0;
		for (size_t i = 0; i < I.size(); ++i) {
			if (I[i] != I2[i] || std::fabs(D[i] - D2[i]) > 1e-6f) {
				++diff;
			}
		}
		std::cout << "\nconsistency diff count: " << diff << '\n';
		std::cout << "ondisk invlists file: " << invlists_path << '\n';
		std::cout << "index file: " << index_path << '\n';

		return 0;
	} catch (const std::exception& e) {
		std::cerr << "exception: " << e.what() << '\n';
		return 1;
	}
}

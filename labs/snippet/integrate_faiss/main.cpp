#include "faiss/IndexHNSW.h"
#include "faiss/MetricType.h"
#include "faiss/impl/AuxIndexStructures.h"
#include <faiss/IndexFlat.h>
#include <faiss/IndexIVFFlat.h>
#include <faiss/index_io.h>
#include <faiss/invlists/OnDiskInvertedLists.h>
#include <iostream>
#include <string>
#include <vector>
#include <sys/stat.h>
#include <unistd.h>

static std::string make_tmp_path_in_dir(const std::string& dir, const char* prefix) {
    std::string path = dir + "/" + prefix + "XXXXXX";
    std::vector<char> buf(path.begin(), path.end());
    buf.push_back('\0');
    int fd = mkstemp(buf.data());
    if (fd != -1) {
        close(fd);
    }
    return std::string(buf.data());
}

int main() {
    // Test faiss index merge
    int dim = 4;  // 4-dimensional vectors
    
    // Create first index
    faiss::IndexHNSWFlat index1(dim, 16, faiss::METRIC_L2);
    
    // Add vectors to first index
    std::vector<float> vectors1 = {
        1.0, 2.0, 3.0, 4.0,    // vector 0
        5.0, 6.0, 7.0, 8.0,    // vector 1
        9.0, 10.0, 11.0, 12.0  // vector 2
    };
    index1.add(3, vectors1.data());
    
    // Create second index
    faiss::IndexHNSWFlat index2(dim, 16, faiss::METRIC_L2);
    
    // Add vectors to second index
    std::vector<float> vectors2 = {
        13.0, 14.0, 15.0, 16.0,  // vector 0
        17.0, 18.0, 19.0, 20.0,  // vector 1
        21.0, 22.0, 23.0, 24.0   // vector 2
    };
    index2.add(3, vectors2.data());
    
    std::cout << "Before merge:" << std::endl;
    std::cout << "Index1 size: " << index1.ntotal << std::endl;
    std::cout << "Index2 size: " << index2.ntotal << std::endl;
    
    // Merge index2 into index1
    try {
        index1.merge_from(index2, 0);  // 0 means add new IDs starting from index1.ntotal
    } catch (faiss::FaissException& e) {
        std::cerr << "Error during merge: " << e.what() << std::endl;
    }
    
    
    std::cout << "\nAfter merge:" << std::endl;
    std::cout << "Index1 size: " << index1.ntotal << std::endl;
    
    // Test search on merged index
    std::vector<float> query = {1.5, 2.5, 3.5, 4.5};
    int k = 5;
    std::vector<float> distances(k);
    std::vector<faiss::idx_t> labels(k);
    
    index1.search(1, query.data(), k, distances.data(), labels.data());
    
    std::cout << "\nSearch results on merged index:" << std::endl;
    std::cout << "Query: [" << query[0] << ", " << query[1] << ", " << query[2] << ", " << query[3] << "]" << std::endl;
    for (int i = 0; i < k && labels[i] != -1; i++) {
        std::cout << "Label: " << labels[i] << ", Distance: " << distances[i] << std::endl;
    }
    
    // Alternative: Test with IndexFlat for simpler merge verification
    std::cout << "\n--- Testing with IndexFlat ---" << std::endl;
    
    faiss::IndexFlat flat_index1(dim, faiss::METRIC_L2);
    faiss::IndexFlat flat_index2(dim, faiss::METRIC_L2);
    
    flat_index1.add(3, vectors1.data());
    flat_index2.add(3, vectors2.data());
    
    std::cout << "Before merge - Flat Index1 size: " << flat_index1.ntotal << std::endl;
    std::cout << "Before merge - Flat Index2 size: " << flat_index2.ntotal << std::endl;
    
    // Merge flat indices
    flat_index1.merge_from(flat_index2, 0);
    
    std::cout << "After merge - Flat Index1 size: " << flat_index1.ntotal << std::endl;
    
    // Search on merged flat index
    flat_index1.search(1, query.data(), k, distances.data(), labels.data());
    
    std::cout << "\nSearch results on merged flat index:" << std::endl;
    for (int i = 0; i < k && labels[i] != -1; i++) {
        std::cout << "Label: " << labels[i] << ", Distance: " << distances[i] << std::endl;
    }

    // Test OnDiskIVF (IndexIVFFlat with OnDiskInvertedLists)
    std::cout << "\n--- Testing OnDiskIVF ---" << std::endl;
    std::vector<float> all_vectors = vectors1;
    all_vectors.insert(all_vectors.end(), vectors2.begin(), vectors2.end());

    int nlist = 2;
    faiss::IndexFlatL2 quantizer(dim);
    faiss::IndexIVFFlat ivf_index(&quantizer, dim, nlist, faiss::METRIC_L2);

    // Provide more training data to avoid clustering warnings.
    int ntrain = 100;
    std::vector<float> train_vectors(ntrain * dim);
    for (int i = 0; i < ntrain; ++i) {
        for (int d = 0; d < dim; ++d) {
            train_vectors[i * dim + d] = static_cast<float>(i * 0.1 + d);
        }
    }
    ivf_index.train(ntrain, train_vectors.data());

    std::string ondisk_dir = "../ondisk_test";
    ::mkdir(ondisk_dir.c_str(), 0755);
    std::string invlists_path = make_tmp_path_in_dir(ondisk_dir, "faiss_invlists_");
    faiss::OnDiskInvertedLists ondisk(ivf_index.nlist, ivf_index.code_size, invlists_path.c_str());
    ivf_index.replace_invlists(&ondisk);
    ivf_index.add(6, all_vectors.data());
    ivf_index.nprobe = nlist;

    std::cout << "OnDiskIVF size: " << ivf_index.ntotal << std::endl;
    std::string index_path = make_tmp_path_in_dir(ondisk_dir, "faiss_index_");
    faiss::write_index(&ivf_index, index_path.c_str());

    faiss::Index* loaded = faiss::read_index(index_path.c_str());
    if (auto* ivf_loaded = dynamic_cast<faiss::IndexIVF*>(loaded)) {
        ivf_loaded->nprobe = nlist;
    }
    loaded->search(1, query.data(), k, distances.data(), labels.data());

    std::cout << "Search results on OnDiskIVF (after reload):" << std::endl;
    for (int i = 0; i < k && labels[i] != -1; i++) {
        std::cout << "Label: " << labels[i] << ", Distance: " << distances[i] << std::endl;
    }

    // Keep on-disk files for inspection.
    delete loaded;
    
    return 0;
}

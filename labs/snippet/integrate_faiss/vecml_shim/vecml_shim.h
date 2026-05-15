// C shim for VecML (Fluffy) to avoid C++ ABI conflicts.
#pragma once

#include <cstddef>

extern "C" {

// Opaque context for VecML instance
typedef void* vecml_ctx_t;

// Create and return a VecML context. Returns nullptr on error.
vecml_ctx_t vecml_create(const char* base_path, const char* license_path, bool fast_index);

// Add data: `data` is n * dim floats, `ids` is array of n int64 ids (can be nullptr to use 0..n-1).
// Returns 0 on success, non-zero on error.
int vecml_add_data(vecml_ctx_t ctx, const float* data, int n, int dim, const long* ids);

// Search: queries is nq * dim floats; out_ids must be preallocated with size nq * k
// and will be filled with long ids (or -1 for missing). Returns 0 on success.
int vecml_search(vecml_ctx_t ctx, const float* queries, int nq, int dim, int k, long* out_ids);

// Destroy context
void vecml_destroy(vecml_ctx_t ctx);

// Return disk usage (megabytes) under the VecML base path used to create the context.
// Returns a non-negative double on success, or -1.0 on error.
double vecml_get_disk_mb(vecml_ctx_t ctx);

// Enable building and searching a Fast Index (aka soil index) for the current context.
// Must be called before adding data. Returns 0 on success, non-zero on error.
// Parameters:
// - shrink_rate: in (0,1], larger for slightly higher recall but slower indexing. Default 0.4 is recommended.
// - max_num_samples: approximate number of total vectors; affects internal tuning. E.g., set to nb if known.
int vecml_enable_fast_index(vecml_ctx_t ctx, float shrink_rate, int max_num_samples, int num_threads);

// Set number of threads used by VecML operations in this context (index build,
// add_data, and fast-index attach). If threads <= 0, implementation will clamp
// to 1. Default is 16.
void vecml_set_threads(vecml_ctx_t ctx, int threads);

} // extern C

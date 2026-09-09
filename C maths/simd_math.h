#ifndef SIMD_MATH_H
#define SIMD_MATH_H

#ifdef __cplusplus
extern "C" {
#endif

// Vector similarity and dot product
float c_dot_product(const float* a, const float* b, int dimension);
float c_cosine_similarity(const float* a, const float* b, int dimension);

// Batch search (find top K)
void c_batch_vector_search(const float* query, const float* database, int num_vectors, int dimension, int* out_indices, float* out_scores, int top_k);

#ifdef __cplusplus
}
#endif

#endif // SIMD_MATH_H

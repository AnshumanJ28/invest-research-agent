#include "simd_math.h"
#include <math.h>

#if defined(__AVX2__)
#include <immintrin.h>
#endif

float c_dot_product(const float* a, const float* b, int dimension) {
    float result = 0.0f;
    int i = 0;

#if defined(__AVX2__)
    __m256 sum = _mm256_setzero_ps();
    int simd_limit = dimension - (dimension % 8);
    for (; i < simd_limit; i += 8) {
        __m256 va = _mm256_loadu_ps(&a[i]);
        __m256 vb = _mm256_loadu_ps(&b[i]);
        // sum = sum + (va * vb)
        sum = _mm256_fmadd_ps(va, vb, sum);
    }
    // Horizontal add
    float temp[8];
    _mm256_storeu_ps(temp, sum);
    result = temp[0] + temp[1] + temp[2] + temp[3] + temp[4] + temp[5] + temp[6] + temp[7];
#endif

    // Fallback for remaining elements or non-AVX2
    for (; i < dimension; ++i) {
        result += a[i] * b[i];
    }

    return result;
}

float c_cosine_similarity(const float* a, const float* b, int dimension) {
    float dot = 0.0f;
    float normA = 0.0f;
    float normB = 0.0f;
    int i = 0;

#if defined(__AVX2__)
    __m256 sum_dot = _mm256_setzero_ps();
    __m256 sum_nA = _mm256_setzero_ps();
    __m256 sum_nB = _mm256_setzero_ps();
    int simd_limit = dimension - (dimension % 8);
    
    for (; i < simd_limit; i += 8) {
        __m256 va = _mm256_loadu_ps(&a[i]);
        __m256 vb = _mm256_loadu_ps(&b[i]);
        sum_dot = _mm256_fmadd_ps(va, vb, sum_dot);
        sum_nA = _mm256_fmadd_ps(va, va, sum_nA);
        sum_nB = _mm256_fmadd_ps(vb, vb, sum_nB);
    }
    
    float temp_dot[8], temp_nA[8], temp_nB[8];
    _mm256_storeu_ps(temp_dot, sum_dot);
    _mm256_storeu_ps(temp_nA, sum_nA);
    _mm256_storeu_ps(temp_nB, sum_nB);
    
    for(int j=0; j<8; ++j) {
        dot += temp_dot[j];
        normA += temp_nA[j];
        normB += temp_nB[j];
    }
#endif

    for (; i < dimension; ++i) {
        dot += a[i] * b[i];
        normA += a[i] * a[i];
        normB += b[i] * b[i];
    }

    if (normA == 0.0f || normB == 0.0f) return 0.0f;
    return dot / (sqrtf(normA) * sqrtf(normB));
}

void c_batch_vector_search(const float* query, const float* database, int num_vectors, int dimension, int* out_indices, float* out_scores, int top_k) {
    // Initialize output arrays
    for (int i = 0; i < top_k; i++) {
        out_indices[i] = -1;
        out_scores[i] = -1e9f;
    }

    for (int i = 0; i < num_vectors; i++) {
        const float* db_vec = &database[i * dimension];
        // Faiss generally uses dot product for L2 normalized vectors or cosine
        // We will use cosine similarity here
        float score = c_cosine_similarity(query, db_vec, dimension);
        
        // Simple insertion sort to keep top_k
        if (score > out_scores[top_k - 1]) {
            int j = top_k - 1;
            while (j > 0 && score > out_scores[j - 1]) {
                out_scores[j] = out_scores[j - 1];
                out_indices[j] = out_indices[j - 1];
                j--;
            }
            out_scores[j] = score;
            out_indices[j] = i;
        }
    }
}

#ifndef FAST_RATIOS_H
#define FAST_RATIOS_H

#ifdef __cplusplus
extern "C" {
#endif

#include <math.h>

typedef struct {
    double revenue;
    double net_income;
    double operating_income;
    double ebit;
    double gross_profit;
    double operating_expenses;
    double total_assets;
    double total_equity;
    double current_assets;
    double current_liabilities;
    double total_liabilities;
    double retained_earnings;
    double market_cap;
    double total_debt;
    double long_term_debt;
    double short_term_debt;
} FinancialInputs;

// Core fallbacks
void apply_financial_fallbacks(FinancialInputs* inputs);

// Existing fast ratios
double calculate_roe(const FinancialInputs* inputs);
double calculate_roa(const FinancialInputs* inputs);
double calculate_altman_z(const FinancialInputs* inputs);
double calculate_current_ratio(const FinancialInputs* inputs);

// Peer & Composite Math
double calculate_peer_premium_discount(double target_val, double peer_val);
double calculate_composite_score(double health_score, double val_score, double sent_score, double risk_score, double peer_score);
void get_conviction_label(double composite_score, char* label_out);

#ifdef __cplusplus
}
#endif

#endif // FAST_RATIOS_H

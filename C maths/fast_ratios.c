#include "fast_ratios.h"
#include <string.h>

void apply_financial_fallbacks(FinancialInputs* inputs) {
    if (isnan(inputs->total_debt)) {
        if (!isnan(inputs->long_term_debt) || !isnan(inputs->short_term_debt)) {
            double ltd = isnan(inputs->long_term_debt) ? 0.0 : inputs->long_term_debt;
            double std = isnan(inputs->short_term_debt) ? 0.0 : inputs->short_term_debt;
            inputs->total_debt = ltd + std;
        }
    }
    if (isnan(inputs->operating_income)) {
        if (!isnan(inputs->ebit)) {
            inputs->operating_income = inputs->ebit;
        } else if (!isnan(inputs->gross_profit) && !isnan(inputs->operating_expenses)) {
            inputs->operating_income = inputs->gross_profit - inputs->operating_expenses;
        }
    }
    if (isnan(inputs->total_liabilities)) {
        if (!isnan(inputs->total_assets) && !isnan(inputs->total_equity)) {
            inputs->total_liabilities = inputs->total_assets - inputs->total_equity;
        }
    }
}

double calculate_roe(const FinancialInputs* inputs) {
    if (isnan(inputs->net_income) || isnan(inputs->total_equity) || inputs->total_equity == 0.0) return NAN;
    return inputs->net_income / inputs->total_equity;
}

double calculate_roa(const FinancialInputs* inputs) {
    if (isnan(inputs->net_income) || isnan(inputs->total_assets) || inputs->total_assets == 0.0) return NAN;
    return inputs->net_income / inputs->total_assets;
}

double calculate_altman_z(const FinancialInputs* inputs) {
    if (isnan(inputs->total_assets) || inputs->total_assets == 0.0) return NAN;
    
    double t1 = 0.0, t2 = 0.0, t3 = 0.0, t4 = 0.0, t5 = 0.0;
    
    if (!isnan(inputs->current_assets) && !isnan(inputs->current_liabilities)) {
        t1 = (inputs->current_assets - inputs->current_liabilities) / inputs->total_assets;
    } else return NAN;
    
    if (!isnan(inputs->retained_earnings)) t2 = inputs->retained_earnings / inputs->total_assets;
    else return NAN;
    
    if (!isnan(inputs->operating_income)) t3 = inputs->operating_income / inputs->total_assets;
    else return NAN;
    
    if (!isnan(inputs->total_liabilities) && inputs->total_liabilities > 0.0 && !isnan(inputs->market_cap)) {
        t4 = inputs->market_cap / inputs->total_liabilities;
    } else return NAN;
    
    if (!isnan(inputs->revenue)) t5 = inputs->revenue / inputs->total_assets;
    else return NAN;
    
    return 1.2 * t1 + 1.4 * t2 + 3.3 * t3 + 0.6 * t4 + 1.0 * t5;
}

double calculate_current_ratio(const FinancialInputs* inputs) {
    if (isnan(inputs->current_assets) || isnan(inputs->current_liabilities) || inputs->current_liabilities == 0.0) return NAN;
    return inputs->current_assets / inputs->current_liabilities;
}

double calculate_peer_premium_discount(double target_val, double peer_val) {
    if (isnan(target_val) || isnan(peer_val) || peer_val == 0.0) return NAN;
    return ((target_val - peer_val) / fabs(peer_val)) * 100.0;
}

double calculate_composite_score(double health_score, double val_score, double sent_score, double risk_score, double peer_score) {
    double composite = 0.30 * health_score + 0.25 * val_score + 0.20 * sent_score + 0.15 * risk_score + 0.10 * peer_score;
    if (composite < 1.0) composite = 1.0;
    if (composite > 10.0) composite = 10.0;
    return composite;
}

void get_conviction_label(double composite_score, char* label_out) {
    if (composite_score >= 7.5) strcpy(label_out, "STRONG BUY");
    else if (composite_score >= 6.5) strcpy(label_out, "BUY");
    else if (composite_score <= 3.5) strcpy(label_out, "STRONG SELL");
    else if (composite_score <= 4.5) strcpy(label_out, "SELL");
    else strcpy(label_out, "HOLD");
}


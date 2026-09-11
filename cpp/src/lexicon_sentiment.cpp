#include "lexicon_sentiment.h"
#include <algorithm>
#include <cctype>
#include <cmath>
#include <sstream>
double LexiconScore::net_score() const {
    int sentiment_words = positive_count + negative_count;
    if (sentiment_words == 0 || total_words == 0) return 0.0;
    double raw = static_cast<double>(positive_count - negative_count) / sentiment_words;
    double density = static_cast<double>(sentiment_words) / total_words;
    double density_boost = std::min(1.0, density * 5.0);
    double uncertainty_penalty = 1.0;
    if (total_words > 0) {
        double uncertainty_ratio = static_cast<double>(uncertainty_count) / total_words;
        uncertainty_penalty = std::max(0.5, 1.0 - uncertainty_ratio * 3.0);
    }
    double score = raw * density_boost * uncertainty_penalty;
    return std::max(-1.0, std::min(1.0, score));
}
std::string LexiconScore::label() const {
    double s = net_score();
    if (s > 0.10)  return "POSITIVE";
    if (s < -0.10) return "NEGATIVE";
    return "NEUTRAL";
}
double LexiconScore::confidence() const {
    int sentiment_words = positive_count + negative_count;
    if (sentiment_words == 0 || total_words == 0) return 0.0;
    double density = static_cast<double>(sentiment_words) / total_words;
    return std::min(1.0, density * 4.0);  
}
std::vector<std::string> LexiconSentiment::tokenize(const std::string& text) {
    std::vector<std::string> tokens;
    std::string word;
    for (char c : text) {
        if (std::isalpha(static_cast<unsigned char>(c)) || c == '\'') {
            word += static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        } else {
            if (!word.empty()) {
                tokens.push_back(word);
                word.clear();
            }
        }
    }
    if (!word.empty()) tokens.push_back(word);
    return tokens;
}
LexiconSentiment::LexiconSentiment() {
    negative_ = {
        "abandon", "abandoned", "abandonment", "abdicate", "abrupt", "abruptly",
        "abuse", "abuses", "abusive", "accident", "accidents", "accidental",
        "acquitted", "adulterate", "adulterated", "adulteration", "adversarial",
        "adverse", "adversely", "adversity", "allegation", "allegations", "allege",
        "alleged", "allegedly", "annulled", "anomalous", "anomaly",
        "arrears", "backdating", "bail", "bailout", "bankrupt", "bankruptcy",
        "blight", "breach", "breached", "breaches", "breakage", "breakdown",
        "bribe", "bribery", "burden", "burdensome",
        "calamity", "cancel", "cancellation", "cancelled", "catastrophe",
        "catastrophic", "ceased", "censure", "censured", "closing",
        "coerce", "coercion", "collapse", "collapsed", "collusion",
        "complain", "complaint", "complaints", "complicate", "complication",
        "compulsion", "concede", "concern", "concerns", "condemn",
        "confiscate", "confiscated", "confiscation", "conflict", "conflicts",
        "conspire", "contaminate", "contaminated", "contamination",
        "contempt", "contraction", "convict", "convicted", "conviction",
        "correction", "corrective", "costly", "counterclaim", "counterfeit",
        "crime", "criminal", "criminally", "crisis", "critical", "critically",
        "criticism", "criticize", "curtail", "curtailment",
        "damage", "damaged", "damages", "damaging", "danger", "dangerous",
        "deadlock", "deadweight", "debarment", "debarred", "deceptive",
        "decline", "declined", "declines", "declining", "defalcation",
        "default", "defaulted", "defaults", "defeat", "defect", "defective",
        "deficiency", "deficient", "deficit", "deficits", "defraud",
        "degradation", "delay", "delayed", "delays", "deleterious",
        "deliberate", "delist", "delisted", "delisting", "delinquency",
        "delinquent", "denial", "denied", "demotion", "deplete", "depleted",
        "depletion", "depreciation", "depress", "depressed", "depression",
        "deprivation", "derelict", "derogatory", "destabilize", "destroy",
        "destruction", "destructive", "detain", "detained", "deteriorate",
        "deteriorated", "deteriorating", "deterioration", "detract",
        "detriment", "detrimental", "devalue", "devaluation", "devastate",
        "deviation", "difficult", "difficulties", "difficulty", "diminish",
        "diminished", "disadvantage", "disadvantaged", "disadvantageous",
        "disagree", "disagreement", "disappoint", "disappointed", "disappointing",
        "disappointment", "disapproval", "disapprove", "disastrous",
        "disclaim", "disclaimer", "discontinue", "discontinued",
        "discrepancy", "discrimination", "dishonest", "dishonesty",
        "disincentive", "disinterested", "dismiss", "dismissal",
        "disparity", "displeasure", "dispose", "dispossess", "dispute",
        "disputed", "disputes", "disqualification", "disqualified",
        "disregard", "disrepair", "disrepute", "disrupt", "disrupted",
        "disruption", "disruptions", "disruptive", "dissatisfaction",
        "dissolution", "dissolve", "distort", "distortion", "distress",
        "distressed", "divert", "diverted", "divest", "divested",
        "divestiture", "doubt", "doubtful", "downgrade", "downgraded",
        "downsizing", "downturn", "downturns", "downward", "drag",
        "drop", "dropped", "drops", "drought", "duress",
        "embargoed", "embargo", "embezzle", "embezzlement", "encumber",
        "encumbered", "endanger", "endangered", "erode", "eroded",
        "erosion", "erratic", "error", "errors", "escalate", "escalation",
        "evade", "evasion", "evict", "eviction", "exacerbate",
        "exaggerate", "excessive", "excessively", "exclude", "exclusion",
        "exhaust", "exhausted", "exploit", "exploitation", "expose",
        "exposed", "exposure", "expropriate", "expropriation", "extort",
        "extortion",
        "fail", "failed", "failing", "fails", "failure", "failures",
        "fallout", "false", "falsely", "falsification", "falsified",
        "falsify", "fatality", "fault", "faulted", "faulty", "fear",
        "fears", "felony", "fine", "fined", "fines", "fire", "fired",
        "flood", "flaw", "flawed", "fluctuate", "fluctuation",
        "foreclosure", "forfeit", "forfeiture", "fraud", "fraudulent",
        "freeze", "freezing",
        "grievance", "gross", "guilt", "guilty", "hack", "hacked",
        "halt", "halted", "hamper", "hampered", "hardship", "harm",
        "harmful", "harshly", "hazard", "hazardous", "hinder",
        "hindrance", "hostile",
        "illegal", "illegally", "illicit", "illiquid", "illiquidity",
        "impair", "impaired", "impairment", "impairments", "impasse",
        "impede", "impediment", "imperil", "implicate", "implication",
        "impose", "imposed", "imposing", "impossibility", "improper",
        "improperly", "inability", "inaccuracy", "inaccurate",
        "inadequacy", "inadequate", "inadvertent", "inadvertently",
        "incapable", "incidence", "incident", "incompatible",
        "incompetence", "incomplete", "inconsistency", "inconsistent",
        "incorrect", "incorrectly", "indebtedness", "indictment",
        "ineffective", "inefficiency", "inefficient", "inequitable",
        "infeasible", "infringe", "infringement", "injunction",
        "injure", "injured", "injury", "insolvent", "instability",
        "insufficient", "insurrection", "interfere", "interference",
        "interrupt", "interruption", "inundate", "invalid", "invalidate",
        "investigate", "investigation", "involuntary", "irregularity",
        "irrecoverable", "irrecoverable",
        "jeopardize", "jeopardy",
        "kickback",
        "lack", "lacked", "lacking", "lapse", "lapsed", "late",
        "layoff", "layoffs", "legal", "legislate", "liability",
        "liquidate", "liquidated", "liquidation", "litigation",
        "lockout", "lose", "loses", "losing", "loss", "losses", "lost",
        "malfeasance", "malfunction", "malpractice", "manipulate",
        "manipulation", "misappropriate", "misappropriation",
        "misconduct", "mishandle", "misinform", "mislead", "misleading",
        "mismanage", "mismanagement", "misrepresent", "misrepresentation",
        "misstate", "misstatement", "mitigate",
        "moratorium", "neglect", "negligence", "negligent", "noncompetitive",
        "noncompliance", "nonpayment", "nonperformance",
        "obstruct", "obstruction", "offend", "offense", "omission",
        "onerous", "oppose", "opposition", "outage", "overburdened",
        "overcharged", "overdue", "overestimate", "overleveraged",
        "overrun", "overstatement", "overvalued",
        "panic", "penalize", "penalized", "penalty", "penalties",
        "peril", "perilous", "perjury", "perpetrate", "plagiarism",
        "plummet", "plummeted", "plunge", "plunged", "preclude",
        "prejudice", "premature", "pressure", "problematic",
        "prosecute", "prosecution", "protest", "protested",
        "provoke", "punish", "punished", "punitive", "purport",
        "racketeering", "recall", "recalled", "recession", "reckless",
        "recourse", "redress", "refuse", "refused", "rejection",
        "relinquish", "reluctance", "reluctant", "remedial",
        "repossess", "repossession", "reprimand", "repudiate",
        "rescind", "restatement", "restructure", "restructured",
        "restructuring", "retaliate", "retribution", "revoke",
        "revoked", "risk", "risked", "riskier", "risks", "risky",
        "runoff",
        "sabotage", "sacrifice", "sanction", "sanctioned", "scandal",
        "scrutiny", "seize", "seized", "seizure", "setback", "setbacks",
        "severe", "severely", "severity", "shortage", "shortages",
        "shortfall", "shrink", "shrinkage", "shutdown", "shutdowns",
        "skeptic", "skeptical", "slack", "slander", "slippage",
        "slowdown", "slump", "smuggle", "smuggling", "stagnant",
        "stagnation", "stalemate", "stigma", "stolen", "strain",
        "strained", "stress", "stressed", "strike", "strikes",
        "subpoena", "substandard", "sue", "sued", "suffer", "suffered",
        "suffering", "suspend", "suspended", "suspension", "suspicious",
        "taint", "tainted", "tamper", "terminate", "terminated",
        "termination", "theft", "threat", "threaten", "threatened",
        "threatening", "threats", "turmoil", "unable", "unacceptable",
        "unanticipated", "unauthorized", "uncertain", "uncertainties",
        "uncertainty", "uncover", "uncovered", "underestimate",
        "undermine", "undermined", "underperform", "underperformance",
        "underperformed", "underperforming", "underpayment", "understate",
        "understated", "understatement", "undervalue", "undervalued",
        "undesirable", "undisclosed", "undue", "unfavorable",
        "unfavorably", "unforeseen", "unfounded", "unlawful",
        "unpaid", "unprecedented", "unpredictable", "unproductive",
        "unprofitable", "unqualified", "unreasonable", "unrecoverable",
        "unresolved", "unsafe", "unsatisfactory", "unsound",
        "unstable", "unsuccessful", "unsupported", "untimely",
        "unwarranted", "upheaval", "usurp",
        "vandalism", "verdict", "violate", "violated", "violates",
        "violation", "violations", "volatile", "volatility", "vulnerable",
        "warn", "warned", "warning", "warnings", "waste", "wasted",
        "weak", "weaken", "weakened", "weakness", "weaknesses",
        "worsen", "worsened", "worsening", "worst", "worthless",
        "writedown", "writeoff", "wrongdoing", "wrongful"
    };
    positive_ = {
        "able", "abundance", "abundant", "accomplish", "accomplished",
        "accomplishment", "achieve", "achieved", "achievement", "achievements",
        "achieving", "adequate", "advance", "advanced", "advancement",
        "advancing", "advantage", "advantageous", "advantages",
        "beneficial", "beneficiary", "benefit", "benefited", "benefits",
        "best", "better", "bolster", "bolstered", "boom", "boost",
        "boosted", "breakthrough",
        "capable", "collaboration", "collaborative", "commend",
        "commended", "competent", "competitive", "compliment",
        "confident", "constructive", "creative", "creativity",
        "dependable", "desirable", "diligent", "distinction",
        "distinguished", "diverse", "diversified", "diversify",
        "dividend", "dominance", "dominated",
        "earn", "earned", "earning", "earnings", "ease", "eased",
        "easier", "easy", "effective", "effectiveness", "efficiency",
        "efficient", "efficiently", "empower", "empowered", "enable",
        "enabled", "encourage", "encouraged", "encouraging",
        "endorse", "endorsed", "enhance", "enhanced", "enhancement",
        "enjoy", "enjoyed", "enjoying", "enthusiasm", "enthusiastic",
        "excellence", "excellent", "exceptional", "exceptionally",
        "exciting", "exclusive", "expand", "expanded", "expanding",
        "expansion", "expertise",
        "favorable", "favorably", "flagship", "flexibility", "flourish",
        "forefront", "fortify", "fruitful",
        "gain", "gained", "gains", "generate", "generated", "generating",
        "good", "great", "greater", "greatest", "grew", "grow",
        "growing", "grown", "growth",
        "highest", "honor", "honored",
        "ideal", "improve", "improved", "improvement", "improvements",
        "improving", "increase", "increased", "increases", "increasing",
        "incredible", "innovative", "innovation", "insightful",
        "instrumental",
        "leadership", "leading", "lucrative",
        "maximize", "maximized", "momentum",
        "notable", "noteworthy",
        "optimal", "optimism", "optimistic", "optimize", "optimized",
        "outpace", "outpaced", "outperform", "outperformed",
        "outperformance", "outperforming", "outstanding", "overcome",
        "pioneering", "pleased", "positive", "positively", "powerful",
        "premium", "proactive", "proficiency", "proficient", "profit",
        "profitability", "profitable", "profitably", "progress",
        "progressed", "progressive", "prominent", "promising",
        "prosper", "prosperity", "prosperous",
        "rebound", "rebounded", "recover", "recovered", "recovery",
        "reliable", "reliability", "resilient", "resolve", "resolved",
        "responsive", "restore", "restored", "retain", "retained",
        "revenue", "revitalize", "reward", "rewarded", "rewarding",
        "robust", "rose",
        "satisfaction", "satisfactory", "satisfied", "solid",
        "solution", "solutions", "stable", "steadily", "steady",
        "stimulate", "stimulated", "strategic", "strategically",
        "strength", "strengthen", "strengthened", "strengthening",
        "strong", "stronger", "strongest", "succeed", "succeeded",
        "succeeding", "success", "successful", "successfully",
        "superior", "surpass", "surpassed", "surge", "surged",
        "sustainable", "sustained", "synergy",
        "talent", "talented", "thrive", "thriving", "top",
        "transform", "transformative", "tremendous",
        "unmatched", "unparalleled", "upgrade", "upgraded", "uplift",
        "upside", "upturn", "upward",
        "valuable", "value", "valued", "versatile", "vibrant",
        "victory", "vigorous", "vital",
        "win", "winner", "winning", "won"
    };
    uncertainty_ = {
        "almost", "ambiguity", "ambiguous", "anomalous", "anomaly",
        "anticipate", "anticipated", "apparent", "apparently", "appear",
        "appeared", "appears", "approximate", "approximately",
        "assumption", "assumptions",
        "believe", "believed", "believes",
        "conceivable", "conceivably", "conditional", "conditionally",
        "confuse", "confusing", "confusion", "contingency", "contingent",
        "could",
        "depend", "dependent", "depending", "depends", "deviate",
        "deviation",
        "doubt", "doubtful",
        "equivocal", "estimate", "estimated", "estimation",
        "expect", "expectation", "expectations", "expected",
        "fluctuate", "fluctuation", "fluctuations",
        "generally",
        "imprecise", "imprecision", "improbable", "incompleteness",
        "indefinite", "indefinitely", "indeterminate", "indicate",
        "indication", "indicative", "inexact",
        "likelihood", "likely",
        "may", "maybe", "might",
        "nearly", "nonassessable",
        "occasionally",
        "perhaps", "plausible", "possibility", "possible", "possibly",
        "potential", "potentially", "precaution", "predict",
        "predictability", "predicted", "prediction", "predictions",
        "preliminary", "presumably", "presume", "presumed",
        "probabilistic", "probability", "probable", "probably",
        "projection", "projections",
        "random", "randomness", "reasonably", "recalculate",
        "reconsider", "reexamine", "reinterpret", "reinterpretation",
        "revise", "revised", "revision", "roughly", "rumor", "rumors",
        "seem", "seemed", "seemingly", "seems", "seldom",
        "sometimes", "somewhat", "somewhere", "speculate",
        "speculation", "speculative", "suggest", "suggested", "suggests",
        "suppose", "supposed", "susceptible",
        "tend", "tended", "tends", "tentative", "tentatively",
        "uncertain", "uncertainly", "uncertainties", "uncertainty",
        "unclear", "unconfirmed", "undecided", "undefined",
        "undetermined", "unexpected", "unexpectedly", "unforeseen",
        "unknown", "unlikely", "unobservable", "unpredictable",
        "unpredictably", "unproven", "unquantifiable", "unresolved",
        "unsettled", "unspecified", "untested",
        "vagaries", "vague", "vaguely", "variability", "variable",
        "variation", "vary", "varying", "volatile", "volatility"
    };
    litigious_ = {
        "adjudicate", "adjudicated", "adjudication", "allegation",
        "allegations", "allege", "alleged", "allegedly", "amend",
        "amended", "amendment", "appeal", "appealed", "appeals",
        "arbitrate", "arbitrated", "arbitration", "attorney", "attorneys",
        "claimant", "claimants", "class", "clause", "clauses",
        "codefendant", "codefendants", "complainant", "complainants",
        "complaint", "complaints", "consent", "contend", "contended",
        "contention", "contentions", "contractual", "counterclaim",
        "counterclaimed", "counterclaims", "court", "courts",
        "damages", "decree", "decrees", "defendant", "defendants",
        "deposition", "depositions", "discovery", "docket",
        "enjoin", "enjoined", "evidentiary",
        "fiduciary", "filed", "filing", "filings",
        "incriminate", "indict", "indicted", "indictment",
        "infringement", "injunction", "injunctions",
        "judge", "judges", "judgment", "judgments", "judicial",
        "jurisdiction", "jurisdictions", "jury", "justice",
        "lawsuit", "lawsuits", "legal", "legally", "legislate",
        "legislation", "legislative", "litigate", "litigated",
        "litigation", "litigations",
        "magistrate", "mediate", "mediation", "motion", "motions",
        "plaintiff", "plaintiffs", "plea", "plead", "pleading",
        "precedent", "proceeding", "proceedings", "prosecute",
        "prosecuted", "prosecution",
        "regulator", "regulators", "regulatory", "remand", "remedy",
        "respondent", "respondents", "restitution", "rulings",
        "settlement", "settlements", "statute", "statutes",
        "statutory", "stipulate", "stipulated", "stipulation",
        "subpoena", "subpoenaed", "subpoenas", "sue", "sued", "suing",
        "summons", "testimony", "tort", "torts", "trial", "trials",
        "tribunal", "tribunals",
        "verdict", "verdicts", "violate", "violated", "violation",
        "violations", "witness", "witnesses"
    };
    strong_modal_ = {
        "always", "best", "clearly", "definitely", "definitively",
        "certainly", "committed", "compelled", "essential",
        "guaranteed", "highest", "mandated", "mandatory", "must",
        "necessary", "necessitate", "never", "obligated", "obligatory",
        "required", "shall", "strongest", "unequivocally", "will"
    };
    weak_modal_ = {
        "almost", "apparently", "approximately", "conceivable",
        "conceivably", "could", "depend", "dependent", "depending",
        "depends", "generally", "largely", "likelihood", "likely",
        "may", "maybe", "might", "mostly", "nearly", "occasionally",
        "often", "partially", "partly", "perhaps", "plausible",
        "possible", "possibly", "potential", "potentially",
        "predicated", "predominantly", "presumably", "probable",
        "probably", "seldom", "should", "sometimes", "somewhat",
        "suggest", "suggested", "suggesting", "suggests", "susceptible",
        "tend", "tended", "tends", "typically", "usually", "would"
    };
    forward_looking_ = {
        "aim", "aims", "anticipate", "anticipated", "anticipates",
        "anticipating", "believe", "believes", "could",
        "estimate", "estimated", "estimates", "expect", "expectation",
        "expectations", "expected", "expects",
        "forecast", "forecasted", "forecasting", "forecasts",
        "foresee", "forward", "future",
        "goal", "goals", "guidance", "guide", "guides",
        "intend", "intending", "intends", "intention", "intentions",
        "may", "might",
        "objective", "objectives", "opportunity", "outlook",
        "pipeline", "plan", "planned", "planning", "plans",
        "predict", "predicted", "prediction", "predictions",
        "project", "projected", "projection", "projections",
        "pursue", "pursuing",
        "seek", "seeking", "seeks", "shall", "should", "strategy",
        "target", "targets", "will", "would"
    };
}
LexiconScore LexiconSentiment::score(const std::string& text) const {
    LexiconScore result;
    auto words = tokenize(text);
    result.total_words = static_cast<int>(words.size());
    for (const auto& w : words) {
        if (positive_.count(w))       result.positive_count++;
        if (negative_.count(w))       result.negative_count++;
        if (uncertainty_.count(w))    result.uncertainty_count++;
        if (litigious_.count(w))      result.litigious_count++;
        if (strong_modal_.count(w))   result.strong_modal++;
        if (weak_modal_.count(w))     result.weak_modal++;
        if (forward_looking_.count(w)) result.is_forward_looking = true;
    }
    return result;
}

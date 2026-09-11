import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

/**
 * TemplateEngine — Reads the C++ JSON snapshot and injects its values into
 * the HTML report template, producing a fully rendered HTML string ready
 * for Flying Saucer PDF rendering.
 *
 * <p>This is intentionally dependency-free — we parse the JSON with a tiny
 * hand-rolled approach (adequate for the well-known snapshot schema) and
 * use simple String replacement for the Mustache-like placeholders.
 */
public class TemplateEngine {

    private static final String TEMPLATE_PATH = "java/resources/report_template.html";

    /**
     * Renders the HTML template with data from the given JSON snapshot.
     *
     * @param jsonPath path to the C++ JSON snapshot file
     * @return fully rendered HTML string, or null on error
     */
    public static String render(String jsonPath) {
        try {
            String template = Files.readString(Path.of(TEMPLATE_PATH), StandardCharsets.UTF_8);
            String jsonStr  = Files.readString(Path.of(jsonPath), StandardCharsets.UTF_8);

            // ── Minimal JSON parsing via simple extraction ──
            // We pull top-level fields with straightforward string operations.
            // This avoids pulling in a JSON library in Java.

            String ticker         = extractString(jsonStr, "ticker");
            String compositeScore = extractNumber(jsonStr, "composite_score");
            String convictionLabel= extractString(jsonStr, "conviction_label");
            
            long generationId = 0;
            try {
                // The C++ engine writes generation_id as a string, so we must extract it as a string first.
                generationId = Long.parseLong(extractString(jsonStr, "generation_id"));
            } catch (Exception e) {
                System.err.println("  [TemplateEngine] Could not parse generation_id, defaulting to 0");
            }

            // Sentiment block
            String sentimentBlock = extractObject(jsonStr, "sentiment");
            String sentLabel = extractString(sentimentBlock, "overall_label");
            String sentScore = extractNumber(sentimentBlock, "overall_score");

            // Format generation date
            String generationDate = DateTimeFormatter.ofPattern("dd MMM yyyy, HH:mm z")
                .withZone(ZoneId.systemDefault())
                .format(Instant.ofEpochSecond(generationId));

            // ── Inject scalar placeholders ──
            template = template.replace("{{TICKER}}", esc(ticker));
            template = template.replace("{{COMPOSITE_SCORE}}", esc(compositeScore));
            template = template.replace("{{CONVICTION_LABEL}}", esc(convictionLabel));
            template = template.replace("{{SENTIMENT_LABEL}}", esc(sentLabel));
            template = template.replace("{{SENTIMENT_SCORE}}", esc(sentScore));
            template = template.replace("{{GENERATION_ID}}", String.valueOf(generationId));
            template = template.replace("{{GENERATION_DATE}}", esc(generationDate));

            // ── Ratios Table ──
            template = template.replace("{{RATIOS_TABLE}}", buildRatiosTable(jsonStr));
            template = template.replace("{{METRICS_COUNT}}", String.valueOf(countArrayItems(jsonStr, "ratios")));

            // ── Key Statistics Table ──
            template = template.replace("{{KEY_STATS_TABLE}}", buildKeyStatsTable(jsonStr));

            // ── News Section ──
            template = template.replace("{{NEWS_SECTION}}", buildExcerptSection(jsonStr, "news_excerpts", 5));

            // ── Peers Table ──
            template = template.replace("{{PEERS_TABLE}}", buildPeersTable(jsonStr, ticker));

            return template;

        } catch (Exception e) {
            System.err.println("  [TemplateEngine] Error rendering template: " + e.getMessage());
            e.printStackTrace();
            return null;
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    //  Table Builders
    // ═══════════════════════════════════════════════════════════════════

    private static String buildRatiosTable(String json) {
        String ratiosArray = extractArray(json, "ratios");
        if (ratiosArray.isEmpty()) return "<p><em>Financial ratios are pending evaluation.</em></p>";

        StringBuilder sb = new StringBuilder();
        sb.append("<table><tr><th>Ratio</th><th>Category</th><th>Value</th><th>Health</th><th>Narrative</th></tr>");

        int idx = 0;
        while (true) {
            String item = extractArrayItem(ratiosArray, idx++);
            if (item == null) break;

            String displayName = extractString(item, "display_name");
            String category    = extractString(item, "category");
            String formatted   = extractString(item, "formatted");
            String health      = extractString(item, "health_flag");
            String narrative   = extractString(item, "narrative");

            if (formatted != null && (formatted.contains("DATA_MISSING") || formatted.contains("NOT_COMPUTABLE"))) {
                formatted = "Bruh, API ghosted us. We're on the free tier here \uD83D\uDC80";
                narrative = "Can't do math with invisible numbers.";
            }

            String badgeClass = "badge-neutral";
            if ("HEALTHY".equals(health))       badgeClass = "badge-healthy";
            else if ("CONCERNING".equals(health)) badgeClass = "badge-concerning";
            else if ("CRITICAL".equals(health))   badgeClass = "badge-critical";

            sb.append("<tr>")
              .append("<td><strong>").append(esc(displayName)).append("</strong></td>")
              .append("<td>").append(esc(category)).append("</td>")
              .append("<td>").append(esc(formatted)).append("</td>")
              .append("<td><span class=\"badge ").append(badgeClass).append("\">").append(esc(health)).append("</span></td>")
              .append("<td>").append(esc(narrative)).append("</td>")
              .append("</tr>");
        }
        sb.append("</table>");
        return sb.toString();
    }

    private static String buildKeyStatsTable(String json) {
        String statsArray = extractArray(json, "key_statistics");
        if (statsArray.isEmpty()) return "<p><em>Key statistics are unavailable.</em></p>";

        StringBuilder sb = new StringBuilder();
        sb.append("<table><tr><th>Metric</th><th>Value</th></tr>");

        int idx = 0;
        while (true) {
            String item = extractArrayItem(statsArray, idx++);
            if (item == null) break;

            String displayName = extractString(item, "display_name");
            String formatted   = extractString(item, "formatted");

            sb.append("<tr>")
              .append("<td><strong>").append(esc(displayName)).append("</strong></td>")
              .append("<td>").append(esc(formatted)).append("</td>")
              .append("</tr>");
        }
        sb.append("</table>");
        return sb.toString();
    }

    private static String buildExcerptSection(String json, String arrayName, int limit) {
        String arr = extractArray(json, arrayName);
        if (arr.isEmpty() || arr.equals("[]") || arr.equals("[\n]")) return "<p><em>Data unavailable.</em></p>";

        StringBuilder sb = new StringBuilder();
        int idx = 0;
        while (idx < limit) {
            String item = extractArrayItem(arr, idx++);
            if (item == null) break;

            String label  = extractString(item, "label");
            String excerpt= extractString(item, "excerpt");
            String url    = extractString(item, "source_url");
            String date   = extractString(item, "published_at");

            String sentClass = "sent-neutral";
            if (label != null) {
                String lower = label.toLowerCase();
                if (lower.contains("positive")) sentClass = "sent-positive";
                else if (lower.contains("negative")) sentClass = "sent-negative";
            }

            sb.append("<div class=\"excerpt\">")
              .append("<span class=\"").append(sentClass).append("\">[").append(esc(label)).append("]</span> ")
              .append(esc(excerpt));
            if (url != null && !url.isEmpty()) {
                sb.append(" <span class=\"text-muted\">(").append(esc(date)).append(")</span>");
            }
            sb.append("</div>");
        }
        if (sb.length() == 0) return "<p><em>Data unavailable.</em></p>";
        return sb.toString();
    }

    private static String buildPeersTable(String json, String ticker) {
        String arr = extractArray(json, "peer_benchmarks");
        if (arr.isEmpty()) return "<p><em>Peer benchmark data is currently unavailable.</em></p>";

        StringBuilder sb = new StringBuilder();
        sb.append("<table><tr><th>Peer</th><th>Ratio</th><th>")
          .append(esc(ticker)).append(" Value</th><th>Peer Value</th><th>Prem/Disc</th></tr>");

        int idx = 0;
        while (true) {
            String item = extractArrayItem(arr, idx++);
            if (item == null) break;

            String peerTicker = extractString(item, "peer_ticker");
            String ratioName  = extractString(item, "ratio_name");
            String tickerVal  = extractNumber(item, "ticker_value");
            String peerVal    = extractNumber(item, "peer_value");
            String premDisc   = extractNumber(item, "premium_discount");

            sb.append("<tr>")
              .append("<td>").append(esc(peerTicker)).append("</td>")
              .append("<td>").append(esc(ratioName)).append("</td>")
              .append("<td>").append(esc(tickerVal)).append("</td>")
              .append("<td>").append(esc(peerVal)).append("</td>")
              .append("<td>").append(esc(premDisc)).append("%</td>")
              .append("</tr>");
        }
        sb.append("</table>");
        return sb.toString();
    }

    // ═══════════════════════════════════════════════════════════════════
    //  Minimal JSON extraction helpers (no external dependency)
    // ═══════════════════════════════════════════════════════════════════

    /** Extracts a string value: "key": "value" */
    private static String extractString(String json, String key) {
        if (json == null) return "";
        String search = "\"" + key + "\"";
        int ki = json.indexOf(search);
        if (ki < 0) return "";
        int colon = json.indexOf(':', ki + search.length());
        if (colon < 0) return "";
        // Skip whitespace after colon
        int vi = colon + 1;
        while (vi < json.length() && Character.isWhitespace(json.charAt(vi))) vi++;
        if (vi >= json.length()) return "";
        if (json.charAt(vi) == '"') {
            int end = findClosingQuote(json, vi);
            return json.substring(vi + 1, end).replace("\\\"", "\"").replace("\\n", " ");
        }
        if (json.charAt(vi) == 'n') return ""; // null
        // It might be a number — delegate to extractNumber
        return "";
    }

    /** Extracts a number value as a formatted string */
    private static String extractNumber(String json, String key) {
        if (json == null) return "0";
        String search = "\"" + key + "\"";
        int ki = json.indexOf(search);
        if (ki < 0) return "0";
        int colon = json.indexOf(':', ki + search.length());
        if (colon < 0) return "0";
        int vi = colon + 1;
        while (vi < json.length() && Character.isWhitespace(json.charAt(vi))) vi++;
        if (vi >= json.length()) return "0";
        if (json.charAt(vi) == 'n') return "0"; // null
        int end = vi;
        while (end < json.length() && !isJsonDelimiter(json.charAt(end))) end++;
        String raw = json.substring(vi, end).trim();
        try {
            double d = Double.parseDouble(raw);
            return String.format("%.2f", d);
        } catch (NumberFormatException e) {
            return raw;
        }
    }

    private static long extractLong(String json, String key) {
        String raw = extractNumber(json, key);
        try { return (long) Double.parseDouble(raw); } catch (Exception e) { return 0; }
    }

    /** Extracts a nested JSON object as a raw string */
    private static String extractObject(String json, String key) {
        if (json == null) return "{}";
        String search = "\"" + key + "\"";
        int ki = json.indexOf(search);
        if (ki < 0) return "{}";
        int brace = json.indexOf('{', ki + search.length());
        if (brace < 0) return "{}";
        int end = findClosingBrace(json, brace, '{', '}');
        return json.substring(brace, end + 1);
    }

    /** Extracts a JSON array as a raw string */
    private static String extractArray(String json, String key) {
        if (json == null) return "";
        String search = "\"" + key + "\"";
        int ki = json.indexOf(search);
        if (ki < 0) return "";
        int bracket = json.indexOf('[', ki + search.length());
        if (bracket < 0) return "";
        int end = findClosingBrace(json, bracket, '[', ']');
        return json.substring(bracket, end + 1);
    }

    /** Extracts the nth item from a JSON array string */
    private static String extractArrayItem(String arrStr, int index) {
        if (arrStr == null || arrStr.length() < 2) return null;
        // Strip outer brackets
        String inner = arrStr.substring(1, arrStr.length() - 1).trim();
        if (inner.isEmpty()) return null;

        int depth = 0;
        int itemStart = 0;
        int itemIdx = 0;
        for (int i = 0; i < inner.length(); i++) {
            char c = inner.charAt(i);
            if (c == '"') {
                i = findClosingQuote(inner, i);
            } else if (c == '{' || c == '[') {
                depth++;
            } else if (c == '}' || c == ']') {
                depth--;
            } else if (c == ',' && depth == 0) {
                if (itemIdx == index) {
                    return inner.substring(itemStart, i).trim();
                }
                itemIdx++;
                itemStart = i + 1;
            }
        }
        if (itemIdx == index) {
            return inner.substring(itemStart).trim();
        }
        return null;
    }

    private static int countArrayItems(String json, String key) {
        String arr = extractArray(json, key);
        if (arr.isEmpty() || arr.length() < 3) return 0;
        int count = 0;
        int idx = 0;
        while (extractArrayItem(arr, idx++) != null) count++;
        return count;
    }

    private static int findClosingQuote(String s, int openQuotePos) {
        for (int i = openQuotePos + 1; i < s.length(); i++) {
            if (s.charAt(i) == '\\') { i++; continue; }
            if (s.charAt(i) == '"') return i;
        }
        return s.length() - 1;
    }

    private static int findClosingBrace(String s, int openPos, char open, char close) {
        int depth = 0;
        for (int i = openPos; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '"') { i = findClosingQuote(s, i); continue; }
            if (c == open) depth++;
            else if (c == close) { depth--; if (depth == 0) return i; }
        }
        return s.length() - 1;
    }

    private static boolean isJsonDelimiter(char c) {
        return c == ',' || c == '}' || c == ']' || c == '\n' || c == '\r';
    }

    private static String esc(String text) {
        if (text == null) return "";
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");
    }
}

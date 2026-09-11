import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/**
 * ApiFetcher — Data Ingestion Orchestrator
 * <p>
 * Because Yahoo Finance blocks cloud server IPs and FMP is paid-only,
 * this Java orchestrator delegates the actual HTTP web scraping to a
 * specialized Python script (python/tricker.py). The Python script uses
 * C-bindings (curl_cffi) to impersonate Google Chrome, bypassing the WAF,
 * and dumps the resulting JSON data into the json/ directory for the C++
 * engine to consume.
 */
public class ApiFetcher {

    // ── Peer lists (same sector groupings as before) ──
    private static final Map<String, List<String>> SECTOR_PEERS = Map.of(
        "IT",       List.of("TCS", "INFY", "WIPRO", "HCLTECH"),
        "BANKS",    List.of("HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK"),
        "ENERGY",   List.of("RELIANCE", "ONGC", "BPCL"),
        "FMCG",     List.of("ITC", "HINDUNILVR", "NESTLEIND"),
        "TELECOM",  List.of("BHARTIARTL", "IDEA", "INDUSTOWER"),
        "CAPGOODS", List.of("LT", "BHEL", "SIEMENS")
    );

    /**
     * Main entry point: runs the Python tricker script for the ticker and its peers.
     */
    public static String fetchAll(String ticker, String generationId) {
        System.out.println("  [Java/ApiFetcher] Starting stealth Yahoo ingestion via python/tricker.py for " + ticker);

        // 1. Ensure output directories exist
        try {
            Files.createDirectories(Path.of("json"));
            Files.createDirectories(Path.of("cache"));
        } catch (IOException e) {
            System.err.println("  [Java/ApiFetcher] Could not create directories: " + e.getMessage());
            return null;
        }

        // 2. Find Peers
        List<String> peerTickers = new ArrayList<>();
        String base = ticker.replace(".NS", "");
        for (Map.Entry<String, List<String>> entry : SECTOR_PEERS.entrySet()) {
            if (entry.getValue().contains(base)) {
                for (String p : entry.getValue()) {
                    String full = p + ".NS";
                    if (!full.equals(ticker)) {
                        peerTickers.add(full);
                    }
                }
                break;
            }
        }

        // 3. Construct Command
        List<String> cmd = new ArrayList<>();
        cmd.add("python");
        cmd.add("python/tricker.py");
        cmd.add(generationId);
        cmd.add(ticker);
        cmd.addAll(peerTickers);

        System.out.println("  [Java/ApiFetcher] Executing: " + String.join(" ", cmd));

        // 4. Run Python subprocess
        try {
            ProcessBuilder pb = new ProcessBuilder(cmd);
            pb.redirectErrorStream(true);
            Process proc = pb.start();

            try (BufferedReader br = new BufferedReader(new InputStreamReader(proc.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = br.readLine()) != null) {
                    System.out.println("    " + line);
                }
            }

            int exitCode = proc.waitFor();
            if (exitCode != 0) {
                System.err.println("  [Java/ApiFetcher] FATAL: python/tricker.py exited with code " + exitCode);
            } else {
                System.out.println("  [Java/ApiFetcher] Successfully fetched Yahoo data.");
                // Fetch news sequentially after Python completes
                NewsManager.fetchNews(ticker, generationId);
            }

        } catch (Exception e) {
            System.err.println("  [Java/ApiFetcher] Exception running Python tricker: " + e.getMessage());
            e.printStackTrace();
        }

        return "json/yf_temp.json";
    }
}

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
public class ApiFetcher {
    private static final Map<String, List<String>> SECTOR_PEERS = Map.of(
        "IT",       List.of("TCS", "INFY", "WIPRO", "HCLTECH"),
        "BANKS",    List.of("HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK"),
        "ENERGY",   List.of("RELIANCE", "ONGC", "BPCL"),
        "FMCG",     List.of("ITC", "HINDUNILVR", "NESTLEIND"),
        "TELECOM",  List.of("BHARTIARTL", "IDEA", "INDUSTOWER"),
        "CAPGOODS", List.of("LT", "BHEL", "SIEMENS")
    );
    public static String fetchAll(String ticker, String generationId) {
        System.out.println("  [Java/ApiFetcher] Starting stealth Yahoo ingestion via python/tricker.py for " + ticker);
        try {
            Files.createDirectories(Path.of("json"));
            Files.createDirectories(Path.of("cache"));
        } catch (IOException e) {
            System.err.println("  [Java/ApiFetcher] Could not create directories: " + e.getMessage());
            return null;
        }
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
        List<String> cmd = new ArrayList<>();
        cmd.add("python");
        cmd.add("python/tricker.py");
        cmd.add(generationId);
        cmd.add(ticker);
        cmd.addAll(peerTickers);
        System.out.println("  [Java/ApiFetcher] Executing: " + String.join(" ", cmd));
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
                NewsManager.fetchNews(ticker, generationId);
            }
        } catch (Exception e) {
            System.err.println("  [Java/ApiFetcher] Exception running Python tricker: " + e.getMessage());
            e.printStackTrace();
        }
        return "json/yf_temp.json";
    }
}

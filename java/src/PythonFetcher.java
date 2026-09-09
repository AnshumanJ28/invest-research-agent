import java.util.Arrays;
import java.util.List;
import java.util.ArrayList;

public class PythonFetcher {
    
    public static void fetchConcurrent(String ticker) {
        System.out.println("  [Java] Running unified Python fetch (single process, memory-safe)...");
        
        String base = ticker.split("\\.")[0].toUpperCase();
        List<String> peers = getPeers(base, ticker);
        
        try {
            List<String> command = new ArrayList<>();
            command.add("python");
            command.add("python/ingestion/unified_fetch.py");
            command.add(ticker);
            command.addAll(peers);
            
            ProcessBuilder pb = new ProcessBuilder(command);
            pb.inheritIO();
            Process p = pb.start();
            int exitCode = p.waitFor();
            if (exitCode != 0) {
                System.err.println("  [Java] Unified fetch exited with code: " + exitCode);
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
        
        System.out.println("  [Java] All data fetched.");
    }

    private static List<String> getPeers(String base, String ticker) {
        List<String> peers = new ArrayList<>();
        
        List<String> it = Arrays.asList("TCS", "INFY", "WIPRO", "HCLTECH");
        List<String> banks = Arrays.asList("HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK");
        List<String> energy = Arrays.asList("RELIANCE", "ONGC", "BPCL");
        List<String> fmcg = Arrays.asList("ITC", "HINDUNILVR", "NESTLEIND");
        List<String> telecom = Arrays.asList("BHARTIARTL", "IDEA", "INDUSTOWER");
        List<String> capgoods = Arrays.asList("LT", "BHEL", "SIEMENS");

        List<List<String>> sectorGroups = Arrays.asList(it, banks, energy, fmcg, telecom, capgoods);
        
        for (List<String> group : sectorGroups) {
            if (group.contains(base)) {
                for (String p : group) {
                    peers.add(p + ".NS");
                }
                break;
            }
        }
        peers.remove(ticker);
        if (!peers.contains("^NSEI")) {
            peers.add("^NSEI");
        }
        return peers;
    }
}

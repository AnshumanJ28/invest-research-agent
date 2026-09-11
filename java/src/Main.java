import java.io.*;
import java.nio.charset.StandardCharsets;
public class Main {
    public static void main(String[] args) {
        if (args.length == 0) {
            System.err.println("Usage: java Main <TICKER>");
            System.exit(1);
        }
        String ticker = args[0].toUpperCase();
        System.out.println("\n=== [Java] Starting Investment Pipeline for " + ticker + " ===");
        System.setProperty("java.awt.headless", "true");
        String generationId = String.valueOf(System.currentTimeMillis() / 1000L);
        System.out.println("\n--- Stage 1: FMP Data Ingestion ---");
        ApiFetcher.fetchAll(ticker, generationId);
        System.out.println("\n--- Stage 2: C++ AI & Math Engine ---");
        System.out.println("  [Java] Delegating AI Inference, Math, and JSON Snapshot to C++ Engine...");
        String jsonSnapshotPath = invokeCppEngine("cpp/build/Release/invest_pipeline.exe", ticker, generationId);
        if (jsonSnapshotPath == null || jsonSnapshotPath.isBlank()) {
            System.err.println("  [Java] WARNING: C++ engine did not produce a JSON snapshot path.");
            System.err.println("  [Java] PDF generation will be skipped.");
        } else {
            System.out.println("\n--- Stage 3: PDF Report Generation ---");
            String pdfPath = jsonSnapshotPath.replace(".json", ".pdf");
            PdfGenerator.generatePdf(jsonSnapshotPath, pdfPath);
            System.out.println("\n[OUTPUT_JSON] " + jsonSnapshotPath);
        }
        System.out.println("\n=== [Java] Pipeline Complete! ===");
    }
    private static String invokeCppEngine(String executablePath, String ticker, String generationId) {
        String jsonPath = null;
        try {
            System.out.println("    -> Executing: " + executablePath + " " + ticker + " --skip-rag --gen-id " + generationId);
            ProcessBuilder pb = new ProcessBuilder(executablePath, ticker, "--skip-rag", "--gen-id", generationId);
            pb.redirectErrorStream(true);
            Process p = pb.start();
            try (BufferedReader br = new BufferedReader(
                    new InputStreamReader(p.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = br.readLine()) != null) {
                    System.out.println("    [C++] " + line);
                    if (line.startsWith("[OUTPUT_JSON] ")) {
                        jsonPath = line.substring("[OUTPUT_JSON] ".length()).trim();
                    }
                }
            }
            int exitCode = p.waitFor();
            if (exitCode != 0) {
                System.err.println("  [Java] C++ engine exited with code: " + exitCode);
            }
        } catch (Exception e) {
            System.err.println("  [Java] Failed to invoke C++ engine: " + e.getMessage());
            e.printStackTrace();
        }
        return jsonPath;
    }
}

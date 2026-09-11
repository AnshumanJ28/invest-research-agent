import java.io.*;
import java.nio.charset.StandardCharsets;

/**
 * Main — Polyglot pipeline orchestrator.
 *
 * <p>Pipeline stages:
 * <ol>
 *   <li><b>ApiFetcher</b> (Java) — Concurrent FMP ingestion with 24h cache.</li>
 *   <li><b>C++ Engine</b> — AI inference, SIMD math, and JSON snapshot generation.</li>
 *   <li><b>TemplateEngine + PdfGenerator</b> (Java) — HTML template → PDF.</li>
 * </ol>
 *
 * <p>On completion, prints the JSON snapshot path to stdout for FastAPI:
 * {@code [OUTPUT_JSON] reports/TICKER_TIMESTAMP.json}
 */
public class Main {

    public static void main(String[] args) {
        if (args.length == 0) {
            System.err.println("Usage: java Main <TICKER>");
            System.exit(1);
        }

        String ticker = args[0].toUpperCase();
        System.out.println("\n=== [Java] Starting Investment Pipeline for " + ticker + " ===");

        // Dramatically speeds up PDF generation by skipping AWT GUI initialization
        System.setProperty("java.awt.headless", "true");

        // Generate a unique generation ID (Unix timestamp) for concurrency safety
        String generationId = String.valueOf(System.currentTimeMillis() / 1000L);

        // ──────────────────────────────────────────────────
        // 1. FMP Data Ingestion (Java — parallel HTTP)
        // ──────────────────────────────────────────────────
        System.out.println("\n--- Stage 1: FMP Data Ingestion ---");
        ApiFetcher.fetchAll(ticker, generationId);

        // ──────────────────────────────────────────────────
        // 2. C++ AI/Math Engine + JSON Snapshot
        // ──────────────────────────────────────────────────
        System.out.println("\n--- Stage 2: C++ AI & Math Engine ---");
        System.out.println("  [Java] Delegating AI Inference, Math, and JSON Snapshot to C++ Engine...");

        String jsonSnapshotPath = invokeCppEngine("cpp/build/Release/invest_pipeline.exe", ticker, generationId);

        if (jsonSnapshotPath == null || jsonSnapshotPath.isBlank()) {
            System.err.println("  [Java] WARNING: C++ engine did not produce a JSON snapshot path.");
            System.err.println("  [Java] PDF generation will be skipped.");
        } else {
            // ──────────────────────────────────────────────────
            // 3. HTML Template → PDF (Java)
            // ──────────────────────────────────────────────────
            System.out.println("\n--- Stage 3: PDF Report Generation ---");

            // Derive PDF path from JSON path: replace .json with .pdf
            String pdfPath = jsonSnapshotPath.replace(".json", ".pdf");

            PdfGenerator.generatePdf(jsonSnapshotPath, pdfPath);

            // ──────────────────────────────────────────────────
            // 4. Print output path for FastAPI to capture
            // ──────────────────────────────────────────────────
            System.out.println("\n[OUTPUT_JSON] " + jsonSnapshotPath);
        }

        System.out.println("\n=== [Java] Pipeline Complete! ===");
    }

    /**
     * Invokes the C++ engine and captures its stdout to find the
     * {@code [OUTPUT_JSON]} line containing the snapshot path.
     *
     * @return the JSON snapshot file path, or null if not found.
     */
    private static String invokeCppEngine(String executablePath, String ticker, String generationId) {
        String jsonPath = null;
        try {
            System.out.println("    -> Executing: " + executablePath + " " + ticker + " --skip-rag --gen-id " + generationId);
            ProcessBuilder pb = new ProcessBuilder(executablePath, ticker, "--skip-rag", "--gen-id", generationId);
            pb.redirectErrorStream(true);
            Process p = pb.start();

            // Read stdout line-by-line to capture [OUTPUT_JSON]
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

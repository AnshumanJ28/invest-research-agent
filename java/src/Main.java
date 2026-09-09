public class Main {
    public static void main(String[] args) {
        if (args.length == 0) {
            System.err.println("Usage: java Main <TICKER>");
            System.exit(1);
        }
        
        String ticker = args[0].toUpperCase();
        System.out.println("\n=== [Java] Starting Investment Pipeline for " + ticker + " ===");
        
        // 1. Unified I/O Ingestion (single Python process)
        PythonFetcher.fetchConcurrent(ticker);
        
        // 2. Invoke C++ Core for AI/Math and Markdown Generation
        System.out.println("  [Java] Delegating AI Inference, Math, and Markdown Generation to C++ Engine...");
        CppEngine.invokeNativeEngine("cpp/build/Release/invest_pipeline.exe", ticker);
        
        // 3. Generate PDF from Markdown in Java (fast, no Python overhead)
        System.out.println("  [Java] Generating PDF from Markdown natively...");
        PdfGenerator.generatePdfFromMarkdown(ticker);
        
        System.out.println("=== [Java] Pipeline Complete! ===");
    }
}

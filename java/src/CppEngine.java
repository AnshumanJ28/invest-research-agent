public class CppEngine {
    
    public static void invokeNativeEngine(String executablePath, String ticker) {
        try {
            System.out.println("    -> Executing: " + executablePath + " " + ticker + " --skip-rag");
            ProcessBuilder pb = new ProcessBuilder(executablePath, ticker, "--skip-rag");
            pb.inheritIO();
            Process p = pb.start();
            p.waitFor();
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}

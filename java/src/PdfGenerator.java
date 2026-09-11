import java.io.FileOutputStream;
import java.io.OutputStream;
import java.nio.file.Path;
import java.nio.file.Paths;
import org.xhtmlrenderer.pdf.ITextRenderer;
public class PdfGenerator {
    public static void generatePdf(String jsonSnapshotPath, String pdfOutputPath) {
        System.out.println("  [Java/PdfGen] Rendering HTML template from JSON snapshot...");
        String html = TemplateEngine.render(jsonSnapshotPath);
        if (html == null || html.isBlank()) {
            System.err.println("  [Java/PdfGen] TemplateEngine returned empty HTML. Aborting PDF.");
            return;
        }
        try (OutputStream os = new FileOutputStream(pdfOutputPath)) {
            ITextRenderer renderer = new ITextRenderer();
            renderer.setDocumentFromString(html);
            renderer.layout();
            renderer.createPDF(os);
            System.out.println("  [Java/PdfGen] PDF generated: " + pdfOutputPath);
        } catch (Exception e) {
            System.err.println("  [Java/PdfGen] PDF generation error: " + e.getMessage());
            e.printStackTrace();
        }
    }
}

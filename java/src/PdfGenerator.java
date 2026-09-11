import java.io.FileOutputStream;
import java.io.OutputStream;
import java.nio.file.Path;
import java.nio.file.Paths;

import org.xhtmlrenderer.pdf.ITextRenderer;

/**
 * PdfGenerator — Takes a rendered HTML string (from {@link TemplateEngine})
 * and passes it to Flying Saucer / OpenPDF to produce a PDF file.
 *
 * <p>The old Markdown-to-HTML conversion is gone; the TemplateEngine now
 * owns the full HTML rendering pipeline using the JSON snapshot.
 */
public class PdfGenerator {

    /**
     * Generates a PDF from the given JSON snapshot path.
     *
     * @param jsonSnapshotPath path to the C++ JSON snapshot
     * @param pdfOutputPath    desired output path for the PDF
     */
    public static void generatePdf(String jsonSnapshotPath, String pdfOutputPath) {
        System.out.println("  [Java/PdfGen] Rendering HTML template from JSON snapshot...");

        // 1. Have the TemplateEngine render the HTML
        String html = TemplateEngine.render(jsonSnapshotPath);
        if (html == null || html.isBlank()) {
            System.err.println("  [Java/PdfGen] TemplateEngine returned empty HTML. Aborting PDF.");
            return;
        }

        // 2. Pass to Flying Saucer
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

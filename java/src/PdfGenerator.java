import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.Files;
import java.io.FileOutputStream;
import java.io.OutputStream;
import org.xhtmlrenderer.pdf.ITextRenderer;

public class PdfGenerator {
    public static void generatePdfFromMarkdown(String ticker) {
        Path mdPath = Paths.get("reports", ticker + ".md");
        Path pdfPath = Paths.get("reports", ticker + ".pdf");
        
        if (!Files.exists(mdPath)) {
            System.err.println("  [Java] Markdown file not found: " + mdPath);
            return;
        }
        
        try {
            String markdown = Files.readString(mdPath);
            String html = markdownToHtml(markdown, ticker);
            
            OutputStream os = new FileOutputStream(pdfPath.toFile());
            ITextRenderer renderer = new ITextRenderer();
            renderer.setDocumentFromString(html);
            renderer.layout();
            renderer.createPDF(os);
            os.close();
            
            System.out.println("  [Java] PDF generated natively: " + pdfPath);
        } catch (Exception e) {
            System.err.println("  [Java] PDF generation error: " + e.getMessage());
            e.printStackTrace();
        }
    }

    private static String markdownToHtml(String markdown, String ticker) {
        StringBuilder html = new StringBuilder();
        html.append("<html><head><meta charset='UTF-8'/>");
        html.append("<title>Investment Memo - ").append(ticker).append("</title>");
        html.append("<style>");
        html.append("body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 11px; line-height: 1.5; margin: 20px; color: #1a1a1a; }");
        html.append("h1 { font-size: 20px; color: #0d47a1; border-bottom: 2px solid #0d47a1; padding-bottom: 8px; }");
        html.append("h2 { font-size: 16px; color: #1565c0; margin-top: 24px; border-bottom: 1px solid #e0e0e0; padding-bottom: 4px; }");
        html.append("h3 { font-size: 13px; color: #1976d2; margin-top: 16px; }");
        html.append("table { -fs-table-paginate: paginate; border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 10px; }");
        html.append("tr { page-break-inside: avoid; }");
        html.append("th { background-color: #e3f2fd; padding: 6px 10px; text-align: left; border: 1px solid #bbdefb; font-weight: bold; }");
        html.append("td { padding: 5px 10px; border: 1px solid #e0e0e0; }");
        html.append("strong { color: #0d47a1; font-weight: bold; }");
        html.append("em { font-style: italic; }");
        html.append("</style></head><body>");
        
        boolean inList = false;
        boolean inTable = false;
        
        for (String line : markdown.split("\n")) {
            String trimmed = line.trim();
            
            // Handle table closure if we exit a table
            if (inTable && !trimmed.startsWith("|")) {
                html.append("</tbody></table>");
                inTable = false;
            }

            if (trimmed.startsWith("### ")) {
                if (inList) { html.append("</ul>"); inList = false; }
                html.append("<h3>").append(applyInlineFormatting(trimmed.substring(4))).append("</h3>");
            } else if (trimmed.startsWith("## ")) {
                if (inList) { html.append("</ul>"); inList = false; }
                html.append("<h2>").append(applyInlineFormatting(trimmed.substring(3))).append("</h2>");
            } else if (trimmed.startsWith("# ")) {
                if (inList) { html.append("</ul>"); inList = false; }
                html.append("<h1>").append(applyInlineFormatting(trimmed.substring(2))).append("</h1>");
            } else if (trimmed.startsWith("---")) {
                if (inList) { html.append("</ul>"); inList = false; }
                html.append("<hr/>");
            } else if (trimmed.startsWith("* ")) {
                if (!inList) { html.append("<ul>"); inList = true; }
                html.append("<li>").append(applyInlineFormatting(trimmed.substring(2))).append("</li>");
            } else if (trimmed.startsWith("|")) {
                if (inList) { html.append("</ul>"); inList = false; }
                if (trimmed.contains("|---")) {
                    // It's a separator line, skip it
                    continue;
                }
                
                String[] cols = trimmed.split("\\|");
                if (!inTable) {
                    html.append("<table><thead><tr>");
                    for (int i = 1; i < cols.length; i++) {
                        html.append("<th>").append(applyInlineFormatting(cols[i].trim())).append("</th>");
                    }
                    html.append("</tr></thead><tbody>");
                    inTable = true;
                } else {
                    html.append("<tr>");
                    for (int i = 1; i < cols.length; i++) {
                        html.append("<td>").append(applyInlineFormatting(cols[i].trim())).append("</td>");
                    }
                    html.append("</tr>");
                }
            } else if (!trimmed.isEmpty()) {
                if (inList) { html.append("</ul>"); inList = false; }
                html.append("<p>").append(applyInlineFormatting(trimmed)).append("</p>");
            }
        }
        if (inList) html.append("</ul>");
        if (inTable) html.append("</tbody></table>");
        
        html.append("</body></html>");
        return html.toString();
    }
    
    private static String escapeXml(String text) {
        return text.replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;");
    }

    private static String applyInlineFormatting(String text) {
        text = escapeXml(text);
        text = text.replaceAll("\\*\\*(.+?)\\*\\*", "<strong>$1</strong>");
        text = text.replaceAll("\\*(.+?)\\*", "<em>$1</em>");
        text = text.replaceAll("\\[([^\\]]+)\\]\\(([^\\)]+)\\)", "<a href=\"$2\">$1</a>");
        return text;
    }
}

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.*;
import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
public class NewsManager {
    public static void fetchNews(String ticker, String generationId) {
        System.out.println("  [Java/NewsManager] Starting NewsAPI ingestion for " + ticker);
        String apiKey = null;
        try {
            List<String> lines = Files.readAllLines(Path.of(".env"));
            for (String line : lines) {
                if (line.startsWith("NEWSAPI_KEY=")) {
                    apiKey = line.split("=")[1].trim();
                    break;
                }
            }
        } catch (Exception e) {
            System.err.println("  [Java/NewsManager] Could not read .env file: " + e.getMessage());
        }
        if (apiKey == null || apiKey.isEmpty()) {
            System.out.println("  [Java/NewsManager] No NEWSAPI_KEY found, skipping news.");
            return;
        }
        String cleanTicker = ticker.replace(".NS", "");
        String searchQuery = cleanTicker;
        try {
            HttpClient searchClient = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
            HttpRequest searchReq = HttpRequest.newBuilder()
                    .uri(URI.create("https:
                    .header("User-Agent", "InvestResearchAgent/2.0")
                    .GET()
                    .build();
            HttpResponse<String> searchResp = searchClient.send(searchReq, HttpResponse.BodyHandlers.ofString());
            if (searchResp.statusCode() == 200) {
                JsonObject searchJson = JsonParser.parseString(searchResp.body()).getAsJsonObject();
                if (searchJson.has("quotes") && searchJson.getAsJsonArray("quotes").size() > 0) {
                    JsonObject firstQuote = searchJson.getAsJsonArray("quotes").get(0).getAsJsonObject();
                    if (firstQuote.has("shortname") && !firstQuote.get("shortname").isJsonNull()) {
                        String shortName = firstQuote.get("shortname").getAsString();
                        String[] words = shortName.split(" ");
                        if (words.length > 0 && words[0].length() > 2) {
                            searchQuery = words[0];
                        }
                    }
                }
            }
        } catch (Exception e) {
            System.err.println("  [Java/NewsManager] Failed dynamic name lookup, falling back to ticker: " + e.getMessage());
        }
        String urlString = "https:
        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(10))
                    .build();
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(urlString))
                    .header("User-Agent", "InvestResearchAgent/2.0")
                    .GET()
                    .build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() == 200) {
                JsonObject jsonObject = JsonParser.parseString(response.body()).getAsJsonObject();
                JsonArray rawArticles = jsonObject.getAsJsonArray("articles");
                List<JsonObject> cleanedArticles = new ArrayList<>();
                Set<String> seenTitles = new HashSet<>();
                for (JsonElement element : rawArticles) {
                    JsonObject article = element.getAsJsonObject();
                    String title = article.has("title") && !article.get("title").isJsonNull() 
                                    ? article.get("title").getAsString() : "";
                    if (!title.isEmpty() && !seenTitles.contains(title)) {
                        seenTitles.add(title);
                        JsonObject cleanArticle = new JsonObject();
                        cleanArticle.addProperty("title", title);
                        String sourceName = "";
                        if (article.has("source") && article.get("source").isJsonObject()) {
                            JsonObject sourceObj = article.getAsJsonObject("source");
                            if (sourceObj.has("name") && !sourceObj.get("name").isJsonNull()) {
                                sourceName = sourceObj.get("name").getAsString();
                            }
                        } else if (article.has("source") && !article.get("source").isJsonNull()) {
                            sourceName = article.get("source").getAsString();
                        }
                        cleanArticle.addProperty("source", sourceName);
                        String publishedAt = article.has("publishedAt") && !article.get("publishedAt").isJsonNull()
                                ? article.get("publishedAt").getAsString() : "";
                        cleanArticle.addProperty("publishedAt", publishedAt);
                        String url = article.has("url") && !article.get("url").isJsonNull()
                                ? article.get("url").getAsString() : "";
                        cleanArticle.addProperty("url", url);
                        String description = article.has("description") && !article.get("description").isJsonNull()
                                ? article.get("description").getAsString() : "";
                        cleanArticle.addProperty("description", description);
                        cleanedArticles.add(cleanArticle);
                    }
                }
                String outputPath = "json/" + generationId + "_news_temp.json";
                Gson gson = new Gson();
                String cleanJson = gson.toJson(cleanedArticles);
                Files.writeString(Path.of(outputPath), cleanJson);
                System.out.println("  [Java/NewsManager] Downloaded and cleaned " + cleanedArticles.size() + " unique news articles for " + cleanTicker);
            } else {
                System.err.println("  [Java/NewsManager] Failed to fetch news: " + response.statusCode() + " - " + response.body());
            }
        } catch (Exception e) {
            System.err.println("  [Java/NewsManager] Exception fetching news: " + e.getMessage());
            e.printStackTrace();
        }
    }
}

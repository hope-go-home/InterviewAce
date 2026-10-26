package com.interviewace.service.llm;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.interviewace.config.AppProperties;

/**
 * 通义千问 LLM HTTP 客户端（OpenAI 兼容协议）。
 * 支持非流式（JSON 评分/结构化输出）与流式（SSE token 生成）。
 * 对应 Python 侧 openai.OpenAI(base_url=QWEN_BASE_URL)。
 */
@Component
public class LLMClient {

    private static final Logger log = LoggerFactory.getLogger(LLMClient.class);

    private final HttpClient http;
    private final ObjectMapper objectMapper;
    private final String apiKey;
    private final String baseUrl;
    private final String model;
    private final String judgeModel;

    public LLMClient(AppProperties props, ObjectMapper objectMapper) {
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
        this.objectMapper = objectMapper;
        this.apiKey = props.getAi().getQwen().getApiKey();
        this.baseUrl = props.getAi().getQwen().getBaseUrl();
        this.model = props.getAi().getQwen().getModel();
        String judge = props.getAi().getQwen().getJudgeModel();
        this.judgeModel = judge == null || judge.isBlank() ? this.model : judge;
    }

    /**
     * 非流式对话：单条 user 消息，返回完整文本。
     * jsonMode=true 时设置 response_format=json_object（用于评分/结构化输出）。
     */
    public String chat(String prompt, boolean jsonMode, double temperature) {
        return chatWithModel(model, prompt, jsonMode, temperature);
    }

    private String chatWithModel(String modelName, String prompt, boolean jsonMode, double temperature) {
        ObjectNode body = objectMapper.createObjectNode();
        body.put("model", modelName);
        body.put("temperature", temperature);
        if (jsonMode) {
            body.put("response_format", objectMapper.createObjectNode().put("type", "json_object"));
        }
        ArrayNode messages = body.putArray("messages");
        messages.add(objectMapper.createObjectNode().put("role", "user").put("content", prompt));
        return postForContent(body, "chat");
    }

    /**
     * 流式对话：逐 token 回调 onToken，返回拼接后的完整文本。
     * SSE 帧格式：data: {...}\n\n，以 data: [DONE] 结束。
     */
    public String chatStream(String prompt, Consumer<String> onToken) {
        ObjectNode body = objectMapper.createObjectNode();
        body.put("model", model);
        body.put("stream", true);
        body.put("temperature", 0.7);
        ArrayNode messages = body.putArray("messages");
        messages.add(objectMapper.createObjectNode().put("role", "user").put("content", prompt));

        StringBuilder full = new StringBuilder();
        try {
            HttpRequest request = buildRequest(body.toString());
            HttpResponse<java.io.InputStream> resp =
                    http.send(request, HttpResponse.BodyHandlers.ofInputStream());
            if (resp.statusCode() != 200) {
                log.warn("LLM stream HTTP {}: {}", resp.statusCode(), resp.statusCode());
                return "";
            }
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(resp.body(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    if (!line.startsWith("data: ")) continue;
                    String data = line.substring(6).trim();
                    if ("[DONE]".equals(data)) break;
                    try {
                        JsonNode chunk = objectMapper.readTree(data);
                        String delta = chunk.path("choices").path(0).path("delta").path("content").asText("");
                        if (!delta.isEmpty()) {
                            full.append(delta);
                            onToken.accept(delta);
                        }
                    } catch (Exception parseEx) {
                        // 跳过无法解析的帧
                    }
                }
            }
        } catch (IOException | InterruptedException e) {
            log.warn("LLM stream failed: {}", e.getMessage());
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
        }
        return full.toString();
    }

    /**
     * 多模态读图：提取图片中的面试题文字（对应 Python qa_service.vision_extract_node）。
     * 用 judgeModel（qwen3.8-max 多模态可读图）；账号未开通 qwen-vl 系列。
     * 返回识别出的题干文本，失败返回空串。
     */
    public String chatWithImage(String text, String imageBase64) {
        ObjectNode body = objectMapper.createObjectNode();
        body.put("model", judgeModel);
        ArrayNode messages = body.putArray("messages");
        ObjectNode msg = objectMapper.createObjectNode().put("role", "user");
        ArrayNode content = msg.putArray("content");
        content.add(objectMapper.createObjectNode().put("type", "text").put("text", text));
        ObjectNode imagePart = objectMapper.createObjectNode().put("type", "image_url");
        imagePart.putObject("image_url").put("url", "data:image/png;base64," + imageBase64);
        content.add(imagePart);
        messages.add(msg);

        return postForContent(body, "vision");
    }

    /** 联网兜底作答结果：正文 + 来源 URL + 是否真正联网成功 */
    public record SearchAnswer(String text, List<String> urls, boolean online) {}

    /**
     * 题库未收录时的联网搜索兜底（对应 Python qa_service._web_search_answer）。
     * enable_search 是 Qwen 专属能力，必须用 judgeModel；联网失败时降级为离线直答。
     */
    public SearchAnswer chatWithSearch(String prompt) {
        ObjectNode body = objectMapper.createObjectNode();
        body.put("model", judgeModel);
        body.put("temperature", 0.3);
        body.put("enable_search", true);
        ArrayNode messages = body.putArray("messages");
        messages.add(objectMapper.createObjectNode().put("role", "user").put("content", prompt));

        try {
            // 联网搜索+长文生成实测可超过 2 分钟，给 5 分钟（对齐 Python openai 默认 10min 的容错空间）
            HttpRequest request = buildRequest(body.toString(), Duration.ofMinutes(5));
            HttpResponse<String> resp = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() != 200) {
                throw new IOException("HTTP " + resp.statusCode() + ": " + truncate(resp.body(), 300));
            }
            JsonNode root = objectMapper.readTree(resp.body());
            JsonNode msg = root.path("choices").path(0).path("message");
            String text = msg.path("content").asText("");
            // 模型没真搜时会吐 <tool_call> 空壳，视为联网失败降级
            if (text.contains("<tool_call>")) {
                throw new IOException("model emitted tool_call instead of searching");
            }
            List<String> urls = new java.util.ArrayList<>();
            for (String key : new String[]{"search_results", "citations"}) {
                for (JsonNode item : msg.path(key)) {
                    String u = item.path("url").asText(item.path("source").asText(""));
                    if (!u.isBlank()) urls.add(u);
                }
            }
            return new SearchAnswer(text, urls, true);
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            log.warn("web search failed, degrade to offline: {}", e.getMessage());
            String offline = chatWithModel(judgeModel,
                    prompt + "\n\n（当前无法联网，请基于你的知识库作答）", false, 0.3);
            if (offline.isBlank()) {
                offline = "抱歉，这个问题超出了题库范围，联网检索也暂时不可用，请稍后再试。";
            }
            return new SearchAnswer(offline, List.of(), false);
        }
    }

    private String postForContent(ObjectNode body, String tag) {
        try {
            HttpRequest request = buildRequest(body.toString(), Duration.ofMinutes(4));
            HttpResponse<String> resp = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() != 200) {
                log.warn("LLM {} HTTP {}: {}", tag, resp.statusCode(), truncate(resp.body(), 300));
                return "";
            }
            JsonNode root = objectMapper.readTree(resp.body());
            return root.path("choices").path(0).path("message").path("content").asText("");
        } catch (IOException | InterruptedException e) {
            log.warn("LLM {} failed: {}", tag, e.getMessage());
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            return "";
        }
    }

    private HttpRequest buildRequest(String jsonBody) {
        return buildRequest(jsonBody, Duration.ofMinutes(3));
    }

    private HttpRequest buildRequest(String jsonBody, Duration timeout) {
        return HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/chat/completions"))
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + apiKey)
                .timeout(timeout)
                .POST(HttpRequest.BodyPublishers.ofString(jsonBody, StandardCharsets.UTF_8))
                .build();
    }

    private String truncate(String s, int max) {
        return s.length() <= max ? s : s.substring(0, max);
    }
}

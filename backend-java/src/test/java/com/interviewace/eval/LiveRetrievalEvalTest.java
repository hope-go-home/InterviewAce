package com.interviewace.eval;

import static org.junit.jupiter.api.Assumptions.assumeTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Java 版检索链路金标集评测（实弹：需要后端已启动 + Milvus 有题库数据）。
 *
 * <p>默认在 mvn test / CI 中跳过（后端不在线）。手动触发：
 * <pre>LIVE_EVAL=1 mvn test -Dtest=LiveRetrievalEvalTest</pre>
 *
 * <p>口径与 Python 版 eval_retrieval.py 完全一致：tier B 前 60 条金标 query，
 * title 前 80 字符归一化比对，指标 Recall@1/3/5/10 + MRR@10 + nDCG@10 + HitRate@10。
 * 结果写出到 target/eval_retrieval_result.json。
 */
class LiveRetrievalEvalTest {

    private static final String BASE = "http://localhost:8002";
    private static final Path GOLDEN = Path.of("..", "legacy-python", "interviewace",
            "evaluation", "golden_interview.json").normalize();
    private static final Path BASELINE = Path.of("..", "legacy-python", "interviewace",
            "evaluation", "baseline.json").normalize();
    private static final Path RESULT_OUT = Path.of("target", "eval_retrieval_result.json");
    private static final int[] KS = {1, 3, 5, 10};

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10)).build();
    private final ObjectMapper om = new ObjectMapper();

    @Test
    void evaluate() throws Exception {
        assumeTrue(System.getenv("LIVE_EVAL") != null,
                "实弹评测：需后端在线，用 LIVE_EVAL=1 mvn test -Dtest=LiveRetrievalEvalTest 触发");

        String token = login();

        JsonNode goldenAll = om.readTree(GOLDEN.toUri().toURL());
        List<JsonNode> golden = new ArrayList<>();
        for (JsonNode g : goldenAll) {
            if ("B".equals(g.path("tier").asText())) golden.add(g);
            if (golden.size() >= 60) break;
        }
        System.out.printf("评测 %d 条金标 query（tier B）→ Java 稠密+云端重排链路%n", golden.size());

        double[] recall = new double[KS.length];
        double mrr = 0, ndcg = 0, hitrate = 0;
        List<String> misses = new ArrayList<>();

        int done = 0;
        for (JsonNode g : golden) {
            String gold = normKey(g.path("gold").asText());
            List<String> ranked = retrieve(g.path("query").asText(), token);
            for (int i = 0; i < KS.length; i++) {
                if (ranked.subList(0, Math.min(KS[i], ranked.size())).contains(gold)) recall[i] += 1;
            }
            mrr += mrrAt(ranked, gold, 10);
            ndcg += ndcgAt(ranked, gold, 10);
            if (ranked.subList(0, Math.min(10, ranked.size())).contains(gold)) hitrate += 1;
            else misses.add(g.path("query").asText());
            done++;
            if (done % 10 == 0) {
                System.out.printf("  进度 %d/%d，当前 recall@1=%.3f%n", done, golden.size(), recall[0] / done);
            }
        }

        int n = golden.size();
        StringBuilder report = new StringBuilder("\n=== Java 版检索指标（稠密 + qwen3.7-text-rerank）===\n");
        for (int i = 0; i < KS.length; i++) {
            report.append(String.format("Recall@%-4d %.3f%n", KS[i], recall[i] / n));
        }
        report.append(String.format("MRR@10     %.3f%n", mrr / n));
        report.append(String.format("nDCG@10    %.3f%n", ndcg / n));
        report.append(String.format("HitRate@10 %.3f%n", hitrate / n));

        if (BASELINE.toFile().exists()) {
            JsonNode base = om.readTree(BASELINE.toUri().toURL()).path("retrieval");
            report.append("\n=== 与 Python 版基线对比（同金标同口径）===\n");
            report.append(String.format("%-12s%-14s%-14s%s%n", "指标", "Java", "Py纯稠密", "Py混合+本地重排"));
            report.append(compareRow("recall@1", recall[0] / n, base));
            report.append(compareRow("recall@10", recall[3] / n, base));
            report.append(compareRow("mrr@10", mrr / n, base));
            report.append(compareRow("ndcg@10", ndcg / n, base));
        }
        if (!misses.isEmpty()) {
            report.append(String.format("%n未命中 %d 条：%n", misses.size()));
            for (String q : misses) report.append("  - ").append(q, 0, Math.min(40, q.length())).append('\n');
        }
        System.out.println(report);

        var resultNode = om.createObjectNode();
        for (int i = 0; i < KS.length; i++) resultNode.put("recall@" + KS[i], recall[i] / n);
        resultNode.put("mrr@10", mrr / n);
        resultNode.put("ndcg@10", ndcg / n);
        resultNode.put("hitrate@10", hitrate / n);
        java.nio.file.Files.writeString(RESULT_OUT,
                om.writerWithDefaultPrettyPrinter().writeValueAsString(resultNode), StandardCharsets.UTF_8);
        System.out.println("结果已写入 " + RESULT_OUT.toAbsolutePath());
    }

    private String compareRow(String metric, double javaVal, JsonNode base) {
        return String.format("%-12s%-14.3f%-14.3f%.3f%n", metric, javaVal,
                base.path("dense_only").path(metric).asDouble(),
                base.path("hybrid_rerank").path(metric).asDouble());
    }

    /** 题库 title 存题干前 80 字符，检索返回完整题干 → 一律按前 80 字符比对（与 Python 版一致） */
    private static String normKey(String s) {
        String t = s == null ? "" : s.strip();
        return t.substring(0, Math.min(80, t.length()));
    }

    private String login() throws Exception {
        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(BASE + "/auth/login"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"username\":\"admin\",\"password\":\"admin123\"}", StandardCharsets.UTF_8))
                .build();
        HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
        return om.readTree(resp.body()).path("token").asText();
    }

    private List<String> retrieve(String query, String token) throws Exception {
        String qs = "query=" + java.net.URLEncoder.encode(query, StandardCharsets.UTF_8)
                + "&topK=10&qType=qa_pair";
        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(BASE + "/debug/retrieve?" + qs))
                .header("Authorization", "Bearer " + token)
                .timeout(Duration.ofSeconds(60))
                .GET().build();
        HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
        List<String> titles = new ArrayList<>();
        for (JsonNode s : om.readTree(resp.body()).path("sources")) {
            titles.add(normKey(s.path("title").asText()));
        }
        return titles;
    }

    private static double mrrAt(List<String> ranked, String gold, int k) {
        for (int i = 0; i < Math.min(k, ranked.size()); i++) {
            if (ranked.get(i).equals(gold)) return 1.0 / (i + 1);
        }
        return 0.0;
    }

    private static double ndcgAt(List<String> ranked, String gold, int k) {
        for (int i = 0; i < Math.min(k, ranked.size()); i++) {
            if (ranked.get(i).equals(gold)) return 1.0 / (Math.log(i + 2) / Math.log(2));
        }
        return 0.0;   // 单金标：IDCG=1
    }
}

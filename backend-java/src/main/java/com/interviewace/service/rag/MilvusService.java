package com.interviewace.service.rag;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import com.google.gson.JsonObject;
import com.interviewace.config.AppProperties;

import io.milvus.v2.client.ConnectConfig;
import io.milvus.v2.client.MilvusClientV2;
import io.milvus.v2.common.DataType;
import io.milvus.v2.common.IndexParam;
import io.milvus.v2.service.collection.request.CreateCollectionReq;
import io.milvus.v2.service.collection.request.HasCollectionReq;
import io.milvus.v2.service.collection.request.LoadCollectionReq;
import io.milvus.v2.service.index.request.CreateIndexReq;
import io.milvus.v2.service.partition.request.CreatePartitionReq;
import io.milvus.v2.service.vector.request.DeleteReq;
import io.milvus.v2.service.vector.request.InsertReq;
import io.milvus.v2.service.vector.request.QueryReq;
import io.milvus.v2.service.vector.request.SearchReq;
import io.milvus.v2.service.vector.request.data.FloatVec;
import io.milvus.v2.service.vector.response.DeleteResp;
import io.milvus.v2.service.vector.response.InsertResp;
import io.milvus.v2.service.vector.response.QueryResp;
import io.milvus.v2.service.vector.response.SearchResp;

/**
 * Milvus 数据层：interview_kb 集合的连接/建表/增删搜。
 * 对应 Python 侧 database/milvus.py。
 * 使用 milvus-sdk-java 2.5.x v2 API；启动时自动建表+建索引。
 */
@Component
public class MilvusService implements DisposableBean {

    private static final Logger log = LoggerFactory.getLogger(MilvusService.class);

    public static final List<String> PARTITIONS = List.of("qa_pair", "experience", "knowledge");
    public static final List<String> SEARCH_FIELDS = List.of(
            "text", "parent_text", "q_type", "domain", "difficulty",
            "company", "source", "title", "url");

    private final AppProperties props;
    private volatile MilvusClientV2 client;
    private volatile boolean ready = false;

    public MilvusService(AppProperties props) {
        this.props = props;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void init() {
        try {
            AppProperties.Milvus cfg = props.getAi().getMilvus();
            ConnectConfig config = ConnectConfig.builder()
                    .uri("http://" + cfg.getHost() + ":" + cfg.getPort())
                    .build();
            client = new MilvusClientV2(config);
            createCollectionIfAbsent();
            ready = true;
            log.info("Milvus connected {}:{} collection={}", cfg.getHost(), cfg.getPort(), cfg.getCollection());
        } catch (Exception e) {
            log.warn("Milvus init failed (degraded): {}", e.getMessage());
        }
    }

    public boolean isReady() {
        return ready && client != null;
    }

    private void ensureClient() {
        if (!isReady()) {
            throw new IllegalStateException("Milvus 不可用");
        }
    }

    private String collection() {
        return props.getAi().getMilvus().getCollection();
    }

    private void createCollectionIfAbsent() {
        Boolean exists = client.hasCollection(HasCollectionReq.builder()
                .collectionName(collection())
                .build());
        if (Boolean.TRUE.equals(exists)) {
            ensurePartitions();
            return;
        }

        int dim = props.getAi().getMilvus().getDim();
        List<CreateCollectionReq.FieldSchema> fields = List.of(
                CreateCollectionReq.FieldSchema.builder()
                        .name("id").dataType(DataType.Int64).isPrimaryKey(true).autoID(true).build(),
                CreateCollectionReq.FieldSchema.builder()
                        .name("text").dataType(DataType.VarChar).maxLength(65535).build(),
                CreateCollectionReq.FieldSchema.builder()
                        .name("parent_text").dataType(DataType.VarChar).maxLength(65535).build(),
                CreateCollectionReq.FieldSchema.builder()
                        .name("dense_vector").dataType(DataType.FloatVector).dimension(dim).build(),
                CreateCollectionReq.FieldSchema.builder()
                        .name("q_type").dataType(DataType.VarChar).maxLength(32).build(),
                CreateCollectionReq.FieldSchema.builder()
                        .name("domain").dataType(DataType.VarChar).maxLength(64).build(),
                CreateCollectionReq.FieldSchema.builder()
                        .name("position").dataType(DataType.VarChar).maxLength(64).build(),
                CreateCollectionReq.FieldSchema.builder()
                        .name("company").dataType(DataType.VarChar).maxLength(64).build(),
                CreateCollectionReq.FieldSchema.builder()
                        .name("difficulty").dataType(DataType.Int8).build(),
                CreateCollectionReq.FieldSchema.builder()
                        .name("source").dataType(DataType.VarChar).maxLength(256).build(),
                CreateCollectionReq.FieldSchema.builder()
                        .name("title").dataType(DataType.VarChar).maxLength(512).build(),
                CreateCollectionReq.FieldSchema.builder()
                        .name("url").dataType(DataType.VarChar).maxLength(512).build());

        CreateCollectionReq req = CreateCollectionReq.builder()
                .collectionName(collection())
                .collectionSchema(CreateCollectionReq.CollectionSchema.builder()
                        .fieldSchemaList(fields)
                        .build())
                .build();
        client.createCollection(req);

        // 建索引
        Map<String, Object> extraParams = Map.of("nlist", 128);
        client.createIndex(CreateIndexReq.builder()
                .collectionName(collection())
                .indexParams(List.of(IndexParam.builder()
                        .fieldName("dense_vector")
                        .indexType(IndexParam.IndexType.IVF_FLAT)
                        .metricType(IndexParam.MetricType.IP)
                        .extraParams(extraParams)
                        .build()))
                .build());

        ensurePartitions();
        client.loadCollection(LoadCollectionReq.builder().collectionName(collection()).build());
        log.info("Milvus collection created: {}", collection());
    }

    private void ensurePartitions() {
        for (String p : PARTITIONS) {
            try {
                client.createPartition(CreatePartitionReq.builder()
                        .collectionName(collection()).partitionName(p).build());
            } catch (Exception ignore) {
                // 分区已存在
            }
        }
    }

    /** 稠密向量检索 */
    public List<SearchHit> searchDense(float[] queryVector, int topK, String filterExpr, String partition) {
        ensureClient();
        try {
            SearchReq req = SearchReq.builder()
                    .collectionName(collection())
                    .data(List.of(new FloatVec(queryVector)))
                    .annsField("dense_vector")
                    .topK(topK)
                    .filter(filterExpr == null ? "" : filterExpr)
                    .outputFields(SEARCH_FIELDS)
                    .metricType(IndexParam.MetricType.IP)
                    .searchParams(Map.of("nprobe", 10))
                    .partitionNames(partition == null ? List.of() : List.of(partition))
                    .build();
            SearchResp resp = client.search(req);
            List<SearchHit> hits = new ArrayList<>();
            // getSearchResults 返回 List<List<SearchResult>>（每个查询向量一个列表）
            List<List<SearchResp.SearchResult>> results = resp.getSearchResults();
            if (!results.isEmpty()) {
                for (SearchResp.SearchResult r : results.get(0)) {
                    Map<String, Object> entity = r.getEntity();
                    hits.add(new SearchHit(
                            r.getScore(),
                            str(entity, "text"), str(entity, "parent_text"),
                            str(entity, "q_type"), str(entity, "domain"),
                            intVal(entity, "difficulty"), str(entity, "company"),
                            str(entity, "source"), str(entity, "title"), str(entity, "url")));
                }
            }
            return hits;
        } catch (Exception e) {
            log.warn("searchDense failed: {}", e.getMessage());
            return List.of();
        }
    }

    /** 标量过滤查询（抽题/浏览/统计） */
    public List<Map<String, Object>> query(String filterExpr, List<String> outputFields,
                                           int limit, int offset) {
        ensureClient();
        try {
            QueryReq req = QueryReq.builder()
                    .collectionName(collection())
                    .filter(filterExpr)
                    .outputFields(outputFields)
                    .limit(limit)
                    .offset(offset)
                    .build();
            QueryResp resp = client.query(req);
            List<Map<String, Object>> results = new ArrayList<>();
            for (QueryResp.QueryResult r : resp.getQueryResults()) {
                results.add(r.getEntity());
            }
            return results;
        } catch (Exception e) {
            log.warn("query failed: {}", e.getMessage());
            return List.of();
        }
    }

    /** 统计符合条件的行数 */
    public long count(String filterExpr) {
        ensureClient();
        try {
            QueryReq req = QueryReq.builder()
                    .collectionName(collection())
                    .filter(filterExpr)
                    .outputFields(List.of("count(*)"))
                    .build();
            QueryResp resp = client.query(req);
            List<QueryResp.QueryResult> results = resp.getQueryResults();
            if (!results.isEmpty()) {
                Object v = results.get(0).getEntity().get("count(*)");
                if (v instanceof Number n) return n.longValue();
            }
        } catch (Exception e) {
            log.warn("count failed: {}", e.getMessage());
        }
        return 0;
    }

    /** 按 source 删除（增量更新幂等清理） */
    public long deleteBySource(String source) {
        ensureClient();
        try {
            String escaped = source.replace("\\", "\\\\").replace("\"", "\\\"");
            String expr = "source == \"" + escaped + "\"";
            DeleteResp resp = client.delete(DeleteReq.builder()
                    .collectionName(collection()).filter(expr).build());
            return resp.getDeleteCnt();
        } catch (Exception e) {
            log.warn("deleteBySource failed: {}", e.getMessage());
            return 0;
        }
    }

    /** 批量插入（rows 中 dense_vector 键对应 float[] 值） */
    public int insert(List<Map<String, Object>> rows, String partition) {
        ensureClient();
        try {
            List<JsonObject> data = new ArrayList<>();
            for (Map<String, Object> row : rows) {
                JsonObject obj = new JsonObject();
                for (Map.Entry<String, Object> e : row.entrySet()) {
                    Object v = e.getValue();
                    if (v instanceof float[] arr) {
                        com.google.gson.JsonArray arrJson = new com.google.gson.JsonArray();
                        for (float f : arr) arrJson.add(f);
                        obj.add(e.getKey(), arrJson);
                    } else if (v instanceof String s) {
                        obj.addProperty(e.getKey(), s);
                    } else if (v instanceof Number n) {
                        obj.addProperty(e.getKey(), n);
                    } else if (v instanceof Boolean b) {
                        obj.addProperty(e.getKey(), b);
                    }
                }
                // collection schema 要求 sparse_vector（Python 侧 BGE-M3 稀疏通道）；
                // Java 为纯稠密检索，补空稀疏向量满足 schema，不影响稠密检索与 RRF（稀疏通道贡献 0）
                if (!obj.has("sparse_vector")) {
                    obj.add("sparse_vector", new JsonObject());
                }
                data.add(obj);
            }
            InsertResp resp = client.insert(InsertReq.builder()
                    .collectionName(collection())
                    .data(data)
                    .partitionName(partition)
                    .build());
            return (int) resp.getInsertCnt();
        } catch (Exception e) {
            log.warn("insert failed: {}", e.getMessage());
            return 0;
        }
    }

    /** 构造标量过滤表达式（AND 组合） */
    public static String buildFilterExpr(String domain, String qType, Integer difficulty,
                                          String company, String position) {
        List<String> clauses = new ArrayList<>();
        if (domain != null && !domain.isBlank()) clauses.add("domain == \"" + escape(domain) + "\"");
        if (qType != null && !qType.isBlank()) clauses.add("q_type == \"" + escape(qType) + "\"");
        if (difficulty != null) clauses.add("difficulty == " + difficulty);
        if (company != null && !company.isBlank()) clauses.add("company == \"" + escape(company) + "\"");
        if (position != null && !position.isBlank()) clauses.add("position == \"" + escape(position) + "\"");
        return String.join(" and ", clauses);
    }

    private static String escape(String v) {
        return v.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private static String str(Map<String, Object> m, String k) {
        Object v = m.get(k);
        return v == null ? "" : v.toString();
    }

    private static int intVal(Map<String, Object> m, String k) {
        Object v = m.get(k);
        if (v instanceof Number n) return n.intValue();
        return 0;
    }

    @Override
    public void destroy() {
        if (client != null) {
            try { client.close(); } catch (Exception ignore) {}
        }
    }

    /** 检索命中结果 */
    public record SearchHit(
            float score, String text, String parentText,
            String qType, String domain, int difficulty, String company,
            String source, String title, String url) {
    }
}

package com.interviewace.service;

import java.util.List;

import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.interviewace.common.BizException;
import com.interviewace.dto.ResumeDetail;
import com.interviewace.dto.ResumeListItem;
import com.interviewace.entity.Resume;
import com.interviewace.mapper.ResumeMapper;

/**
 * 简历备考服务（查询侧）：历史列表 / 详情。
 * 对应 mysql.py list_resumes / get_resume；
 * 上传解析、话术生成、项目预演在 ResumeGenerateService（M3）。
 */
@Service
public class ResumeService {

    private final ResumeMapper resumeMapper;
    private final ObjectMapper objectMapper;

    public ResumeService(ResumeMapper resumeMapper, ObjectMapper objectMapper) {
        this.resumeMapper = resumeMapper;
        this.objectMapper = objectMapper;
    }

    public List<ResumeListItem> list(Integer userId) {
        return resumeMapper.selectList(new LambdaQueryWrapper<Resume>()
                        .eq(Resume::getUserId, userId)
                        .orderByDesc(Resume::getCreatedAt)
                        .last("LIMIT 50")).stream()
                .map(r -> new ResumeListItem(r.getId(), r.getFilename(), r.getName(),
                        r.getTarget(), r.getCreatedAt()))
                .toList();
    }

    /** 详情：解析 profile/questions/pitch/rehearse 四段 JSON（缺失给空，与 Python .get 默认值一致） */
    public ResumeDetail detail(Integer resumeId, Integer userId) {
        Resume r = resumeMapper.selectOne(new LambdaQueryWrapper<Resume>()
                .eq(Resume::getId, resumeId)
                .eq(Resume::getUserId, userId)
                .last("LIMIT 1"));
        if (r == null) {
            throw BizException.notFound("简历不存在");
        }

        JsonNode profile = readTreeOr(r.getProfileJson(), "{}");
        JsonNode questions = readTreeOr(r.getQuestionsJson(), "[]");
        JsonNode pitch = r.getPitchJson() == null ? null : readTreeOr(r.getPitchJson(), "null");
        JsonNode rehearse = r.getRehearseJson() == null ? null : readTreeOr(r.getRehearseJson(), "null");

        return new ResumeDetail(
                r.getId(), r.getFilename(),
                textOrEmpty(profile, "name"), textOrEmpty(profile, "target"),
                profile.has("skills") ? profile.get("skills") : objectMapper.createArrayNode(),
                profile.has("projects") ? profile.get("projects") : objectMapper.createArrayNode(),
                questions, pitch, rehearse, r.getCreatedAt());
    }

    private String textOrEmpty(JsonNode parent, String field) {
        JsonNode n = parent.get(field);
        if (n == null || n.isNull() || n.isMissingNode() || !n.isTextual()) {
            return n == null || n.isNull() || n.isMissingNode() ? "" : n.asText();
        }
        return n.asText();
    }

    private JsonNode readTreeOr(String json, String fallback) {
        String source = json == null || json.isBlank() ? fallback : json;
        try {
            return objectMapper.readTree(source);
        } catch (Exception e) {
            return objectMapper.nullNode();
        }
    }
}

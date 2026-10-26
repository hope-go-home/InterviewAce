package com.interviewace.service.resume;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.apache.tika.Tika;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.interviewace.common.BizException;
import com.interviewace.entity.Resume;
import com.interviewace.mapper.ResumeMapper;
import com.interviewace.service.llm.LLMClient;

/**
 * 简历备考服务：文件解析（Tika）+ LLM 结构化 + 话术生成 + 项目预演。
 * 对应 Python resume_service.py。
 */
@Service
public class ResumeGenerateService {

    private static final Logger log = LoggerFactory.getLogger(ResumeGenerateService.class);
    private static final int MAX_TEXT = 6000;

    private final LLMClient llm;
    private final ObjectMapper objectMapper;
    private final ResumeMapper resumeMapper;
    private final Tika tika = new Tika();

    public ResumeGenerateService(LLMClient llm, ObjectMapper objectMapper, ResumeMapper resumeMapper) {
        this.llm = llm;
        this.objectMapper = objectMapper;
        this.resumeMapper = resumeMapper;
    }

    /** 上传简历 → Tika 提取文本 → LLM 结构化 → 存库 */
    public Map<String, Object> upload(byte[] fileBytes, String filename, Integer userId) {
        // Tika 提取文本
        String text;
        try {
            text = tika.parseToString(new java.io.ByteArrayInputStream(fileBytes));
            if (text.length() > MAX_TEXT) text = text.substring(0, MAX_TEXT);
        } catch (Exception e) {
            throw BizException.badRequest("文件解析失败：" + e.getMessage());
        }
        if (text.strip().length() < 30) {
            throw BizException.badRequest("简历内容太少，无法解析");
        }

        // LLM 结构化
        String prompt = String.format("""
                你是一位资深技术面试官。请阅读下面这份简历，抽取关键信息并生成针对性面试题。

                简历内容：
                %s

                输出 JSON（不要 markdown 包裹）：
                {"name": "姓名或称呼", "target": "目标岗位", "skills": ["技能1"], "projects": ["项目1 一句话"], "questions": [{"question": "面试官会问的具体问题", "domain": "知识域", "why": "为什么问这个"}]}

                要求：questions 生成 10-15 道，覆盖项目深挖/技能原理/基础知识/行为问题。domain 从枚举选：llm_basics/prompt/rag/agent/vectordb/framework/python_backend/ml_dl/cs_basic
                """, text);

        Map<String, Object> data;
        try {
            String raw = llm.chat(prompt, true, 0.4);
            data = objectMapper.readValue(raw, new TypeReference<Map<String, Object>>() {});
        } catch (Exception e) {
            throw BizException.serverError("简历解析失败：" + e.getMessage());
        }

        // 存库
        Resume r = new Resume();
        r.setUserId(userId);
        r.setFilename(filename);
        r.setName(str(data, "name"));
        r.setTarget(str(data, "target"));
        r.setProfileJson(toJson(data));
        r.setQuestionsJson(toJson(data.getOrDefault("questions", List.of())));
        r.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
        resumeMapper.insert(r);

        Map<String, Object> result = new HashMap<>(data);
        result.put("resume_id", r.getId());
        return result;
    }

    /** 生成 60s/90s 自我介绍话术 */
    public Map<String, Object> generatePitch(Map<String, Object> profile, String level, Integer resumeId) {
        String profileJson = toJson(profile);
        String prompt = String.format("""
                你是资深求职教练。请根据下面的简历信息，写两版自我介绍话术：60 秒版和 90 秒版。

                简历信息：
                %s

                要求：
                - 60 秒版：简洁有力，突出最匹配的 1-2 个亮点
                - 90 秒版：在 60 秒基础上展开一个代表性项目的技术亮点
                - 口语化、适合开口说
                - 级别：%s；目标岗位：%s
                - 输出 JSON：{"pitch_60": "...", "pitch_90": "..."}
                """, profileJson, level, profile.getOrDefault("target", ""));

        Map<String, Object> data;
        try {
            String raw = llm.chat(prompt, true, 0.5);
            data = objectMapper.readValue(raw, new TypeReference<Map<String, Object>>() {});
        } catch (Exception e) {
            throw BizException.serverError("生成话术失败：" + e.getMessage());
        }

        if (resumeId != null) {
            try {
                Resume r = resumeMapper.selectById(resumeId);
                if (r != null) {
                    r.setPitchJson(toJson(data));
                    resumeMapper.updateById(r);
                }
            } catch (Exception e) {
                log.warn("save pitch failed: {}", e.getMessage());
            }
        }
        return data;
    }

    /** 项目预演：深挖问题 + 应答要点 */
    public Map<String, Object> rehearseProject(String project, List<String> skills, int n, Integer resumeId) {
        String prompt = String.format("""
                你是技术面试官。针对下面这个项目，出 %d 个层层递进的深挖问题（技术选型→架构→难点→权衡→数据指标），并给出每个问题的应答要点（STAR 话术骨架）。

                项目：%s
                求职者技能：%s

                输出 JSON：{"questions": [{"question": "...", "points": ["要点1", "要点2"]}]}
                """, n, project, String.join(", ", skills));

        Map<String, Object> data;
        try {
            String raw = llm.chat(prompt, true, 0.5);
            data = objectMapper.readValue(raw, new TypeReference<Map<String, Object>>() {});
        } catch (Exception e) {
            throw BizException.serverError("项目预演失败：" + e.getMessage());
        }

        if (resumeId != null) {
            try {
                Resume r = resumeMapper.selectById(resumeId);
                if (r != null) {
                    r.setRehearseJson(toJson(data));
                    resumeMapper.updateById(r);
                }
            } catch (Exception e) {
                log.warn("save rehearse failed: {}", e.getMessage());
            }
        }
        data.put("project", project);
        return data;
    }

    private String toJson(Object o) {
        try { return objectMapper.writeValueAsString(o); } catch (Exception e) { return "[]"; }
    }

    private static String str(Map<String, Object> m, String k) {
        Object v = m.get(k);
        return v == null ? "" : v.toString();
    }
}

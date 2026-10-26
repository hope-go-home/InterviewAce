package com.interviewace.entity;

import java.time.LocalDateTime;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/** 简历备考历史：上传的简历及其生成的备考内容（面试题/话术/预演）。 */
@Data
@TableName("resume")
public class Resume {

    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    private Integer userId;

    private String filename;

    /** 目标岗位 */
    private String target;

    /** 姓名 */
    private String name;

    /** 结构化简历 JSON */
    private String profileJson;

    /** 生成的面试题 JSON */
    private String questionsJson;

    /** 自我介绍话术 JSON */
    private String pitchJson;

    /** 项目预演 JSON（按项目缓存） */
    private String rehearseJson;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}

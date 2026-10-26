package com.interviewace.entity;

import java.time.LocalDateTime;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/** 模拟面试：一场面试的配置与状态。 */
@Data
@TableName("interview_session")
public class InterviewSession {

    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    private Integer userId;

    private String position;

    private String level;

    /** JSON 选中的知识域列表 */
    private String domains;

    private Integer numQuestions;

    private Integer difficultyCap;

    /** in_progress / finished */
    private String status;

    private Integer currentSeq;

    private Integer totalScore;

    /** 总评报告 JSON */
    private String reportJson;

    private LocalDateTime createdAt;

    private LocalDateTime finishedAt;
}

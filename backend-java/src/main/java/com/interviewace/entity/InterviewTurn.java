package com.interviewace.entity;

import java.time.LocalDateTime;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/** 模拟面试：一轮问答（含追问，parent_turn_id 挂到主问题）。 */
@Data
@TableName("interview_turn")
public class InterviewTurn {

    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    private Integer sessionId;

    /** 主问题序号 */
    private Integer seq;

    /** 追问链：指向主问题 turn id */
    private Integer parentTurnId;

    /** 0=主问题，1/2=第几层追问 */
    private Integer followupNo;

    private String question;

    /** rag / resume / llm */
    private String questionSource;

    /** JSON：检索到的参考题 [{title,url,score}] */
    private String qaRefs;

    private String answer;

    /** 0-100 */
    private Integer score;

    /** 四维得分 JSON */
    private String dimJson;

    private String feedback;

    /** JSON list */
    private String missingPoints;

    private LocalDateTime createdAt;
}

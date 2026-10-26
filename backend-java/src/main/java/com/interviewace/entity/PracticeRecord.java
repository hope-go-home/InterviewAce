package com.interviewace.entity;

import java.time.LocalDateTime;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/**
 * 答题练习记录：每次作答的评分与点评。
 * 注意 JSON 字段（dim_json / missing_points）以字符串列存储，读写时再序列化。
 */
@Data
@TableName("practice_record")
public class PracticeRecord {

    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    private Integer userId;

    /** 题干（题没有自增 id，用 title 标识） */
    private String questionTitle;

    private String questionUrl;

    private String domain;

    private Integer difficulty;

    private String position;

    /** intern / campus / social */
    private String level;

    private String myAnswer;

    /** 0-100 */
    private Integer score;

    /** 各维度得分 JSON */
    private String dimJson;

    private String feedback;

    /** JSON list */
    private String missingPoints;

    /** score<60 进错题本（列名 is_wrong，勿改） */
    private Boolean isWrong;

    private LocalDateTime createdAt;
}

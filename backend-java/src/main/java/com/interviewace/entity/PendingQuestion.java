package com.interviewace.entity;

import java.time.LocalDateTime;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/** 待补题池：题库外被问到的问题，待生成答案入库。 */
@Data
@TableName("pending_question")
public class PendingQuestion {

    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    private String question;

    private String domain;

    private String position;

    private Integer askCount;

    private String draftAnswer;

    private String sourceUrl;

    /** pending / drafted / adopted */
    private String status;

    private LocalDateTime createdAt;
}

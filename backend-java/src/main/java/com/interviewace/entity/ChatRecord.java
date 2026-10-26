package com.interviewace.entity;

import java.time.LocalDateTime;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/** 问答会话记录：历史会话按用户隔离。 */
@Data
@TableName("chat_records")
public class ChatRecord {

    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    private String sessionId;

    private Integer userId;

    private String question;

    private String answer;

    private LocalDateTime createdAt;
}

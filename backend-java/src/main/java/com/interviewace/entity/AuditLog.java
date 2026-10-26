package com.interviewace.entity;

import java.time.LocalDateTime;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/** 审计日志：登录、提问、上传、删除等敏感操作留痕。 */
@Data
@TableName("audit_logs")
public class AuditLog {

    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    private Integer userId;

    private String username;

    /** login / chat / upload / delete */
    private String action;

    private String resource;

    private String detail;

    private String ip;

    private LocalDateTime createdAt;
}

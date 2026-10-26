package com.interviewace.entity;

import java.time.LocalDateTime;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/** 每日 token 用量：按用户/按天累计，用于每日预算熔断。 */
@Data
@TableName("token_usage")
public class TokenUsage {

    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    private Integer userId;

    /** YYYY-MM-DD（UTC，与 Python datetime.utcnow() 一致） */
    private String day;

    private Integer tokens;

    private LocalDateTime updatedAt;
}

package com.interviewace.entity;

import java.time.LocalDateTime;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/**
 * 系统用户：角色绑定在服务端，前端不可伪造。
 * 密码哈希与 Python passlib bcrypt 完全互通。
 */
@Data
@TableName("users")
public class User {

    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    private String username;

    private String passwordHash;

    /** admin / user */
    private String role;

    @TableField("is_active")
    private Boolean active;

    private LocalDateTime createdAt;
}

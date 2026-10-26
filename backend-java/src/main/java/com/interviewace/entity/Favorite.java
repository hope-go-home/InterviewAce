package com.interviewace.entity;

import java.time.LocalDateTime;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/** 收藏 / 错题标记。 */
@Data
@TableName("favorite")
public class Favorite {

    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    private Integer userId;

    private String questionTitle;

    private String questionUrl;

    private String domain;

    private Integer difficulty;

    /** fav / wrong */
    private String ftype;

    private LocalDateTime createdAt;
}

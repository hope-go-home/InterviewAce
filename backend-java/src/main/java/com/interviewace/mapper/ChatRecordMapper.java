package com.interviewace.mapper;

import java.util.List;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.interviewace.dto.SessionSummary;
import com.interviewace.entity.ChatRecord;

@Mapper
public interface ChatRecordMapper extends BaseMapper<ChatRecord> {

    /**
     * 按会话聚合：首问、末次时间、问答条数（对应 mysql.py list_sessions）。
     * 派生表先聚合分页，再回查首问，避免 N+1。
     */
    // 列顺序必须与 SessionSummary 构造参数顺序一致：MyBatis 构造器自动映射按位置而非列名
    @Select("""
            SELECT g.session_id,
                   (SELECT c2.question FROM chat_records c2 WHERE c2.id = g.first_id) AS first_question,
                   g.last_time,
                   g.cnt AS `count`
            FROM (SELECT session_id,
                         MIN(id)   AS first_id,
                         MAX(created_at) AS last_time,
                         COUNT(*)  AS cnt
                  FROM chat_records
                  WHERE user_id = #{userId}
                  GROUP BY session_id
                  ORDER BY MAX(created_at) DESC
                  LIMIT #{limit}) g
            """)
    List<SessionSummary> listSessions(@Param("userId") Integer userId, @Param("limit") int limit);
}

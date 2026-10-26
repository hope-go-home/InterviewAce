package com.interviewace.mapper;

import org.apache.ibatis.annotations.Mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.interviewace.entity.AuditLog;

@Mapper
public interface AuditLogMapper extends BaseMapper<AuditLog> {
}

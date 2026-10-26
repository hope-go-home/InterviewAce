package com.interviewace.common.audit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.interviewace.entity.AuditLog;
import com.interviewace.mapper.AuditLogMapper;

import java.time.LocalDateTime;
import java.time.ZoneOffset;

/**
 * 审计日志服务：登录、提问、上传、删除等敏感操作留痕。
 * 对应 mysql.py write_audit()；写失败只告警，不影响主流程。
 */
@Service
public class AuditService {

    private static final Logger log = LoggerFactory.getLogger(AuditService.class);
    private static final int DETAIL_MAX = 2000;

    private final AuditLogMapper auditLogMapper;

    public AuditService(AuditLogMapper auditLogMapper) {
        this.auditLogMapper = auditLogMapper;
    }

    public void write(Integer userId, String username, String action,
                      String resource, String detail, String ip) {
        try {
            AuditLog row = new AuditLog();
            row.setUserId(userId);
            row.setUsername(username);
            row.setAction(action);
            row.setResource(resource == null ? "" : resource);
            row.setDetail(detail == null ? "" : truncate(detail, DETAIL_MAX));
            row.setIp(ip == null ? "" : ip);
            row.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
            auditLogMapper.insert(row);
        } catch (Exception e) {
            log.warn("审计日志写入失败: {}", e.getMessage());
        }
    }

    private String truncate(String s, int max) {
        return s.length() <= max ? s : s.substring(0, max);
    }
}

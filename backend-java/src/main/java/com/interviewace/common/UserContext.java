package com.interviewace.common;

/**
 * 当前登录用户上下文（由 JWT 拦截器解析后放入 request attribute）。
 * 对应 Python 侧 Depends(get_current_user) 返回的 user dict。
 */
public record UserContext(Integer id, String username, String role) {

    public static final String REQUEST_ATTRIBUTE = "iaCurrentUser";

    public boolean isAdmin() {
        return "admin".equals(role);
    }
}

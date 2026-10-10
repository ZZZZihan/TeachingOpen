package org.jeecg.config;

import org.springframework.web.servlet.HandlerInterceptor;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

/** Reject unbounded HTTP pagination before any controller or count query runs. */
public class PaginationRequestInterceptor implements HandlerInterceptor {
    public static final int MAX_PAGE_SIZE = 100;

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
        if (valid(request.getParameterValues("pageNo"), Integer.MAX_VALUE)
                && valid(request.getParameterValues("pageSize"), MAX_PAGE_SIZE)) return true;
        response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"success\":false,\"code\":400,\"message\":\"页码必须为正整数，每页数量须为1至100\"}");
        return false;
    }

    private boolean valid(String[] values, int maximum) {
        if (values == null) return true;
        if (values.length != 1 || values[0] == null || !values[0].matches("[0-9]{1,10}")) return false;
        try {
            long value = Long.parseLong(values[0]);
            return value >= 1 && value <= maximum;
        } catch (NumberFormatException invalid) {
            return false;
        }
    }
}

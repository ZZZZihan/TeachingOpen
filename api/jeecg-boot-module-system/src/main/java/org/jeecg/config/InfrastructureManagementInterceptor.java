package org.jeecg.config;

import javax.servlet.http.HttpServletRequest;
import org.apache.shiro.authz.UnauthorizedException;
import javax.servlet.http.HttpServletResponse;
import org.jeecg.modules.quartz.controller.QuartzJobController;
import org.jeecg.modules.system.controller.SysDataSourceController;
import org.jeecg.modules.system.service.InfrastructureAccessService;
import org.springframework.stereotype.Component;
import org.springframework.util.ClassUtils;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.HandlerInterceptor;

/** Protect compiled Online controllers as well as local infrastructure controllers. */
@Component
public class InfrastructureManagementInterceptor implements HandlerInterceptor {
    private final InfrastructureAccessService access;
    public InfrastructureManagementInterceptor(InfrastructureAccessService access) { this.access = access; }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
        if (handler instanceof HandlerMethod) {
            Class<?> type = ClassUtils.getUserClass(((HandlerMethod) handler).getBeanType());
            // Class-based matching follows Spring's actual handler, including suffix, encoded,
            // semicolon and trailing-slash aliases. A raw URI prefix can miss those aliases.
            if (type.getName().startsWith("org.jeecg.modules.online.")
                    || SysDataSourceController.class.isAssignableFrom(type)
                    || QuartzJobController.class.isAssignableFrom(type)) {
                try { access.requireOperator(); }
                catch (UnauthorizedException denied) {
                    // A .js/.json alias must not turn an authorization denial into content-negotiation 500.
                    response.setStatus(HttpServletResponse.SC_FORBIDDEN);
                    response.setContentType("application/json;charset=UTF-8");
                    response.getWriter().write("{\"success\":false,\"code\":403,\"message\":\"没有运维管理权限\"}");
                    return false;
                }
            }
        }
        return true;
    }
}

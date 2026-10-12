package org.jeecg.config;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.modules.monitor.controller.ActuatorRedisController;
import org.jeecg.modules.oss.controller.OSSFileController;
import org.jeecg.modules.system.controller.SysPositionController;
import org.jeecg.modules.system.controller.SysUploadController;
import org.jeecg.modules.system.controller.SysUserAgentController;
import org.jeecg.modules.system.service.InfrastructureAccessService;
import org.jeecg.modules.system.service.UserQueryAccessService;
import org.springframework.stereotype.Component;
import org.springframework.util.ClassUtils;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.HandlerInterceptor;

/** Narrow management boundary following Spring's resolved handler, including URL aliases. */
@Component
public class GlobalManagementInterceptor implements HandlerInterceptor {
    private final UserQueryAccessService accounts;
    private final InfrastructureAccessService infrastructure;

    public GlobalManagementInterceptor(UserQueryAccessService accounts, InfrastructureAccessService infrastructure) {
        this.accounts = accounts;
        this.infrastructure = infrastructure;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
        if (!(handler instanceof HandlerMethod)) return true;
        HandlerMethod method = (HandlerMethod) handler;
        Class<?> type = ClassUtils.getUserClass(method.getBeanType());
        try {
            if (ActuatorRedisController.class.isAssignableFrom(type)) {
                infrastructure.requireOperator();
            } else if (SysPositionController.class.isAssignableFrom(type)) {
                // The address book and position selector need this one read operation.
                if ("queryPageList".equals(method.getMethod().getName())) accounts.currentUser();
                else accounts.requireAdministrator();
            } else if (SysUserAgentController.class.isAssignableFrom(type)
                    || OSSFileController.class.isAssignableFrom(type)
                    || SysUploadController.class.isAssignableFrom(type)) {
                accounts.requireAdministrator();
            }
        } catch (UnauthorizedException denied) {
            // A suffix's media type must not turn a refusal into a negotiation error.
            response.setStatus(HttpServletResponse.SC_FORBIDDEN);
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write("{\"success\":false,\"code\":403,\"message\":\"没有管理权限\"}");
            return false;
        }
        return true;
    }
}

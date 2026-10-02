package org.jeecg.modules.shiro.authc.aop;

import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
import javax.servlet.http.HttpServletRequest;
import org.jeecg.modules.shiro.vo.DefContants;

/** Public work readers may be anonymous; a supplied credential must still be valid. */
public class OptionalJwtFilter extends JwtFilter {
    @Override
    protected boolean isAccessAllowed(ServletRequest request, ServletResponse response, Object mappedValue) {
        if (((HttpServletRequest) request).getHeader(DefContants.X_ACCESS_TOKEN) == null) {
            return true;
        }
        return super.isAccessAllowed(request, response, mappedValue);
    }
}

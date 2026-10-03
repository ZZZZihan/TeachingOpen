package org.jeecg.modules.shiro.authc.aop;

import org.apache.shiro.web.filter.InvalidRequestFilter;
import org.apache.shiro.web.util.WebUtils;

import javax.servlet.DispatcherType;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
import javax.servlet.http.HttpServletRequest;

/** Preserve Shiro's path guards while allowing Unicode storage keys on direct media reads. */
public final class LocalMediaInvalidRequestFilter extends InvalidRequestFilter {
    private static final String MEDIA_PREFIX = "/sys/common/static/";
    private final UnicodePathChecks unicodeChecks = new UnicodePathChecks();

    @Override
    protected boolean isAccessAllowed(ServletRequest req, ServletResponse response, Object mappedValue) throws Exception {
        HttpServletRequest request = WebUtils.toHttp(req);
        if (!isDirectMediaRead(request)) return super.isAccessAllowed(req, response, mappedValue);

        // Shiro's non-ASCII flag also rejects controls. Keep that boundary when
        // allowing Unicode; no per-request change is made to either filter.
        return withoutControls(request.getRequestURI())
                && withoutControls(request.getServletPath())
                && withoutControls(request.getPathInfo())
                && unicodeChecks.allows(req, response, mappedValue);
    }

    private static boolean isDirectMediaRead(HttpServletRequest request) {
        if (request.getDispatcherType() != DispatcherType.REQUEST
                || !("GET".equals(request.getMethod()) || "HEAD".equals(request.getMethod()))) return false;
        String uri = request.getRequestURI();
        String servletPath = request.getServletPath();
        String pathInfo = request.getPathInfo();
        // Require the literal route in both representations. Do not decode again,
        // normalize Unicode, or allow an encoded structural prefix into the exception.
        return uri != null && uri.startsWith(request.getContextPath() + MEDIA_PREFIX)
                && servletPath != null
                && (servletPath + (pathInfo == null ? "" : pathInfo)).startsWith(MEDIA_PREFIX);
    }

    private static boolean withoutControls(String value) {
        if (value == null) return true;
        for (int i = 0; i < value.length(); i++) {
            if (Character.isISOControl(value.charAt(i))) return false;
        }
        return true;
    }

    /** Reuse all upstream structural checks; only this private checker accepts Unicode. */
    private static final class UnicodePathChecks extends InvalidRequestFilter {
        private UnicodePathChecks() {
            setBlockNonAscii(false);
            // This narrow exception never permits backslashes, even with Shiro's
            // optional allowBackslash system property enabled elsewhere.
            setBlockBackslash(true);
        }

        private boolean allows(ServletRequest request, ServletResponse response, Object mappedValue) throws Exception {
            return super.isAccessAllowed(request, response, mappedValue);
        }
    }
}

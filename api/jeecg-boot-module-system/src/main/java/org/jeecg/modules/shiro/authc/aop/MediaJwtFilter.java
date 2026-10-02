package org.jeecg.modules.shiro.authc.aop;

import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

/** Anonymous public assets or a fully validated header/cookie credential; never URL tokens. */
public class MediaJwtFilter extends JwtFilter {
    public MediaJwtFilter(MediaCookie cookie) { super(cookie); }

    @Override
    protected String token(HttpServletRequest request) {
        String header = super.token(request);
        return header == null ? mediaCookie.read(request) : header;
    }

    @Override
    protected boolean isAccessAllowed(ServletRequest request, ServletResponse response, Object value) {
        HttpServletResponse http = (HttpServletResponse) response;
        http.setHeader("Cache-Control", "no-store");
        http.setHeader("Vary", "Cookie, X-Access-Token");
        String method = ((HttpServletRequest) request).getMethod();
        if (!"GET".equals(method) && !"HEAD".equals(method)) { http.setStatus(405); return false; }
        return token((HttpServletRequest) request) == null || super.isAccessAllowed(request, response, value);
    }

    @Override
    protected boolean onAccessDenied(ServletRequest request, ServletResponse response) throws Exception {
        if (((HttpServletResponse) response).getStatus() == 405) return false;
        mediaCookie.write((HttpServletRequest) request, (HttpServletResponse) response, "", true);
        if ("HEAD".equals(((HttpServletRequest) request).getMethod())) {
            ((HttpServletResponse) response).setStatus(401); return false;
        }
        return super.onAccessDenied(request, response);
    }
}

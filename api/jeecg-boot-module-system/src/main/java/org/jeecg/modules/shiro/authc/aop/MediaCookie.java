package org.jeecg.modules.shiro.authc.aop;

import javax.servlet.http.Cookie;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

/** Browser media tags cannot set X-Access-Token. Only the download filter reads this cookie. */
@Component
public class MediaCookie {
    @Value("${jeecg.media.cookie-name:teaching_media}") private String name;

    public String read(HttpServletRequest request) {
        String token = null;
        if (request.getCookies() != null) for (Cookie cookie : request.getCookies()) {
            if (name.equals(cookie.getName())) {
                if (token != null) return ""; // Ambiguous cookies fail authentication.
                token = cookie.getValue();
            }
        }
        return token;
    }

    public void issue(String token) {
        if (RequestContextHolder.getRequestAttributes() instanceof ServletRequestAttributes) {
            ServletRequestAttributes context = (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();
            if (context.getResponse() != null) write(context.getRequest(), context.getResponse(), token, false);
        }
    }

    public void write(HttpServletRequest request, HttpServletResponse response, String token, boolean clear) {
        response.addHeader("Set-Cookie", name + "=" + (clear ? "" : token)
                + "; Path=" + request.getContextPath() + "/sys/common/static; HttpOnly; SameSite=Strict"
                + (request.isSecure() ? "; Secure" : "") + (clear ? "; Max-Age=0" : ""));
        response.setHeader("Cache-Control", "no-store");
    }
}

package org.jeecg.modules.common.util;

import com.qiniu.util.Auth;
import com.qiniu.util.StringMap;
import org.apache.shiro.authz.UnauthorizedException;
import java.nio.charset.StandardCharsets;
import org.springframework.util.DigestUtils;

/** User-scoped, insert-only credentials. Client-provided object keys are never authority. */
public final class QiniuUploadPolicy {
    private QiniuUploadPolicy() { }

    public static String prefix(String userId) {
        if (userId == null || userId.isEmpty()) throw new UnauthorizedException("请先登录");
        return "user-upload/" + DigestUtils.md5DigestAsHex(userId.getBytes(StandardCharsets.UTF_8)) + "/";
    }

    public static void requireOwnedKey(String userId, String key) {
        String prefix = prefix(userId);
        if (key == null || !key.startsWith(prefix) || key.length() <= prefix.length() || key.length() > 1024
                || key.indexOf('\\') >= 0 || key.indexOf(':') >= 0 || key.chars().anyMatch(Character::isISOControl)) {
            throw new UnauthorizedException("只能上传和登记本人目录内的文件");
        }
        for (String part : key.split("/", -1)) {
            if (part.isEmpty() || part.equals(".") || part.equals("..")) throw new UnauthorizedException("文件路径不合法");
        }
    }

    public static String token(Auth auth, String bucket, String userId, String key, long expires) {
        StringMap policy = new StringMap().put("insertOnly", 1);
        if (key == null) {
            policy.put("isPrefixalScope", 1);
            key = prefix(userId);
        } else requireOwnedKey(userId, key);
        return auth.uploadToken(bucket, key, expires, policy);
    }
}
